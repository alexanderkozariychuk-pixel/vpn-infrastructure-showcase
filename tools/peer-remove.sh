#!/usr/bin/env bash
#
# peer-remove.sh — take a reviewed list of client peers off the entry node,
# with a snapshot to come back to. Runs on the node, as root:
#
#   scp tools/peer-remove.sh remove.txt sov-entry:/tmp/
#   ssh -t sov-entry 'sudo bash /tmp/peer-remove.sh /tmp/remove.txt'            # dry run
#   ssh -t sov-entry 'sudo bash /tmp/peer-remove.sh /tmp/remove.txt --apply'
#   ssh -t sov-entry 'sudo bash /tmp/peer-remove.sh --restore 10.88.88.207'
#
# The list: one peer per line, "<address> <first 8+ characters of its public
# key> [a note]", as tools/peer_reconcile.py prints them. Blank lines and
# lines starting with # are skipped. Full keys never leave the node: each line
# is matched here against the running interface by its address, and the
# beginning of the key must agree.
#
# Every line is checked before anything changes, and one bad line stops the
# whole run — an address that is not a client's, not on the node, carried by
# two peers or listed twice, a key that does not match. A peer with a
# handshake in the last 3 minutes is someone connected right now: it is
# refused unless --allow-live is given.
#
# --apply   A snapshot first — awg0.conf and `awg show awg0 dump` into
#           /root/peer-audit-<time>/, mode 700 — then pwa-del-peer for each
#           peer in list order, stopping at the first refusal. pwa-del-peer
#           keeps a full copy of the config before every edit; when every
#           removal succeeded, the copies made by this run are shredded, since
#           the snapshot holds the same. Older copies are not touched.
#
# --restore <address>
#           Puts one peer back from the newest snapshot (or $SNAP): its block
#           appended to awg0.conf the way pwa-add-peer writes one, then the
#           peer set on the running interface with its own preshared key.
#           Refuses if the key or the address is in use.
#
# The snapshot holds every client's preshared key; delete the directory once
# nothing will be restored from it.

set -uo pipefail
export LC_ALL=C PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
umask 077

IFACE=${IFACE:-awg0}
CONF=${CONF:-/etc/amnezia/amneziawg/$IFACE.conf}
SNAP_ROOT=${SNAP_ROOT:-/root}
AWG=${AWG:-awg}
DEL=${DEL:-pwa-del-peer}
LIVE_S=180

die() { echo "STOP: $*" >&2; exit 1; }
now=$(date +%s)

ago() {
    local hs=$1 s
    (( hs > 0 )) || { echo "никогда"; return; }
    s=$(( now - hs ))
    if (( s < 3600 )); then echo "$(( s / 60 )) мин назад"
    elif (( s < 172800 )); then echo "$(( s / 3600 )) ч назад"
    else echo "$(( s / 86400 )) дн назад"; fi
}

# One line per peer: pub psk endpoint allowed-ips handshake rx tx keepalive.
dump() { "$AWG" show "$IFACE" dump | awk 'NR > 1'; }

client_ip() { [[ $1 =~ ^10\.88\.(88|89)\.([0-9]{1,3})$ ]] && (( BASH_REMATCH[2] <= 255 )); }

# The running peers whose allowed-ips hold exactly <ip>/32.
peers_with() { dump | awk -v ip="$1/32" '{ n = split($4, a, ","); for (i = 1; i <= n; i++) if (a[i] == ip) print }'; }

# ── restore ─────────────────────────────────────────────────────────────

