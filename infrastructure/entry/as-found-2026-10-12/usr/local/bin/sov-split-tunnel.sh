#!/bin/bash
# Restore RU split-tunnel: ipset + mark rule + ip rule.
IPSET_NAME="ru_nets"
FWMARK="0x64"
CLIENT_SUBNET="10.88.88.0/24"
CONF_DIR="/etc/sovereign"

# 1. restore ipset — destroy any existing set first, then load from dump
#    (dump file contains its own `create` line; -exist makes it idempotent)
ipset destroy ${IPSET_NAME} 2>/dev/null || true
ipset restore -exist < ${CONF_DIR}/ru_nets.ipset

# 2. mangle mark rule (idempotent)
iptables -t mangle -D PREROUTING -s ${CLIENT_SUBNET} -m set --match-set ${IPSET_NAME} dst -j MARK --set-mark ${FWMARK} 2>/dev/null || true
iptables -t mangle -A PREROUTING -s ${CLIENT_SUBNET} -m set --match-set ${IPSET_NAME} dst -j MARK --set-mark ${FWMARK}

# 3. ip rule: marked traffic -> main table (local RF exit), priority 99
ip rule del fwmark ${FWMARK} lookup main 2>/dev/null || true
ip rule add fwmark ${FWMARK} lookup main priority 99
