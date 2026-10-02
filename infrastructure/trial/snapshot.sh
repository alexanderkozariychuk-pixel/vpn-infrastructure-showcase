#!/usr/bin/env bash
#
# snapshot.sh — record the entry node's network state before the trial subnet
# is installed, so rollback.sh can restore the wrappers and prove that what
# it leaves behind is what was there before.
#
# Run as root, BEFORE installing anything:
#   sudo ./snapshot.sh
#
# Writes /root/sovrn-pre-trial-<timestamp>/ and records its path in
# /etc/sovereign/trial-snapshot.

set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

IFACE=awg0
dir="/root/sovrn-pre-trial-$(date +%Y%m%d-%H%M%S)"

# shellcheck source=capture.sh
. "$(dirname "$0")/capture.sh"

mkdir -m 0700 "$dir"
capture_state "$IFACE" "$dir"

mkdir "$dir/wrappers"
cp -p /usr/local/bin/pwa-add-peer /usr/local/bin/pwa-del-peer "$dir/wrappers/"
sha256sum /usr/local/bin/pwa-add-peer /usr/local/bin/pwa-del-peer > "$dir/wrappers.sha256"
cp -p "$(dirname "$0")/capture.sh" "$dir/"

mkdir -p /etc/sovereign
echo "$dir" > /etc/sovereign/trial-snapshot

echo "snapshot written to $dir"
ls -1 "$dir"
