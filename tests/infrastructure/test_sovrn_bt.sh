#!/usr/bin/env bash
#
# Tests infrastructure/exit/sovrn-bt against a fake iptables that keeps its
# rules in a file (no root, nothing touched outside a temporary directory).
#
#   bash tests/infrastructure/test_sovrn_bt.sh
#
# What matters on the node: the jump comes first in FORWARD once the link's
# PostUp has inserted its ACCEPTs, `up` twice leaves one jump, `down <if>`
# keeps other links' jumps and the chain, and `down` without an interface
# (what the hand-built exit-2 config called) clears everything.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
BT="$ROOT/infrastructure/exit/sovrn-bt"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"
# Rules as `iptables -S` prints them: "-P/-N/-A <chain> ...", one per line.
cat > "$WORK/bin/iptables" <<'FAKE'
#!/usr/bin/env bash
set -u
db="$STATE"
[[ -f $db ]] || printf -- '-P FORWARD DROP\n' > "$db"
op=$1; ch=$2; shift 2
spec="$*"
has_chain() { [[ $1 == FORWARD ]] || grep -qxF -- "-N $1" "$db"; }
case $op in
    -N) has_chain "$ch" && exit 1; echo "-N $ch" >> "$db" ;;
    -F) has_chain "$ch" || exit 1; grep -vF -- "-A $ch " "$db" > "$db.t"; mv "$db.t" "$db" ;;
    -X) has_chain "$ch" || exit 1
        grep -q -- "-j $ch\$" "$db" && exit 1
        grep -qF -- "-A $ch " "$db" && exit 1
        grep -vxF -- "-N $ch" "$db" > "$db.t"; mv "$db.t" "$db" ;;
    -A) has_chain "$ch" || exit 1; echo "-A $ch $spec" >> "$db" ;;
    -I) has_chain "$ch" || exit 1
        [[ ${1:-} =~ ^[0-9]+$ ]] && { shift; spec="$*"; }
        # first rule of the chain: right after the -P/-N header lines
        awk -v r="-A $ch $spec" 'BEGIN{d=0} !d && /^-A /{print r; d=1} {print} END{if(!d) print r}' "$db" > "$db.t"; mv "$db.t" "$db" ;;
    -C) grep -qxF -- "-A $ch $spec" "$db" ;;
    -D) grep -qxF -- "-A $ch $spec" "$db" || exit 1
        awk -v r="-A $ch $spec" '!d && $0==r {d=1; next} {print}' "$db" > "$db.t"; mv "$db.t" "$db" ;;
    -S) has_chain "$ch" || exit 1; grep -E -- "^-(P|N) $ch\$|^-P $ch |^-A $ch " "$db" ;;
    *) echo "fake iptables: $op not handled" >&2; exit 99 ;;
esac
FAKE
chmod 755 "$WORK/bin/iptables"

pass=0
fail=0
ok()   { echo "ok   $1"; pass=$((pass + 1)); }
bad()  { echo "FAIL $1"; sed 's/^/    /' "$STATE"; fail=$((fail + 1)); }
bt()   { PATH="$WORK/bin:/usr/bin:/bin" STATE="$STATE" sh "$BT" "$@"; }
ipt()  { PATH="$WORK/bin:/usr/bin:/bin" STATE="$STATE" iptables "$@"; }
fwd()  { grep -- '^-A FORWARD ' "$STATE"; }
# the link's PostUp, as roles/exit/templates/link.conf.j2 writes it
postup() {
    ipt -C FORWARD -i "$1" -o eth0 -j ACCEPT 2>/dev/null || ipt -I FORWARD -i "$1" -o eth0 -j ACCEPT
    bt up "$1"
}

export STATE="$WORK/rules"

rm -f "$STATE"; postup awg0
if [[ "$(fwd | head -1)" == "-A FORWARD -i awg0 -j SOVRN_BT" ]] \
   && [[ "$(grep -c -- '^-A SOVRN_BT .* -j DROP$' "$STATE")" -eq 8 ]]; then ok "up: jump first, 8 rules"; else bad "up: jump first, 8 rules"; fi

bt up awg0
if [[ "$(grep -c -- '-j SOVRN_BT$' "$STATE")" -eq 1 ]] \
   && [[ "$(grep -c -- '^-A SOVRN_BT ' "$STATE")" -eq 8 ]]; then ok "up twice: one jump, 8 rules"; else bad "up twice: one jump, 8 rules"; fi

postup awg2
if [[ "$(grep -c -- '-j SOVRN_BT$' "$STATE")" -eq 2 ]] \
   && [[ "$(fwd | head -1)" == "-A FORWARD -i awg2 -j SOVRN_BT" ]]; then ok "second link: own jump, first"; else bad "second link: own jump, first"; fi

bt down awg2
if [[ "$(grep -c -- '-j SOVRN_BT$' "$STATE")" -eq 1 ]] && grep -qxF -- '-N SOVRN_BT' "$STATE" \
   && grep -qxF -- '-A FORWARD -i awg0 -j SOVRN_BT' "$STATE"; then ok "down one link: the other keeps its jump"; else bad "down one link: the other keeps its jump"; fi

bt down awg0
if ! grep -q SOVRN_BT "$STATE"; then ok "down last link: chain gone"; else bad "down last link: chain gone"; fi

rm -f "$STATE"; postup awg0; postup awg2; bt down
if ! grep -q SOVRN_BT "$STATE"; then ok "down without interface: everything gone"; else bad "down without interface: everything gone"; fi

if bt up >/dev/null 2>&1; then bad "up without interface refused"; else ok "up without interface refused"; fi

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
