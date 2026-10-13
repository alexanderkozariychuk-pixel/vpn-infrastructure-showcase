#!/bin/bash
# Installed by Ansible (roles/entry) — edit in the repository, not on the node.
#
# Policy routing for paying clients, restored at boot by sov-split.service:
#
#   prio  99  fwmark 0x64      -> main   RU destinations leave from the entry
#   prio 100  from CLIENT_NET  -> 200    everything else goes to the exit
#
# Table 200 holds one route, `default via <exit> dev <link>`, set by the link
# interface's PostUp. On entry A rule 100 lived in /etc/rc.local; here it sits
# with rule 99, where someone reading the split tunnel will find it.
#
# The trial subnet has its own rules (sovrn-trial-net, prio 101).
#
# Idempotent: every rule is removed (all copies) before it is added once.

set -u

IPSET_NAME="ru_nets"
FWMARK="0x64"
CLIENT_SUBNET="10.88.88.0/24"
TABLE="200"
CONF_DIR="/etc/sovereign"

# 1. The ipset, from the dump sov-update-ru-list.sh keeps. The dump carries its
#    own `create` line. While the mangle rule below references the set,
#    destroy fails and restore -exist adds into the live set instead.
ipset destroy "$IPSET_NAME" 2>/dev/null || true
ipset restore -exist < "$CONF_DIR/ru_nets.ipset"

# 2. Mark client traffic to RU prefixes.
MARK=(-s "$CLIENT_SUBNET" -m set --match-set "$IPSET_NAME" dst -j MARK --set-mark "$FWMARK")
while iptables -t mangle -D PREROUTING "${MARK[@]}" 2>/dev/null; do :; done
iptables -t mangle -A PREROUTING "${MARK[@]}"

# 3. Marked traffic -> main table (leaves through the entry's own uplink).
while ip rule del fwmark "$FWMARK" lookup main priority 99 2>/dev/null; do :; done
ip rule add fwmark "$FWMARK" lookup main priority 99

# 4. The rest of the client traffic -> table 200 (the link to the exit).
while ip rule del from "$CLIENT_SUBNET" lookup "$TABLE" priority 100 2>/dev/null; do :; done
ip rule add from "$CLIENT_SUBNET" lookup "$TABLE" priority 100
