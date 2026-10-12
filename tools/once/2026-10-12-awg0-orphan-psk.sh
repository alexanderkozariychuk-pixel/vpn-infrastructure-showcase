#!/bin/bash
#
# One-off, 2026-10-12: entry A's awg0.conf held a PresharedKey + AllowedIPs pair
# with no [Peer]/PublicKey of its own (a leftover of an old hand edit), which the
# parser folds into the peer above it. Run:
#   ssh sov-entry 'sudo bash -s' < tools/once/2026-10-12-awg0-orphan-psk.sh
# Remove the headerless PresharedKey/AllowedIPs pair (PSK fingerprint $FP) from
# awg0.conf. Never touches the running interface. Aborts on any surprise.
set -uo pipefail
F=${F:-/etc/amnezia/amneziawg/awg0.conf}
FP=${FP:-d4fb054e}
EXPECT_NEXT=${EXPECT_NEXT:-AllowedIPs = 10.88.88.49/32}
fp() { printf %s "$1" | sha256sum | cut -c1-8; }

before=$(sha256sum < "$F")
TMP=$(mktemp)
# One pass: drop the PSK line whose key has fingerprint $FP, and the line after
# it, only if the line before is blank and the line after is exactly $EXPECT_NEXT.
hits=0; prev=""; skip_next=0
mapfile -t L < "$F"
for ((i = 0; i < ${#L[@]}; i++)); do
    l=${L[i]}
    if (( skip_next )); then skip_next=0; continue; fi
    if [[ $l =~ ^PresharedKey\ =\ ([A-Za-z0-9+/]{43}=)$ ]] && [[ $(fp "${BASH_REMATCH[1]}") == "$FP" ]]; then
        if [[ -z $prev && ${L[i+1]:-} == "$EXPECT_NEXT" ]]; then
            hits=$((hits + 1)); skip_next=1; echo "drop line $((i + 1)) and $((i + 2))"; continue
        fi
        echo "STOP: found the key at line $((i + 1)) but not in the expected place"; rm -f "$TMP"; exit 1
    fi
    printf '%s\n' "$l" >> "$TMP"
    prev=$l
done
if (( hits != 1 )); then echo "STOP: expected exactly 1 match, got $hits"; rm -f "$TMP"; exit 1; fi

# Every peer block in the new file: one PublicKey, one PresharedKey, one or more AllowedIPs.
c() { grep -c "$1" "$TMP"; }
if [[ $(c '^\[Peer\]') != "$(c '^PublicKey')" || $(c '^PublicKey') != "$(c '^PresharedKey')" ]]; then
    echo "STOP: peer/key counts differ in the result"; rm -f "$TMP"; exit 1
fi
# Nothing else changed: the new file is the old one minus exactly two lines.
if [[ $(diff "$F" "$TMP" | grep -c '^<') != 2 || $(diff "$F" "$TMP" | grep -c '^>') != 0 ]]; then
    echo "STOP: the diff is not exactly two removed lines"; rm -f "$TMP"; exit 1
fi
# The file must not have changed under us (a portal add/remove in between).
if [[ $(sha256sum < "$F") != "$before" ]]; then echo "STOP: the file changed while working, run again"; rm -f "$TMP"; exit 1; fi
cp -p "$F" "$F.bak-orphan-$(date +%Y%m%d-%H%M%S)"
cat "$TMP" > "$F"     # keeps the file's inode, owner and mode
rm -f "$TMP"
echo "done"
