#!/usr/bin/env bash
#
# Tests for pwa-add-peer and pwa-del-peer, against a fake `awg` and a config
# file in a temp directory. No root and no network needed.
#
#   bash tests/infrastructure/test_wrappers.sh
#
# Each case is checked against what it must protect; see the mutation notes in
# infrastructure/trial/README.md for how the suite was shown to fail when the
# wrapper is broken.

# `check && ok … || bad …` is used as if-then-else throughout. That is safe
# here only because ok() always succeeds (its last command is echo), which is
# exactly the case SC2015 warns about and cannot see.
# shellcheck disable=SC2015

set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/bin" "$work/etc"
cp "$here/fake-awg" "$work/bin/awg"
export PATH="$work/bin:$PATH"
export AWG_STATE="$work/awg.state"

CONF="$work/etc/awg0.conf"
for w in pwa-add-peer pwa-del-peer; do
    sed "s#/etc/amnezia/amneziawg/#$work/etc/#" "${WRAPPER_DIR:-$repo/infrastructure/wrappers}/$w" > "$work/bin/$w"
    chmod +x "$work/bin/$w"
done

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "  ok   $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1"; }

key() { head -c 32 /dev/urandom | base64; }

reset() {
    printf '[Interface]\nPrivateKey = %s\nAddress = 10.88.88.1/24\nListenPort = 8443\n' "$(key)" > "$CONF"
    : > "$AWG_STATE"
}

# expect <name> <exit code> <stderr/stdout substring> -- command...
expect() {
    local name="$1" code="$2" text="$3"; shift 4
    local out rc
    out="$("$@" 2>&1)"; rc=$?
    if [[ "$rc" -eq "$code" && "$out" == *"$text"* ]]; then
        ok "$name"
    else
        bad "$name (exit $rc, output: $out)"
    fi
}

peers_in_conf() { grep -c '^\[Peer\]' "$CONF"; }

echo "pwa-add-peer"

reset
k1="$(key)"; p1="$(key)"
expect "adds a paying client"            0 "ok: added" -- pwa-add-peer "$k1" "$p1" 10.88.88.42/32 auto-alice
grep -qF "$k1 10.88.88.42/32" "$AWG_STATE" && ok "  ...to the runtime" || bad "  ...to the runtime"
grep -qF "PublicKey = $k1" "$CONF" && grep -q '^### auto-alice$' "$CONF" \
    && ok "  ...and to the config, with its ### header" || bad "  ...and to the config, with its ### header"

k2="$(key)"
expect "adds a trial client"             0 "ok: added" -- pwa-add-peer "$k2" "$(key)" 10.88.89.10/32 trial-bob
grep -qF "$k2 10.88.89.10/32" "$AWG_STATE" && ok "  ...to the runtime" || bad "  ...to the runtime"

expect "refuses another subnet"          2 "client subnet" -- pwa-add-peer "$(key)" "$(key)" 10.88.90.10/32 x
expect "refuses the backbone"            2 "client subnet" -- pwa-add-peer "$(key)" "$(key)" 10.77.77.1/32 x
expect "refuses .1 (the node itself)"    2 "out of range"  -- pwa-add-peer "$(key)" "$(key)" 10.88.89.1/32 x
expect "refuses .255"                    2 "out of range"  -- pwa-add-peer "$(key)" "$(key)" 10.88.88.255/32 x
expect "refuses leading zeros"           2 "X/32"          -- pwa-add-peer "$(key)" "$(key)" 10.88.88.042/32 x
expect "refuses a non-/32"               2 "X/32"          -- pwa-add-peer "$(key)" "$(key)" 10.88.88.50/24 x
expect "refuses a bad key"               2 "bad pubkey"    -- pwa-add-peer "not-a-key" "$(key)" 10.88.88.50/32 x
expect "refuses a bad name"              2 "bad name"      -- pwa-add-peer "$(key)" "$(key)" 10.88.88.50/32 'a;b'

expect "refuses a key already running"   3 "peer exists"   -- pwa-add-peer "$k1" "$(key)" 10.88.88.50/32 x
expect "refuses an IP already running"   3 "ip in use"     -- pwa-add-peer "$(key)" "$(key)" 10.88.88.42/32 x

# In the file but not the runtime: what a half-finished manual edit leaves.
k3="$(key)"
printf '\n\n### ghost\n[Peer]\nPublicKey = %s\nPresharedKey = %s\nAllowedIPs = 10.88.88.60/32\n' "$k3" "$(key)" >> "$CONF"
expect "refuses a key only in the config" 3 "peer exists" -- pwa-add-peer "$k3" "$(key)" 10.88.88.61/32 x
expect "refuses an IP only in the config" 3 "ip in use"   -- pwa-add-peer "$(key)" "$(key)" 10.88.88.60/32 x

# The address check compares whole fields: .4 is not taken because .42 is.
expect "a prefix of a used IP is free"   0 "ok: added"     -- pwa-add-peer "$(key)" "$(key)" 10.88.88.4/32 y

before="$(sha256sum < "$CONF")"; runtime_before="$(wc -l < "$AWG_STATE")"
expect "reports a runtime failure"       4 "config restored" -- env AWG_FAIL_SET=1 pwa-add-peer "$(key)" "$(key)" 10.88.88.70/32 z
[[ "$(sha256sum < "$CONF")" == "$before" ]] \
    && ok "  ...and leaves the config byte-identical" || bad "  ...and leaves the config byte-identical"
[[ "$(wc -l < "$AWG_STATE")" -eq "$runtime_before" ]] \
    && ok "  ...and the runtime unchanged" || bad "  ...and the runtime unchanged"
if compgen -G "$work/etc/*.add.*" >/dev/null; then bad "  ...without leaving temp files"; else ok "  ...without leaving temp files"; fi

echo "pwa-del-peer"

n="$(peers_in_conf)"
expect "removes a trial client"          0 "ok: removed 10.88.89.10/32" -- pwa-del-peer "$k2"
[[ "$(peers_in_conf)" -eq $((n - 1)) ]] && ok "  ...exactly one block from the config" || bad "  ...exactly one block from the config"
grep -qF "$k2" "$CONF" "$AWG_STATE" && bad "  ...and from the runtime" || ok "  ...and from the runtime"
grep -q '^### trial-bob$' "$CONF" && bad "  ...including its ### header" || ok "  ...including its ### header"
grep -qF "PublicKey = $k1" "$CONF" && ok "  ...leaving the others" || bad "  ...leaving the others"

kb="$(key)"
echo "$kb 10.77.77.1/32" >> "$AWG_STATE"
expect "refuses a peer outside the client subnets" 1 "outside the client subnets" -- pwa-del-peer "$kb"
grep -qF "$kb" "$AWG_STATE" && ok "  ...and leaves it running" || bad "  ...and leaves it running"

echo
echo "$pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
