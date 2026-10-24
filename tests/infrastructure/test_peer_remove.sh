#!/usr/bin/env bash
#
# Tests for tools/peer-remove.sh, against the fake `awg`, the real
# pwa-del-peer and a config file in a temp directory. No root, no network.
#
#   bash tests/infrastructure/test_peer_remove.sh
#
# The fixture is shaped like entry A: portal peers with "### name" headers, a
# hand-made peer with none, and client18's block holding a headerless
# PresharedKey/AllowedIPs pair (docs/entry-spec.md, "Found on A").

# ok() always succeeds, so `check && ok || bad` is if-then-else here.
# shellcheck disable=SC2015

set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/bin" "$work/etc" "$work/root"
cp "$here/fake-awg" "$work/bin/awg"
sed "s#/etc/amnezia/amneziawg/#$work/etc/#" "$repo/infrastructure/wrappers/pwa-del-peer" > "$work/bin/pwa-del-peer"
chmod +x "$work/bin/awg" "$work/bin/pwa-del-peer"

export AWG_STATE="$work/awg.state"
export CONF="$work/etc/awg0.conf" SNAP_ROOT="$work/root"
# peer-remove.sh resets PATH to the system's, as it should on the node; the
# wrapper it calls finds `awg` by name, so here it is called through a shim
# that puts the fake first.
# shellcheck disable=SC2016  # $PATH and "$@" are for the shim, not for here
printf '#!/usr/bin/env bash\nPATH="%s:$PATH" exec "%s" "$@"\n' "$work/bin" "$work/bin/pwa-del-peer" > "$work/bin/del"
chmod +x "$work/bin/del"
export AWG="$work/bin/awg" DEL="$work/bin/del"
SCRIPT="$repo/tools/peer-remove.sh"
CHECK="$repo/tools/awg-conf-check.sh"

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "  ok   $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1"; }

key() { head -c 32 /dev/urandom | base64; }
now=$(date +%s)

# Keys are fixed per run so the list can name their beginnings.
K42=$(key); P42=$(key)        # portal, .42
K48=$(key); P48=$(key)        # client18, .48 — the stray pair sits in its block
STRAY=$(key)                  # the stray PresharedKey (matches no peer)
K49=$(key); P49=$(key)        # .49
K20=$(key); P20=$(key)        # hand-made, .20, no header, keepalive 25
K89=$(key); P89=$(key)        # trial, 10.88.89.10
KL=$(key);  PL=$(key)         # .60, connected right now

reset() {
    cat > "$CONF" <<EOF
[Interface]
PrivateKey = $(key)
Address = 10.88.88.1/24
ListenPort = 8443


### alice-phone
[Peer]
PublicKey = $K42
PresharedKey = $P42
AllowedIPs = 10.88.88.42/32


### client18
[Peer]
PublicKey = $K48
PresharedKey = $P48
AllowedIPs = 10.88.88.48/32

PresharedKey = $STRAY
AllowedIPs = 10.88.88.49/32


### client19
[Peer]
PublicKey = $K49
PresharedKey = $P49
AllowedIPs = 10.88.88.49/32

[Peer]
PublicKey = $K20
PresharedKey = $P20
AllowedIPs = 10.88.88.20/32
PersistentKeepalive = 25


### bob-trial
[Peer]
PublicKey = $K89
PresharedKey = $P89
AllowedIPs = 10.88.89.10/32


### carol-laptop
[Peer]
PublicKey = $KL
PresharedKey = $PL
AllowedIPs = 10.88.88.60/32
EOF
    cat > "$AWG_STATE" <<EOF
$K42 10.88.88.42/32 $P42 $(( now - 86400 ))
$K48 10.88.88.48/32 $P48 $(( now - 40 * 86400 ))
$K49 10.88.88.49/32 $P49 $(( now - 3600 ))
$K20 10.88.88.20/32 $P20 0 25
$K89 10.88.89.10/32 $P89 $(( now - 7200 ))
$KL 10.88.88.60/32 $PL $(( now - 60 ))
EOF
    rm -rf "$SNAP_ROOT"/peer-audit-* "$CONF".bak-*
}

list() { printf '%s\n' "$@" > "$work/list.txt"; }
run() { bash "$SCRIPT" "$@" 2>&1; }
state_sum() { sha256sum "$CONF" "$AWG_STATE" | awk '{ print $1 }' | paste -sd,; }
has_conf() { grep -qF -- "$1" "$CONF"; }
has_run()  { awk '{ print $1 }' "$AWG_STATE" | grep -qxF -- "$1"; }
conf_check() { "$AWG" show awg0 dump > "$work/dump"; F="$CONF" DUMP="$work/dump" bash "$CHECK" >/dev/null 2>&1; }

