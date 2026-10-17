#!/bin/bash
#
# One-off, 2026-10-17: client isolation on an existing entry (A by hand; B,
# whose awg0.conf Ansible writes only once). Clients must not reach each
# other: docs/entry-spec.md, "Client isolation". Run on the node:
#
#   ssh sov-entry 'sudo -n true && sudo bash -s -- check'    < tools/once/2026-10-17-client-isolation.sh
#   ssh sov-entry 'sudo -n true && sudo bash -s -- apply'    < tools/once/2026-10-17-client-isolation.sh
#   ssh sov-entry 'sudo -n true && sudo bash -s -- rollback /root/sov-backup/isolation-<stamp>' < ...
#
# check     read-only: what apply would add to the file and to FORWARD.
# apply     backup (file + FORWARD as found) under /root/sov-backup/, then the
#           missing PostUp/PostDown lines into [Interface] and the missing
#           rules into the running FORWARD. awg0 is never restarted; no peer
#           is touched. Aborts on any surprise, before writing.
# rollback  the file back from the backup (cat >, keeps owner and mode) and
#           only the rules apply added taken out of FORWARD.
#
# Prints no keys: the file is only ever compared and counted.
set -uo pipefail

F=/etc/amnezia/amneziawg/awg0.conf
IFACE=awg0
NETS=10.88.88.0/23
BACKUP_ROOT=/root/sov-backup

# Wanted lines, in the order they go into the file (as the role's template).
WANT=(
    "PostUp = iptables -I FORWARD 1 -i %i -o %i -j DROP"
    "PostUp = iptables -I FORWARD 1 -i %i -d $NETS -j DROP"
    "PostDown = iptables -D FORWARD -i %i -d $NETS -j DROP"
    "PostDown = iptables -D FORWARD -i %i -o %i -j DROP"
)
# Running rules, inserted in this order at position 1: the last one ends first.
RULE_IF=(-i "$IFACE" -o "$IFACE" -j DROP)
RULE_DST=(-i "$IFACE" -d "$NETS" -j DROP)

die() { echo "STOP: $*"; exit 1; }
has_line() { grep -qxF -- "$1" "$F"; }

# Lines of WANT missing from the file, and the line number of the first
# PostUp, which they go in front of. That line must sit in [Interface].
plan_file() {
    MISSING=()
    local w
    for w in "${WANT[@]}"; do has_line "$w" || MISSING+=("$w"); done
    FIRST_POSTUP=$(grep -n -m1 '^PostUp = ' "$F" | cut -d: -f1)
    FIRST_PEER=$(grep -n -m1 '^\[Peer\]' "$F" | cut -d: -f1)
    [[ -n $FIRST_POSTUP ]] || die "no PostUp line in $F"
    [[ -z $FIRST_PEER || $FIRST_POSTUP -lt $FIRST_PEER ]] || die "first PostUp is not in [Interface]"
    [[ $(grep -c '^\[Interface\]' "$F") -eq 1 ]] || die "want exactly one [Interface] in $F"
}

show_state() {
    echo "== FORWARD (head)"
    iptables -L FORWARD -nvx --line-numbers | awk 'NR<=2 || $4=="DROP" || $4=="SOVRN-TRIAL" || ($4=="ACCEPT" && $7=="'"$IFACE"'")'
    echo "== isolation lines in $F"
    grep -nE "^Post(Up|Down) = iptables -[ID] FORWARD .*-j DROP$" "$F" || echo "(none)"
    echo "== peers in file / running: $(grep -c '^\[Peer\]' "$F") / $(awg show "$IFACE" peers | wc -l)"
}

