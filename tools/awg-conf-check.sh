#!/bin/bash
#
# awg-conf-check.sh — run on a node:  ssh sov-entry 'sudo bash -s' < tools/awg-conf-check.sh
# Exit 0 when the file and the running interface agree, 1 when they differ.
# Read-only: every peer in awg0.conf against the running awg0 — public key,
# preshared key and addresses. Prints fingerprints only, never keys.
set -uo pipefail
F=${F:-/etc/amnezia/amneziawg/awg0.conf}
DUMP=${DUMP:-}
fp() { printf %s "$1" | sha256sum | cut -c1-8; }

# file: "pub psk ip,ip" per [Peer] block (a repeated key overwrites, addresses add up — as the parser does)
file_peers() {
    awk '
        function emit() { if (pub != "") print pub, psk, ips }
        /^\[Peer\]/ { emit(); pub = ""; psk = "-"; ips = ""; next }
        /^\[/       { emit(); pub = ""; next }
        /^PublicKey *=/    { pub = $3 }
        /^PresharedKey *=/ { psk = $3 }
        /^AllowedIPs *=/   { sub(/^AllowedIPs *= */, ""); gsub(/ /, ""); ips = ips (ips ? "," : "") $0 }
        END { emit() }' "$F"
}
# runtime: same shape from the dump (skip the interface line)
run_peers() {
    { if [[ -n $DUMP ]]; then cat "$DUMP"; else awg show awg0 dump; fi; } |
        awk 'NR > 1 { print $1, ($2 == "(none)" ? "-" : $2), $4 }'
}
# addresses sorted within a peer, so order in the file does not matter (mawk has no asort)
hashed() { while read -r pub psk ips; do echo "$(fp "$pub") psk:$(fp "$psk") $(tr ',' '\n' <<<"$ips" | sort | paste -sd,)"; done | sort; }

diff <(file_peers | hashed) <(run_peers | hashed) > /tmp/awg0-verify.$$ 
rc=$?
nf=$(file_peers | wc -l); nr=$(run_peers | wc -l)
if (( nf == 0 || nr == 0 )); then echo "STOP: could not read peers (file $nf, running $nr)"; exit 2; fi
echo "peers: file $nf, running $nr"
if (( rc == 0 )); then echo "OK: file == running (keys, preshared keys, addresses)"; else
    echo "DIFFERENT ('<' file only, '>' running only):"; cat /tmp/awg0-verify.$$; fi
rm -f /tmp/awg0-verify.$$
exit $rc