# expect <name> <exit code> <substring> -- args...
expect() {
    local name="$1" code="$2" text="$3"; shift 4
    local out rc
    out="$(run "$@")"; rc=$?
    if [[ $rc -eq $code && $out == *"$text"* ]]; then ok "$name"; else bad "$name (exit $rc, output: $out)"; fi
}

echo "the list is checked before anything changes"
reset; s0=$(state_sum)
list "10.88.88.20 ${K20:0:8} hand-made, moved" "" "# a comment" "10.88.89.10 ${K89:0:10} trial ended"
expect "a good list, dry run" 0 "К удалению с awg0: 2" -- "$work/list.txt"
[[ $(state_sum) == "$s0" ]] && ok "  ...changes nothing" || bad "  ...changes nothing"
compgen -G "$SNAP_ROOT/peer-audit-*" >/dev/null && bad "  ...and makes no snapshot" || ok "  ...and makes no snapshot"
out=$(run "$work/list.txt")
[[ $out == *"10.88.88.20"*"никогда"* ]] && ok "  ...shows when each was last seen" || bad "  ...shows when each was last seen ($out)"
[[ $out != *"$K20"* && $out != *"$P20"* ]] && ok "  ...and never a whole key" || bad "  ...and never a whole key"

list "10.88.88.20 ${K42:0:8}"
expect "a key that does not match the address" 1 "ключ здесь начинается с ${K20:0:8}" -- "$work/list.txt"
list "10.88.88.77 ${K42:0:8}"
expect "an address not on the node" 1 "нет пира с этим адресом" -- "$work/list.txt"
list "10.77.77.1 ${K42:0:8}"
expect "the link to the exit" 1 "не клиентский адрес" -- "$work/list.txt"
list "10.88.88.420 ${K42:0:8}"
expect "not an address" 1 "не клиентский адрес" -- "$work/list.txt"
list "10.88.88.42 ${K42:0:7}"
expect "seven characters of key" 1 "8 символов" -- "$work/list.txt"
list "10.88.88.42"
expect "no key at all" 1 "8 символов" -- "$work/list.txt"
list "10.88.88.42 ${K42:0:8}" "10.88.88.42 ${K42:0:8}"
expect "an address twice" 1 "дважды" -- "$work/list.txt"
list "# nothing" ""
expect "an empty list" 1 "ни одного пира" -- "$work/list.txt"

reset; s0=$(state_sum)
list "10.88.88.42 ${K42:0:8}" "10.88.88.77 ${K42:0:8}"
expect "one bad line among good ones, --apply" 1 "ничего не изменено" -- "$work/list.txt" --apply
[[ $(state_sum) == "$s0" ]] && ok "  ...and nothing was removed" || bad "  ...and nothing was removed"
compgen -G "$SNAP_ROOT/peer-audit-*" >/dev/null && bad "  ...nor a snapshot made" || ok "  ...nor a snapshot made"

reset
echo "$(key) 10.88.88.42/32 $(key) 0" >> "$AWG_STATE"
list "10.88.88.42 ${K42:0:8}"
expect "an address carried by two peers" 1 "у 2 пиров" -- "$work/list.txt"

echo "someone connected right now"
reset; s0=$(state_sum)
list "10.88.88.60 ${KL:0:8}"
expect "refused without --allow-live" 1 "на связи прямо сейчас" -- "$work/list.txt" --apply
[[ $(state_sum) == "$s0" ]] && ok "  ...and still there" || bad "  ...and still there"
expect "shown with --allow-live" 0 "НА СВЯЗИ СЕЙЧАС" -- "$work/list.txt" --allow-live
expect "removed with --allow-live --apply" 0 "удалено 1" -- "$work/list.txt" --allow-live --apply
has_run "$KL" && bad "  ...and gone" || ok "  ...and gone"
reset
# Keys are base64 and may hold "/": rewrite the line with awk, not sed.
awk -v k="$KL" -v t="$(( now - 200 ))" '$1 == k { $4 = t } { print }' "$AWG_STATE" > "$AWG_STATE.new" && mv "$AWG_STATE.new" "$AWG_STATE"
list "10.88.88.60 ${KL:0:8}"
expect "a handshake 200 s ago is not 'now'" 0 "К удалению" -- "$work/list.txt"