restore() {
    local ip=$1 snap line pub psk ips ka header before pskfile n
    client_ip "$ip" || die "$ip is not a client address"
    if [[ -n ${SNAP:-} ]]; then snap=$SNAP; else
        local all=("$SNAP_ROOT"/peer-audit-*)   # a glob comes back sorted; the names are timestamps
        snap=${all[-1]}
    fi
    [[ -n $snap && -f $snap/dump && -f $snap/$IFACE.conf ]] || die "no snapshot found (looked in $SNAP_ROOT/peer-audit-*)"

    line=$(awk -v ip="$ip/32" 'NR > 1 { n = split($4, a, ","); for (i = 1; i <= n; i++) if (a[i] == ip) print }' "$snap/dump")
    n=$(grep -c . <<<"$line")
    (( n == 1 )) || die "the snapshot $snap has $n peers with $ip"
    read -r pub psk _ ips _ _ _ ka <<<"$line"

    dump | awk '{ print $1 }' | grep -qxF -- "$pub" && die "this peer is already on $IFACE"
    [[ -z $(peers_with "$ip") ]] || die "$ip is in use by another peer on $IFACE"
    grep -qF -- "$pub" "$CONF" && die "the key is already in $CONF"

    # The "### name" line that opened its block in the snapshot, if it had one.
    header=$(awk -v key="$pub" '
        /^###/      { h = $0; fresh = 1; next }
        /^\[Peer\]/ { if (!fresh) h = ""; fresh = 0; next }
        /^[[:space:]]*PublicKey[[:space:]]*=/ {
            v = $0; sub(/^[^=]*=[[:space:]]*/, "", v); gsub(/[[:space:]]+$/, "", v)
            if (v == key) { print h; exit }
        }' "$snap/$IFACE.conf")

    before="$snap/$IFACE.conf.before-restore-$ip-$(date +%Y%m%d-%H%M%S)"
    cp -p "$CONF" "$before"
    {
        printf '\n\n'
        [[ -n $header ]] && printf '%s\n' "$header"
        printf '[Peer]\nPublicKey = %s\n' "$pub"
        [[ $psk != "(none)" ]] && printf 'PresharedKey = %s\n' "$psk"
        printf 'AllowedIPs = %s\n' "$ips"
        [[ $ka != off ]] && printf 'PersistentKeepalive = %s\n' "$ka"
    } >> "$CONF"

    local args=(set "$IFACE" peer "$pub")
    if [[ $psk != "(none)" ]]; then
        pskfile=$(mktemp)
        printf '%s\n' "$psk" > "$pskfile"
        args+=(preshared-key "$pskfile")
    fi
    args+=(allowed-ips "$ips")
    [[ $ka != off ]] && args+=(persistent-keepalive "$ka")
    if ! "$AWG" "${args[@]}"; then
        [[ -n ${pskfile:-} ]] && rm -f "$pskfile"
        cat "$before" > "$CONF"
        die "the running interface refused the peer; $CONF is as it was"
    fi
    [[ -n ${pskfile:-} ]] && rm -f "$pskfile"

    [[ $(grep -cF -- "$pub" "$CONF") == 1 ]] || die "restored, but the key is not in $CONF exactly once — look at it"
    echo "ok: $ip (${pub:0:8}…) restored from $snap; the device reconnects on its next handshake"
}

# ── the list ────────────────────────────────────────────────────────────

LIST="" APPLY=0 ALLOW_LIVE=0
while (( $# )); do
    case $1 in
        --restore)    [[ $# -eq 2 ]] || die "usage: peer-remove.sh --restore <address>"; restore "$2"; exit 0 ;;
        --apply)      APPLY=1 ;;
        --allow-live) ALLOW_LIVE=1 ;;
        -*)           die "unknown option $1" ;;
        *)            [[ -z $LIST ]] || die "one list only"; LIST=$1 ;;
    esac
    shift
done
[[ -n $LIST ]] || die "usage: peer-remove.sh <list> [--apply] [--allow-live] | --restore <address>"
[[ -r $LIST ]] || die "cannot read $LIST"
[[ -f $CONF ]] || die "no $CONF"

problems=0
problem() { echo "  ✗ $*"; problems=$(( problems + 1 )); }

