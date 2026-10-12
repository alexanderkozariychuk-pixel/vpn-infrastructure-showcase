#!/bin/bash
# Refresh the ru_nets ipset from RIPE. Best-effort, safe against bad data.
IPSET_NAME="ru_nets"
CONF_DIR="/etc/sovereign"
MIN_PREFIXES=8000
LOG=/var/log/sov-ru-update.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

TMP=$(mktemp)
if ! curl -s --max-time 90 \
  "https://stat.ripe.net/data/country-resource-list/data.json?resource=RU&v4_format=prefix" \
  -o "$TMP"; then
  echo "$TS [ERROR] RIPE fetch failed" >> $LOG
  rm -f "$TMP"
  exit 0
fi

# extract + count
COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$TMP'))
    p = d['data']['resources']['ipv4']
    with open('/tmp/ru_new.txt','w') as f:
        for x in p: f.write(x+'\n')
    print(len(p))
except Exception as e:
    print(0)
")

if [ "$COUNT" -lt "$MIN_PREFIXES" ]; then
  echo "$TS [ERROR] only $COUNT prefixes (< $MIN_PREFIXES) — refusing to update" >> $LOG
  rm -f "$TMP"
  exit 0
fi

# build a temp set, then atomically swap
TMPSET="${IPSET_NAME}_new"
ipset destroy $TMPSET 2>/dev/null || true
ipset create $TMPSET hash:net maxelem 100000 -exist
while read net; do
  ipset add $TMPSET "$net" -exist 2>/dev/null || true
done < /tmp/ru_new.txt

# re-add the manual service ranges (Yandex/VK/Gosuslugi)
for net in \
  5.255.192.0/18 77.88.0.0/18 87.250.224.0/19 93.158.128.0/18 \
  95.108.128.0/17 213.180.192.0/19 \
  87.240.128.0/18 93.186.224.0/20 95.142.192.0/20 95.213.0.0/18 \
  178.248.232.0/21; do
  ipset add $TMPSET "$net" -exist 2>/dev/null || true
done

# atomic swap: new set becomes the live set
ipset swap $TMPSET $IPSET_NAME
ipset destroy $TMPSET

# persist the refreshed set for reboot survival
ipset save $IPSET_NAME > $CONF_DIR/ru_nets.ipset

NEWCOUNT=$(ipset list $IPSET_NAME | grep -c '/')
echo "$TS [OK] updated ru_nets: $NEWCOUNT entries" >> $LOG
rm -f "$TMP" /tmp/ru_new.txt
