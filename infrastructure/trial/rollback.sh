#!/usr/bin/env bash
#
# rollback.sh — return the entry node to the network state recorded by
# snapshot.sh, and prove it.
#
#   sudo ./rollback.sh [snapshot-dir] [--remove-trial-peers]
#
# Without a directory it uses the one recorded in /etc/sovereign/trial-snapshot.
#
# Steps:
#   1. Refuse if trial peers (10.88.89.x) are still on awg0 — once the old
#      wrappers are back, nothing can remove them through the portal path.
#      --remove-trial-peers removes them first, with the new pwa-del-peer.
#   2. Stop and disable sovrn-trial-net (its `down` removes everything it
#      added), and run `down` once more directly in case the unit was never
#      started.
#   3. Put the snapshot's wrappers back and remove the trial files.
#   4. Capture the state again and diff it against the snapshot. Exit 0 only
#      when every file is identical and the wrappers match their checksums.
#
# A difference in step 4 is not automatically this script's fault — a Docker
# container restarted in between rewrites its own chains. Read the diff.

set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

IFACE=awg0
snap=""
remove_peers=0
for arg in "$@"; do
    case "$arg" in
        --remove-trial-peers) remove_peers=1 ;;
        *) snap="$arg" ;;
    esac
done
[[ -n "$snap" ]] || snap="$(cat /etc/sovereign/trial-snapshot 2>/dev/null || true)"
[[ -n "$snap" && -d "$snap" ]] || { echo "snapshot directory not found: '${snap}'" >&2; exit 1; }
[[ -f "$snap/capture.sh" && -d "$snap/wrappers" ]] || { echo "$snap is not a snapshot" >&2; exit 1; }

# shellcheck source=capture.sh
. "$snap/capture.sh"

echo "== rollback to $snap"

# ── 1. trial peers ───────────────────────────────────────────────────────────

if command -v awg >/dev/null 2>&1; then
    trial_keys="$(awg show "$IFACE" allowed-ips | awk '$2 ~ /^10\.88\.89\./ { print $1 }')"
    if [[ -n "$trial_keys" ]]; then
        if [[ "$remove_peers" -eq 0 ]]; then
            echo "trial peers are still on $IFACE:" >&2
            echo "$trial_keys" | sed 's/^/  /' >&2
            echo "re-run with --remove-trial-peers, or remove them with pwa-del-peer first" >&2
            exit 1
        fi
        while read -r key; do
            /usr/local/bin/pwa-del-peer "$key"
        done <<< "$trial_keys"
    fi
fi

# ── 2. stop the trial subnet ────────────────────────────────────────────────

if [[ -f /etc/systemd/system/sovrn-trial-net.service ]]; then
    systemctl disable --now sovrn-trial-net.service || true
fi
if [[ -x /usr/local/bin/sovrn-trial-net ]]; then
    /usr/local/bin/sovrn-trial-net down
fi

# ── 3. files ─────────────────────────────────────────────────────────────────

install -o root -g root -m 0755 "$snap/wrappers/pwa-add-peer" /usr/local/bin/pwa-add-peer
install -o root -g root -m 0755 "$snap/wrappers/pwa-del-peer" /usr/local/bin/pwa-del-peer
rm -f /etc/systemd/system/sovrn-trial-net.service \
      /usr/local/bin/sovrn-trial-net \
      /etc/sovereign/trial.state \
      /etc/sovereign/trial.conf
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
fi

# ── 4. prove it ──────────────────────────────────────────────────────────────

now="$(mktemp -d /root/sovrn-after-rollback-XXXXXX)"
capture_state "$IFACE" "$now"

echo "== state compared with the snapshot"
ok=1
compare_state "$snap" "$now" "$IFACE" || ok=0

echo "== wrappers"
if sha256sum --quiet -c "$snap/wrappers.sha256"; then
    echo "  pwa-add-peer, pwa-del-peer match the snapshot"
else
    ok=0
fi

if [[ "$ok" -eq 1 ]]; then
    echo "ROLLBACK OK — network state identical to $snap"
    exit 0
fi
echo "ROLLBACK INCOMPLETE — see the differences above (captures in $now)" >&2
exit 1
