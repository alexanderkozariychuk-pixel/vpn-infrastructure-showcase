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
# ping: the summary for each address comes from a file, as ping prints it.
cat > "$WORK/bin/ping" <<'FAKE'
#!/usr/bin/env bash
host="${@: -1}"
f="$FAKE_DIR/ping_$host"
[[ -f $f ]] || { echo "10 packets transmitted, 0 received, 100% packet loss, time 9000ms"; exit 1; }
cat "$f"
FAKE
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
if [[ $(port) == 51861 && $(st hops) == 1 && $(st from) == 51851 && $(st last_hop) == "$NOW" && $(st why) == silent ]]; then ok "silent link: next port, state written"; else bad "silent link: next port, state written"; fi

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

# ── slow, not silent (2026-10-29) ──
pings() {   # pings <inside avg> <inside loss %> <outside avg> <outside loss %>; "-" = no answer
    printf 'PROBE_INNER=10.77.77.9\nPROBE_OUTER=203.0.113.5\nSLOW_MS=20\nSLOW_LOSS=5\nSLOW_RUNS=3\nSLOW_COOLDOWN=1800\n' >> "$WORK/d/conf"
    one() { rm -f "$WORK/d/ping_$1"; [[ $2 == - ]] && return
            printf '10 packets transmitted, %s received, %s%% packet loss, time 1800ms\nrtt min/avg/max/mdev = 40.000/%s.500/90.000/5.000 ms\n' \
                   $((10 - $3 / 10)) "$3" "$2" > "$WORK/d/ping_$1"; }
    one 10.77.77.9 "$1" "$2"; one 203.0.113.5 "$3" "$4"
}
fresh=$((NOW - 30))

setup 51851 $fresh; pings 50 0 48 0; run check
if [[ $(port) == 51851 && ! -f $WORK/d/state ]]; then ok "inside as fast as outside: nothing changes, nothing written"; else bad "inside as fast as outside: nothing changes, nothing written"; fi

setup 51851 $fresh; pings 88 0 48 0; run check; run check
if [[ $(port) == 51851 && $(st slow) == 2 ]]; then ok "slow twice: counted, not moved yet"; else bad "slow twice: counted, not moved yet"; fi
run check
if [[ $(port) == 51861 && $(st why) == slow && $(st slow) == 0 && $(st hops) == 1 && $(st from) == 51851 ]]; then ok "slow three checks in a row: next port"; else bad "slow three checks in a row: next port"; fi

setup 51851 $fresh; pings 88 0 48 0; run check; run check; pings 50 0 48 0; run check
if [[ $(port) == 51851 && $(st slow) == 0 ]]; then ok "one good check resets the count"; else bad "one good check resets the count"; fi

setup 51851 $fresh; pings 50 20 48 0; run check; run check; run check
if [[ $(port) == 51861 && $(st why) == slow ]]; then ok "losing inside, not outside, counts as slow"; else bad "losing inside, not outside, counts as slow"; fi

setup 51851 $fresh; pings - 100 48 0; run check; run check; run check
if [[ $(port) == 51861 ]]; then ok "inside silent to ping, outside fine: slow"; else bad "inside silent to ping, outside fine: slow"; fi

setup 51851 $fresh; pings 88 0 - 100; run check; run check; run check
if [[ $(port) == 51851 && ! -f $WORK/d/state ]]; then ok "outside does not answer: no judgement"; else bad "outside does not answer: no judgement"; fi

setup 51861 $fresh port=51861 from=51851 "last_hop=$((NOW - 900))" hops=1 why=slow slow=2; pings 88 0 48 0; run check
if [[ $(port) == 51861 && $(st slow) == 3 ]]; then ok "a slow hop 15 min ago: no churning, still counted"; else bad "a slow hop 15 min ago: no churning, still counted"; fi

setup 51861 $fresh port=51861 from=51851 "last_hop=$((NOW - 2000))" hops=1 why=slow slow=2; pings 88 0 48 0; run check
if [[ $(port) == 51871 && $(st hops) == 2 ]]; then ok "after the cooldown a slow link moves again"; else bad "after the cooldown a slow link moves again"; fi

setup 51861 $fresh port=51861 from=51851 "last_hop=$((NOW - 120))" hops=1 why=silent slow=2; pings 88 0 48 0; run check
if [[ $(port) == 51861 ]]; then ok "right after a silent hop: wait before judging speed"; else bad "right after a silent hop: wait before judging speed"; fi

setup 51851 $fresh; pings 88 0 48 0; sed -i '/^PROBE_/d' "$WORK/d/conf"; run check; run check; run check
if [[ $(port) == 51851 && ! -f $WORK/d/state ]]; then ok "without probe addresses: the old behaviour"; else bad "without probe addresses: the old behaviour"; fi

setup 51851 $fresh port=51871 from=51861 last_hop=1 hops=2 why=slow slow=0; run apply awg1
if [[ $(port) == 51871 ]]; then ok "apply reads the new state format"; else bad "apply reads the new state format"; fi

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