echo "--apply"
reset
touch "$CONF.bak-20260101-000000"
before_conf=$(cat "$CONF")
list "10.88.88.20 ${K20:0:8}" "10.88.88.48 ${K48:0:8} client18" "10.88.89.10 ${K89:0:8}"
conf_check && bad "the stray pair: the check sees it before" || ok "the stray pair: the check sees it before"
expect "removes the list" 0 "Готово: удалено 3" -- "$work/list.txt" --apply
for k in "$K20" "$K48" "$K89"; do
    { has_conf "$k" || has_run "$k"; } && bad "  ...${k:0:8} gone from file and runtime" || ok "  ...${k:0:8} gone from file and runtime"
done
for k in "$K42" "$K49" "$KL"; do
    { has_conf "$k" && has_run "$k"; } && ok "  ...${k:0:8} untouched" || bad "  ...${k:0:8} untouched"
done
grep -qF -- "$STRAY" "$CONF" && bad "  ...the stray pair went with client18" || ok "  ...the stray pair went with client18"
[[ $(grep -c '^AllowedIPs = 10.88.88.49/32' "$CONF") == 1 ]] && ok "  ...client19 keeps .49" || bad "  ...client19 keeps .49"
conf_check && ok "  ...and file == running afterwards" || bad "  ...and file == running afterwards"
snaps=("$SNAP_ROOT"/peer-audit-*); snap=${snaps[0]}
[[ -n $snap && $(stat -c %a "$snap") == 700 ]] && ok "  ...snapshot directory, mode 700" || bad "  ...snapshot directory, mode 700"
[[ $(cat "$snap/awg0.conf" 2>/dev/null) == "$before_conf" ]] && ok "  ...snapshot holds the config as it was" || bad "  ...snapshot holds the config as it was"
grep -qF -- "$K48" "$snap/dump" 2>/dev/null && ok "  ...and the running peers" || bad "  ...and the running peers"
[[ $(cat "$snap/plan" 2>/dev/null) == "10.88.88.20 ${K20:0:8}"$'\n'"10.88.88.48 ${K48:0:8}"$'\n'"10.88.89.10 ${K89:0:8}" ]] \
    && ok "  ...and the plan, keys shortened" || bad "  ...and the plan, keys shortened"