check() {
    [[ -f $F ]] || die "$F not found"
    plan_file
    show_state
    echo "== apply would add to the file, before line $FIRST_POSTUP:"
    if (( ${#MISSING[@]} )); then printf '  %s\n' "${MISSING[@]}"; else echo "  (nothing)"; fi
    echo "== apply would add to FORWARD:"
    local n=0
    iptables -C FORWARD "${RULE_IF[@]}" 2>/dev/null || { echo "  -I FORWARD 1 ${RULE_IF[*]}"; n=1; }
    iptables -C FORWARD "${RULE_DST[@]}" 2>/dev/null || { echo "  -I FORWARD 1 ${RULE_DST[*]}"; n=1; }
    (( n )) || echo "  (nothing)"
}

apply() {
    [[ -f $F ]] || die "$F not found"
    plan_file
    local stamp dir before tmp i
    stamp=$(date +%Y%m%d-%H%M%S)
    dir="$BACKUP_ROOT/isolation-$stamp"
    umask 077
    mkdir -p "$dir" || die "cannot create $dir"
    chmod 700 "$BACKUP_ROOT" "$dir"
    cp -p "$F" "$dir/awg0.conf" || die "backup failed"
    iptables -S FORWARD > "$dir/forward-before"
    before=$(sha256sum < "$F")

    if (( ${#MISSING[@]} )); then
        tmp=$(mktemp)
        i=0
        while IFS= read -r line || [[ -n $line ]]; do
            i=$((i + 1))
            if (( i == FIRST_POSTUP )); then printf '%s\n' "${MISSING[@]}" >> "$tmp"; fi
            printf '%s\n' "$line" >> "$tmp"
        done < "$F"
        # The result is the original plus exactly the missing lines, nothing else.
        local added removed
        added=$(diff "$F" "$tmp" | grep -c '^>')
        removed=$(diff "$F" "$tmp" | grep -c '^<')
        [[ $added -eq ${#MISSING[@]} && $removed -eq 0 ]] || { rm -f "$tmp"; die "diff is +$added -$removed, want +${#MISSING[@]} -0"; }
        # Written only if nobody (pwa-add-peer, pwa-del-peer) changed it meanwhile.
        [[ $(sha256sum < "$F") == "$before" ]] || { rm -f "$tmp"; die "$F changed while preparing; nothing written"; }
        cat "$tmp" > "$F"
        rm -f "$tmp"
        echo "file: added ${#MISSING[@]} line(s) before line $FIRST_POSTUP"
    else
        echo "file: nothing to add"
    fi

    iptables -C FORWARD "${RULE_IF[@]}" 2>/dev/null  || { iptables -I FORWARD 1 "${RULE_IF[@]}";  echo "FORWARD: added ${RULE_IF[*]}"; }
    iptables -C FORWARD "${RULE_DST[@]}" 2>/dev/null || { iptables -I FORWARD 1 "${RULE_DST[@]}"; echo "FORWARD: added ${RULE_DST[*]}"; }

    echo "backup: $dir"
    echo "== diff backup -> file"
    # diff exits 1 when the files differ; under pipefail that alone would print "(no change)".
    { diff "$dir/awg0.conf" "$F" || true; } | grep '^[<>]' || echo "(no change)"
    show_state
}

rollback() {
    local dir=${1:-}
    [[ -n $dir && -f $dir/awg0.conf && -f $dir/forward-before ]] || die "usage: rollback <backup dir with awg0.conf and forward-before>"
    cat "$dir/awg0.conf" > "$F" || die "restore failed"
    echo "file: restored from $dir"
    # Take a rule out only if it was not there before apply.
    if ! grep -qE -- "^-A FORWARD (-i $IFACE -o $IFACE|-o $IFACE -i $IFACE) -j DROP$" "$dir/forward-before"; then
        while iptables -C FORWARD "${RULE_IF[@]}" 2>/dev/null; do iptables -D FORWARD "${RULE_IF[@]}"; done
        echo "FORWARD: removed ${RULE_IF[*]}"
    fi
    if ! grep -qE -- "^-A FORWARD .*-d ${NETS//./\\.}( .*)? -j DROP$" "$dir/forward-before"; then
        while iptables -C FORWARD "${RULE_DST[@]}" 2>/dev/null; do iptables -D FORWARD "${RULE_DST[@]}"; done
        echo "FORWARD: removed ${RULE_DST[*]}"
    fi
    show_state
}

case "${1:-check}" in
    check)    check ;;
    apply)    apply ;;
    rollback) rollback "${2:-}" ;;
    *)        die "usage: check | apply | rollback <dir>" ;;
esac
true