declare -A seen
plan=()       # "ip pub hs allowed-ips"
nr=0
while IFS= read -r raw || [[ -n $raw ]]; do
    nr=$(( nr + 1 ))
    read -r ip pfx _ <<<"$raw"
    [[ -z ${ip:-} || $ip == \#* ]] && continue
    where="строка $nr ($ip)"
    if ! client_ip "$ip"; then problem "$where: не клиентский адрес"; continue; fi
    if [[ -z ${pfx:-} || ${#pfx} -lt 8 || ! $pfx =~ ^[A-Za-z0-9+/=]+$ ]]; then
        problem "$where: нужно начало ключа, 8 символов или больше"; continue
    fi
    if [[ -n ${seen[$ip]:-} ]]; then problem "$where: адрес в списке дважды"; continue; fi
    seen[$ip]=1

    found=$(peers_with "$ip")
    n=$(grep -c . <<<"$found")
    if (( n == 0 )); then problem "$where: на $IFACE нет пира с этим адресом"; continue; fi
    if (( n > 1 )); then problem "$where: этот адрес у $n пиров — разобрать руками"; continue; fi
    read -r pub _ _ ips hs _ <<<"$found"
    if [[ $pub != "$pfx"* ]]; then problem "$where: ключ здесь начинается с ${pub:0:8}, а не с $pfx"; continue; fi
    if (( hs > 0 && now - hs < LIVE_S && ! ALLOW_LIVE )); then
        problem "$where: на связи прямо сейчас (handshake $(( now - hs )) с назад) — удалить только с --allow-live"
        continue
    fi
    plan+=("$ip $pub $hs $ips")
done < "$LIST"

if (( problems )); then
    echo "STOP: в списке $problems проблем(ы), ничего не изменено" >&2
    exit 1
fi
(( ${#plan[@]} )) || die "в списке нет ни одного пира"

echo "К удалению с $IFACE: ${#plan[@]}"
for p in "${plan[@]}"; do
    read -r ip pub hs ips <<<"$p"
    live=""
    (( hs > 0 && now - hs < LIVE_S )) && live="   ← НА СВЯЗИ СЕЙЧАС"
    extra=""
    [[ $ips != "$ip/32" ]] && extra="  (адреса: $ips)"
    printf '  %-15s %s…  связь: %s%s%s\n' "$ip" "${pub:0:8}" "$(ago "$hs")" "$extra" "$live"
done

if (( ! APPLY )); then
    echo "Это сухой прогон, ничего не изменено. Удалить: тот же вызов с --apply"
    exit 0
fi

# ── apply ───────────────────────────────────────────────────────────────

snap="$SNAP_ROOT/peer-audit-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$snap" || die "cannot create $snap"
cp -p "$CONF" "$snap/$IFACE.conf" || die "cannot copy $CONF"
"$AWG" show "$IFACE" dump > "$snap/dump" || die "cannot dump $IFACE"
for p in "${plan[@]}"; do read -r ip pub _ <<<"$p"; echo "$ip ${pub:0:8}"; done > "$snap/plan"
if ! cmp -s "$CONF" "$snap/$IFACE.conf" || [[ $(awk 'NR > 1' "$snap/dump" | wc -l) -eq 0 ]]; then
    die "the snapshot in $snap does not look complete"
fi
echo "Снимок: $snap"

mapfile -t old_baks < <(ls "$CONF".bak-* 2>/dev/null)
peers_before=$(dump | wc -l)
done_n=0
for p in "${plan[@]}"; do
    read -r ip pub _ <<<"$p"
    if out=$("$DEL" "$pub" 2>&1); then
        echo "  $ip: $out"
        done_n=$(( done_n + 1 ))
    else
        echo "  $ip: $out"
        echo "STOP: удалено $done_n из ${#plan[@]}, на $ip $DEL отказал. Остальные не тронуты." >&2
        echo "Снимок для отката: $snap; копии конфига от $DEL оставлены." >&2
        exit 1
    fi
done

# Each removed key must be gone from both places.
gone=1
for p in "${plan[@]}"; do
    read -r ip pub _ <<<"$p"
    if grep -qF -- "$pub" "$CONF" || dump | awk '{ print $1 }' | grep -qxF -- "$pub"; then
        echo "  ✗ $ip: ключ всё ещё на месте" >&2; gone=0
    fi
done
(( gone )) || die "не все удалены — копии конфига оставлены, снимок $snap"

shredded=0
for f in "$CONF".bak-*; do
    [[ -e $f ]] || continue
    printf '%s\n' "${old_baks[@]}" | grep -qxF -- "$f" && continue
    if command -v shred >/dev/null; then shred -u "$f"; else rm -f "$f"; fi
    shredded=$(( shredded + 1 ))
done

echo "Готово: удалено ${#plan[@]}; пиров на $IFACE было $peers_before, стало $(dump | wc -l)."
echo "Копий конфига от этой ночи уничтожено: $shredded (старые не тронуты). Снимок: $snap"
echo "Дальше: tools/awg-conf-check.sh — файл против работающего $IFACE."