baks=("$CONF".bak-*)
[[ ${#baks[@]} == 1 && ${baks[0]} == "$CONF.bak-20260101-000000" ]] \
    && ok "  ...tonight's copies shredded, the old one kept" || bad "  ...tonight's copies shredded, the old one kept (${#baks[@]})"

echo "a refusal half way"
reset
cat > "$work/bin/del-second-fails" <<EOF
#!/usr/bin/env bash
[[ "\$1" == "$K89" ]] && { echo "error: refused" >&2; exit 1; }
exec "$work/bin/del" "\$@"
EOF
chmod +x "$work/bin/del-second-fails"
list "10.88.88.20 ${K20:0:8}" "10.88.89.10 ${K89:0:8}" "10.88.88.42 ${K42:0:8}"
out=$(DEL="$work/bin/del-second-fails" bash "$SCRIPT" "$work/list.txt" --apply 2>&1); rc=$?
[[ $rc == 1 && $out == *"удалено 1 из 3"* ]] && ok "stops at the refusal" || bad "stops at the refusal (exit $rc: $out)"
has_conf "$K20" && bad "  ...the first is gone" || ok "  ...the first is gone"
{ has_conf "$K89" && has_conf "$K42" && has_run "$K42"; } && ok "  ...the rest untouched" || bad "  ...the rest untouched"
compgen -G "$CONF.bak-*" >/dev/null && ok "  ...copies of the config kept" || bad "  ...copies of the config kept"

echo "a wrapper that says ok and leaves the peer running"
reset
cat > "$work/bin/del-file-only" <<EOF
#!/usr/bin/env bash
cp "\$AWG_STATE" "$work/keep"
"$work/bin/del" "\$@" || exit 1
cp "$work/keep" "\$AWG_STATE"
EOF
chmod +x "$work/bin/del-file-only"
list "10.88.88.42 ${K42:0:8}"
out=$(DEL="$work/bin/del-file-only" bash "$SCRIPT" "$work/list.txt" --apply 2>&1); rc=$?
[[ $rc == 1 && $out == *"всё ещё на месте"* ]] && ok "is caught" || bad "is caught (exit $rc: $out)"
compgen -G "$CONF.bak-*" >/dev/null && ok "  ...and the copies are kept" || bad "  ...and the copies are kept"

echo "--restore"
reset
list "10.88.88.20 ${K20:0:8}" "10.88.88.48 ${K48:0:8}" "10.88.88.42 ${K42:0:8}"
run "$work/list.txt" --apply >/dev/null
expect "a portal peer" 0 "ok: 10.88.88.42" -- --restore 10.88.88.42
grep -qF "$K42 10.88.88.42/32 $P42" "$AWG_STATE" && ok "  ...running, with its own preshared key" || bad "  ...running, with its own preshared key"
[[ $(grep -cF -- "$K42" "$CONF") == 1 ]] && ok "  ...in the file once" || bad "  ...in the file once"
grep -B1 -F -- "[Peer]" "$CONF" | grep -q '^### alice-phone' && ok "  ...under its name" || bad "  ...under its name"
expect "the hand-made one" 0 "ok: 10.88.88.20" -- --restore 10.88.88.20
grep -qF "$K20 10.88.88.20/32 $P20 0 25" "$AWG_STATE" && ok "  ...with its keepalive" || bad "  ...with its keepalive"
awk -v k="$K20" 'index($0, k) { getline; getline; getline; print; exit }' "$CONF" | grep -q '^PersistentKeepalive = 25' \
    && ok "  ...in the file too" || bad "  ...in the file too"
grep -B2 -F -- "$K20" "$CONF" | grep -q '^###' && bad "  ...and no name it never had" || ok "  ...and no name it never had"
expect "client18" 0 "ok: 10.88.88.48" -- --restore 10.88.88.48
grep -qF -- "$STRAY" "$CONF" && bad "  ...without the stray pair" || ok "  ...without the stray pair"
conf_check && ok "  ...file == running after all three" || bad "  ...file == running after all three"
expect "already there" 1 "already on awg0" -- --restore 10.88.88.42
reset
list "10.88.88.42 ${K42:0:8}"
run "$work/list.txt" --apply >/dev/null
printf '\n[Peer]\nPublicKey = %s\nAllowedIPs = 10.88.88.99/32\n' "$K42" >> "$CONF"
expect "its key back in the file by hand" 1 "already in" -- --restore 10.88.88.42
expect "not in the snapshot" 1 "has 0 peers" -- --restore 10.88.88.77
expect "not a client address" 1 "not a client address" -- --restore 10.77.77.1

reset
list "10.88.88.42 ${K42:0:8}"
run "$work/list.txt" --apply >/dev/null
echo "$(key) 10.88.88.42/32 $(key) 0" >> "$AWG_STATE"
expect "its address taken meanwhile" 1 "in use by another peer" -- --restore 10.88.88.42
sed -i '$d' "$AWG_STATE"
s0=$(sha256sum < "$CONF")
out=$(AWG_FAIL_SET=1 bash "$SCRIPT" --restore 10.88.88.42 2>&1); rc=$?
[[ $rc == 1 && $(sha256sum < "$CONF") == "$s0" ]] && ok "runtime refuses: the file is put back" || bad "runtime refuses: the file is put back (exit $rc: $out)"
rm -rf "$SNAP_ROOT"/peer-audit-*
expect "no snapshot at all" 1 "no snapshot found" -- --restore 10.88.88.42

echo "the list from peer_reconcile"
reset
"$AWG" show awg0 dump | awk 'NR > 1 { print $1, $4, $5 }' > "$work/node.txt"
printf '%s|10.88.88.42|t|paid|alice|phone\n%s|10.88.89.10|f|trial|bob|tablet\n' "$K42" "$K89" > "$work/db.txt"
printf '%s|hand-made\n' "$K20" > "$work/labels.txt"
python3 "$repo/tools/peer_reconcile.py" "$work/node.txt" "$work/db.txt" "$work/labels.txt" "$work/cand.txt" > /dev/null \
    && ok "peer_reconcile writes candidates" || bad "peer_reconcile writes candidates"
grep -q '^# 10.88.88.20 ' "$work/cand.txt" && grep -q '^# 10.88.89.10 ' "$work/cand.txt" \
    && ok "  ...the hand-made peer and the ended trial among them" || bad "  ...the hand-made peer and the ended trial among them"
# Taken as written, every line is a comment: nothing to remove.
expect "  ...untouched, the file removes nothing" 1 "ни одного пира" -- "$work/cand.txt"
sed -e 's/^# \(10\.88\.88\.20 \)/\1/' -e 's/^# \(10\.88\.89\.10 \)/\1/' "$work/cand.txt" > "$work/picked.txt"
expect "  ...two uncommented, peer-remove takes them as they are" 0 "К удалению с awg0: 2" -- "$work/picked.txt"

echo
echo "$pass passed, $fail failed"
(( fail == 0 ))
