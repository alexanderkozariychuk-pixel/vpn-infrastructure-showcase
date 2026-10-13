#!/bin/bash
# Installed by Ansible (roles/entry) — edit in the repository, not on the node.
#
# Refresh the ru_nets ipset from RIPE (cron, Sundays 04:00 UTC). Also run once
# by Ansible on a new entry, to create the first dump sov-split.service needs.
#
# Best-effort and safe against bad data: a failed fetch or a short list
# (< MIN_PREFIXES) leaves the live set and the dump untouched. The new set is
# built aside and swapped in atomically, so the mark rule never sees a
# half-filled set.
#
# Changes from the copy found on entry A (2026-10-12): temporary files from
# mktemp instead of a fixed /tmp path; the live set is created if missing, so
# the first run on a new node works (swap needs both sets); the dump is
# written to a temporary file and moved, so a failed save cannot leave a
# truncated dump for the next boot. Behaviour is otherwise the same.

set -u

IPSET_NAME="ru_nets"
TMPSET="${IPSET_NAME}_new"
CONF_DIR="/etc/sovereign"
DUMP="$CONF_DIR/ru_nets.ipset"
MIN_PREFIXES=8000
LOG=/var/log/sov-ru-update.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

log() { echo "$TS $*" >> "$LOG"; }

JSON=$(mktemp)
LIST=$(mktemp)
trap 'rm -f "$JSON" "$LIST"' EXIT

if ! curl -fsS --max-time 90 \
    "https://stat.ripe.net/data/country-resource-list/data.json?resource=RU&v4_format=prefix" \
    -o "$JSON"; then
    log "[ERROR] RIPE fetch failed"
    exit 0
fi

COUNT=$(python3 - "$JSON" "$LIST" <<'EOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        prefixes = json.load(f)["data"]["resources"]["ipv4"]
    with open(sys.argv[2], "w") as f:
        f.writelines(p + "\n" for p in prefixes)
    print(len(prefixes))
except Exception:
    print(0)
EOF
)

if [ "$COUNT" -lt "$MIN_PREFIXES" ]; then
    log "[ERROR] only $COUNT prefixes (< $MIN_PREFIXES) — refusing to update"
    exit 0
fi

ipset destroy "$TMPSET" 2>/dev/null || true
ipset create "$TMPSET" hash:net maxelem 100000 -exist
while read -r net; do
    ipset add "$TMPSET" "$net" -exist 2>/dev/null || true
done < "$LIST"

# Service ranges RIPE lists under other countries (Yandex, VK, Gosuslugi).
for net in \
    5.255.192.0/18 77.88.0.0/18 87.250.224.0/19 93.158.128.0/18 \
    95.108.128.0/17 213.180.192.0/19 \
    87.240.128.0/18 93.186.224.0/20 95.142.192.0/20 95.213.0.0/18 \
    178.248.232.0/21; do
    ipset add "$TMPSET" "$net" -exist 2>/dev/null || true
done

ipset create "$IPSET_NAME" hash:net maxelem 100000 -exist
ipset swap "$TMPSET" "$IPSET_NAME"
ipset destroy "$TMPSET"

mkdir -p "$CONF_DIR"
if ipset save "$IPSET_NAME" > "$DUMP.tmp"; then
    mv -f "$DUMP.tmp" "$DUMP"
else
    rm -f "$DUMP.tmp"
    log "[ERROR] ipset save failed — live set updated, dump left as it was"
    exit 0
fi

NEWCOUNT=$(ipset list "$IPSET_NAME" | grep -c '/')
log "[OK] updated $IPSET_NAME: $NEWCOUNT entries"
