#!/usr/bin/env bash
#
# Tests infrastructure/link/sovrn-link-hop against a fake awg, systemctl and
# logger (no root, nothing touched outside a temporary directory).
#
#   bash tests/infrastructure/test_link_hop.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
HOP="$ROOT/infrastructure/link/sovrn-link-hop"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin"

# awg: listen port and last handshake live in files.
cat > "$WORK/bin/awg" <<'FAKE'
#!/usr/bin/env bash
d="$FAKE_DIR"
case "$*" in
    "show awg1 listen-port")       [[ -f $d/up ]] || exit 1; cat "$d/port" ;;
    "show awg1 latest-handshakes") printf 'PEER=\t%s\n' "$(cat "$d/hs")" ;;
    "set awg1 listen-port "*)      echo "$4" > "$d/port"; echo "$4" >> "$d/set" ;;
    *) echo "fake awg: $*" >&2; exit 99 ;;
esac
FAKE
cat > "$WORK/bin/systemctl" <<'FAKE'
#!/usr/bin/env bash
cat "$FAKE_DIR/active_since" 2>/dev/null || echo "n/a"
FAKE
printf '#!/bin/sh\nexit 0\n' > "$WORK/bin/logger"
chmod 755 "$WORK/bin/"*

pass=0; fail=0
ok()  { echo "ok   $1"; pass=$((pass + 1)); }
bad() { echo "FAIL $1"; fail=$((fail + 1)); }

NOW=1800000000
setup() {   # setup <port> <handshake epoch or 0> [state lines...]
    rm -rf "$WORK/d"; mkdir -p "$WORK/d"
    export FAKE_DIR="$WORK/d"
    touch "$WORK/d/up"
    echo "$1" > "$WORK/d/port"; echo "$2" > "$WORK/d/hs"
    printf 'IF=awg1\nPORTS="51851 51861 51871"\nSTALE=180\n' > "$WORK/d/conf"
    shift 2
    if (( $# )); then printf '%s\n' "$@" > "$WORK/d/state"; fi
}
run() { PATH="$WORK/bin:/usr/bin:/bin" SOVRN_NOW=$NOW SOVRN_LINK_HOP_CONF="$WORK/d/conf" \
        SOVRN_LINK_HOP_STATE="$WORK/d/state" bash "$HOP" "$@" >/dev/null 2>&1; }
port() { cat "$WORK/d/port"; }
st()   { sed -n "s/^$1=//p" "$WORK/d/state" 2>/dev/null; }

setup 51851 $((NOW - 30));  run check
if [[ $(port) == 51851 && ! -f $WORK/d/state ]]; then ok "fresh link: nothing changes"; else bad "fresh link: nothing changes"; fi

setup 51851 $((NOW - 600)); run check
if [[ $(port) == 51861 && $(st hops) == 1 && $(st from) == 51851 && $(st last_hop) == "$NOW" ]]; then ok "silent link: next port, state written"; else bad "silent link: next port, state written"; fi

setup 51851 0; run check
if [[ $(port) == 51861 ]]; then ok "never shook hands: hops too"; else bad "never shook hands: hops too"; fi

setup 51861 $((NOW - 600)) port=51861 from=51851 "last_hop=$((NOW - 100))" hops=1; run check
if [[ $(port) == 51861 && $(st hops) == 1 ]]; then ok "a recent hop gets time to work"; else bad "a recent hop gets time to work"; fi

setup 51861 $((NOW - 600)) port=51861 from=51851 "last_hop=$((NOW - 300))" hops=1; run check
if [[ $(port) == 51871 && $(st hops) == 2 ]]; then ok "still silent later: next port again"; else bad "still silent later: next port again"; fi

setup 51871 $((NOW - 600)); run check
if [[ $(port) == 51851 ]]; then ok "the last port wraps to the first"; else bad "the last port wraps to the first"; fi

setup 40000 $((NOW - 600)); run check
if [[ $(port) == 51851 ]]; then ok "a port outside the list goes to the first"; else bad "a port outside the list goes to the first"; fi

setup 51851 $((NOW - 600)); date -u -d "@$((NOW - 60))" '+%a %Y-%m-%d %H:%M:%S UTC' > "$WORK/d/active_since"; run check
if [[ $(port) == 51851 ]]; then ok "a link just (re)started gets time"; else bad "a link just (re)started gets time"; fi

setup 51851 $((NOW - 600)); rm "$WORK/d/up"; run check
if [[ ! -f $WORK/d/set ]]; then ok "interface down: nothing done"; else bad "interface down: nothing done"; fi

setup 51851 $((NOW - 30)) port=51871 from=51861 last_hop=1 hops=2; run apply awg1
if [[ $(port) == 51871 ]]; then ok "apply restores the hopped port"; else bad "apply restores the hopped port"; fi

setup 51851 $((NOW - 30)) port=40000 hops=1; run apply awg1
if [[ $(port) == 51851 ]]; then ok "apply ignores a port outside the list"; else bad "apply ignores a port outside the list"; fi

setup 51851 $((NOW - 30)); if run apply awg1; then ok "apply without state succeeds and changes nothing"; else bad "apply without state succeeds and changes nothing"; fi
[[ $(port) == 51851 ]] || bad "apply without state changed the port"

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
