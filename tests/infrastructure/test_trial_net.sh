#!/usr/bin/env bash
#
# End-to-end test of sovrn-trial-net, snapshot.sh and rollback.sh against an
# emulated entry node, built in throwaway network namespaces.
#
#   sudo bash tests/infrastructure/test_trial_net.sh
#
# Needs root (for namespaces), iptables, ipset, iproute2 and ping. Nothing
# outside the namespaces is touched: the script re-runs itself under
# `unshare -n -m` and mounts tmpfs over every path the node scripts write to.
#
# The emulated node reproduces what `iptables -S`, `ip rule` and the PostUp
# lines showed on the real entry on 2026-10-02:
#
#     paid   10.88.88.50 ─┐                         ┌─ eth0 ── "inet": 5.255.192.10 (in ru_nets)
#                         ├─ awg0 ── [ entry ] ─────┤
#     trial  10.88.89.5 ──┘  10.88.88.1/24          └─ awg1 ── "exit": 203.0.113.10
#
#   FORWARD: DOCKER-USER (returns), -i awg0 -j ACCEPT
#   nat:     -o awg1 MASQUERADE, -o eth0 MASQUERADE
#   mangle:  -s 10.88.88.0/24 --match-set ru_nets dst -> mark 0x64
#   rules:   99 fwmark 0x64 -> main, 100 from 10.88.88.0/24 -> table 200
#   table 200: default via 10.77.77.1 dev awg1
#
# Reaching 203.0.113.10 proves a packet took table 200 (only "exit" has it);
# reaching 5.255.192.10 proves the RU split sent it out of eth0.
#
# awg0 is a bridge here rather than an AmneziaWG interface — the scripts only
# care that it is a layer-3 interface called awg0 carrying 10.88.88.1/24.

set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"

if [[ -z "${SOVRN_TEST_INSIDE:-}" ]]; then
    [[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
    SOVRN_TEST_INSIDE=1 exec unshare -n -m --propagation private bash "$0" "$@"
fi

TRIAL_SRC="${TRIAL_SRC:-$repo/infrastructure/trial}"
WRAPPER_SRC="${WRAPPER_SRC:-$repo/infrastructure/wrappers}"

# ── private filesystem view ─────────────────────────────────────────────────

for d in /run /usr/local/bin /etc/sovereign /etc/amnezia /etc/systemd/system /root; do
    mkdir -p "$d"; mount -t tmpfs none "$d"
done
mkdir -p /run/netns /etc/amnezia/amneziawg /root/stub

cp "$here/fake-awg" /root/stub/awg
printf '#!/bin/sh\nexit 0\n' > /root/stub/systemctl
chmod +x /root/stub/*
export PATH="/root/stub:$PATH"
export AWG_STATE=/root/awg.state
: > "$AWG_STATE"
printf '[Interface]\nAddress = 10.88.88.1/24\nListenPort = 8443\n' > /etc/amnezia/amneziawg/awg0.conf

# The node's wrappers as they are today.
install -m 0755 "$here/fixtures/pwa-add-peer.node-2026-07-18" /usr/local/bin/pwa-add-peer
install -m 0755 "$here/fixtures/pwa-del-peer.node-2026-09-20" /usr/local/bin/pwa-del-peer

# ── topology ────────────────────────────────────────────────────────────────

ns() { ip netns exec "$@"; }

ip link set lo up
for n in paid trial inet exit; do ip netns add "$n"; ns "$n" ip link set lo up; done

ip link add awg0 type bridge
ip addr add 10.88.88.1/24 dev awg0
ip link set awg0 up
for n in paid trial; do
    ip link add "br-$n" type veth peer name c0 netns "$n"
    ip link set "br-$n" master awg0 up
    ns "$n" ip link set c0 up
done
ns paid  ip addr add 10.88.88.50/24 dev c0
ns paid  ip route add default via 10.88.88.1
ns trial ip addr add 10.88.89.5/24 dev c0
ns trial ip route add default via 10.88.89.1

ip link add eth0 type veth peer name i0 netns inet
ip addr add 198.51.100.2/24 dev eth0; ip link set eth0 up
ns inet ip addr add 198.51.100.1/24 dev i0; ns inet ip link set i0 up
ns inet ip addr add 5.255.192.10/32 dev lo
ns inet ip route add default via 198.51.100.2
ip route add default via 198.51.100.1

ip link add awg1 type veth peer name e0 netns exit
ip addr add 10.77.77.2/30 dev awg1; ip link set awg1 up
ns exit ip addr add 10.77.77.1/30 dev e0; ns exit ip link set e0 up
ns exit ip addr add 203.0.113.10/32 dev lo
ns exit ip route add default via 10.77.77.2

sysctl -qw net.ipv4.ip_forward=1

iptables -N DOCKER-USER; iptables -A DOCKER-USER -j RETURN
iptables -A FORWARD -j DOCKER-USER
iptables -A FORWARD -i awg0 -j ACCEPT
iptables -t nat -A POSTROUTING -o awg1 -j MASQUERADE
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
ipset create ru_nets hash:net
ipset add ru_nets 5.255.192.0/18
iptables -t mangle -A PREROUTING -s 10.88.88.0/24 -m set --match-set ru_nets dst -j MARK --set-mark 0x64
ip rule add fwmark 0x64 lookup main priority 99
ip rule add from 10.88.88.0/24 lookup 200 priority 100
ip route add default via 10.77.77.1 dev awg1 table 200

# ── helpers ─────────────────────────────────────────────────────────────────

pass=0; fail=0
ok()  { pass=$((pass + 1)); echo "  ok   $1"; }
bad() { fail=$((fail + 1)); echo "  FAIL $1"; }

# Three tries: the emulated awg0 is a bridge, and a neighbour entry left
# FAILED by an earlier unanswered ARP can eat the first packet. A real awg0
# has no ARP; the "cannot" checks only get stricter this way.
reach()   { ns "$1" ping -c3 -i0.2 -W1 "$2" >/dev/null 2>&1; }
can()     { reach "$1" "$2" && ok "$1 reaches $2 ($3)"  || bad "$1 reaches $2 ($3)"; }
cannot()  { reach "$1" "$2" && bad "$1 cannot reach $2 ($3)" || ok "$1 cannot reach $2 ($3)"; }

paid_is_unaffected() {
    can paid 203.0.113.10 "paid, via exit"
    can paid 5.255.192.10 "paid, RU direct"
}

# ── before ──────────────────────────────────────────────────────────────────

echo "== before install: the node as it is today"
paid_is_unaffected
cannot trial 203.0.113.10 "no trial subnet yet"

echo "== snapshot"
bash "$TRIAL_SRC/snapshot.sh" >/dev/null && ok "snapshot.sh" || bad "snapshot.sh"

echo "== install and up"
install -m 0755 "$WRAPPER_SRC/pwa-add-peer" /usr/local/bin/pwa-add-peer
install -m 0755 "$WRAPPER_SRC/pwa-del-peer" /usr/local/bin/pwa-del-peer
install -m 0755 "$TRIAL_SRC/sovrn-trial-net" /usr/local/bin/sovrn-trial-net
install -m 0644 "$TRIAL_SRC/sovrn-trial-net.service" /etc/systemd/system/sovrn-trial-net.service
echo on > /etc/sovereign/trial.state

# fq_codel is what the node uses; kernels built without it (some sandboxes)
# get pfifo, which exercises everything here except fair queueing itself.
leaf=fq_codel
ip link add qprobe type dummy 2>/dev/null || ip link add qprobe type veth peer name qprobe1
tc qdisc add dev qprobe root handle 1: htb 2>/dev/null
tc class add dev qprobe parent 1: classid 1:1 htb rate 1mbit 2>/dev/null
tc qdisc add dev qprobe parent 1:1 handle 2: fq_codel 2>/dev/null || leaf=pfifo
# Same for the policer (act_police) behind the upload ceiling.
up_rate=10mbit
tc qdisc add dev qprobe handle ffff: ingress 2>/dev/null
tc filter add dev qprobe parent ffff: protocol ip u32 match ip src 10.0.0.0/8 \
    police rate 1mbit burst 10k drop flowid :1 2>/dev/null || up_rate=off
ip link del qprobe
echo "  (leaf qdisc: $leaf, upload ceiling: $up_rate)"

echo "== a failed up leaves nothing behind"
echo "LEAF_QDISC=no-such-qdisc" > /etc/sovereign/trial.conf
sovrn-trial-net up >/root/upfail.log 2>&1 && bad "up fails when tc does" || ok "up fails when tc does"
mkdir -p /root/after-fail
# shellcheck source=../../infrastructure/trial/capture.sh
. "$TRIAL_SRC/capture.sh"
capture_state awg0 /root/after-fail
compare_state "$(cat /etc/sovereign/trial-snapshot)" /root/after-fail awg0 >/root/cmp.log \
    && ok "  ...and the node is exactly as in the snapshot" || { bad "  ...and the node is exactly as in the snapshot"; cat /root/cmp.log; }
cannot trial 203.0.113.10 "after a failed up"
printf 'LEAF_QDISC=%s\nUP_RATE=%s\n' "$leaf" "$up_rate" > /etc/sovereign/trial.conf

sovrn-trial-net up >/root/up.log 2>&1 && ok "up, and its own check passes" || { bad "up"; cat /root/up.log; }
sovrn-trial-net up >/dev/null 2>&1 && ok "up a second time" || bad "up a second time"
[[ "$(iptables -S FORWARD | grep -c SOVRN-TRIAL)" -eq 1 ]] && ok "  ...one FORWARD jump" || bad "  ...one FORWARD jump"
[[ "$(iptables -t mangle -S PREROUTING | grep -c 10.88.89.0/24)" -eq 1 ]] && ok "  ...one mangle rule" || bad "  ...one mangle rule"
[[ "$(ip rule show | grep -c 'from 10.88.89.0/24')" -eq 1 ]] && ok "  ...one ip rule" || bad "  ...one ip rule"

echo "== trial traffic"
can    trial 203.0.113.10 "trial, via exit (table 200)"
can    trial 5.255.192.10 "trial, RU direct (split)"
cannot trial 10.88.88.50  "trial may not reach other clients"
paid_is_unaffected

echo "== bandwidth classes"
bytes() { tc -s class show dev awg0 classid "$1" | awk '/Sent/ { print $2; exit }'; }
t0="$(bytes 1:20)"; p0="$(bytes 1:10)"
reach trial 203.0.113.10; reach paid 203.0.113.10
t1="$(bytes 1:20)"; p1="$(bytes 1:10)"
(( t1 > t0 )) && ok "trial replies go through the limited class 1:20" || bad "trial replies go through the limited class 1:20"
(( p1 > p0 )) && ok "paid replies go through the default class 1:10" || bad "paid replies go through the default class 1:10"
if [[ "$up_rate" == off ]]; then
    echo "  skip upload policer (this kernel has no act_police)"
else
    tc -s filter show dev awg0 parent ffff: | grep -q 'police' && ok "upload policer installed" || bad "upload policer installed"
fi

echo "== kill switch"
sovrn-trial-net off >/dev/null
cannot trial 203.0.113.10 "switched off"
cannot trial 5.255.192.10 "switched off"
paid_is_unaffected
sovrn-trial-net check >/dev/null && ok "check agrees it is off" || bad "check agrees it is off"
[[ "$(cat /etc/sovereign/trial.state)" == off ]] && ok "  ...and the state file says off" || bad "  ...and the state file says off"
sovrn-trial-net up >/dev/null 2>&1
cannot trial 203.0.113.10 "still off after up (as after a reboot)"
sovrn-trial-net on >/dev/null
can trial 203.0.113.10 "switched back on"

echo "== check notices damage"
ip rule del from 10.88.89.0/24 lookup 200 priority 101
sovrn-trial-net check >/dev/null && bad "check misses a removed ip rule" || ok "check misses nothing: removed ip rule"
sovrn-trial-net up >/dev/null 2>&1 && ok "  ...up repairs it" || bad "  ...up repairs it"

echo "== rollback refuses while trial peers exist"
tk="$(head -c 32 /dev/urandom | base64)"
pwa-add-peer "$tk" "$(head -c 32 /dev/urandom | base64)" 10.88.89.20/32 trial-t >/dev/null \
    && ok "new pwa-add-peer issues a trial peer" || bad "new pwa-add-peer issues a trial peer"
bash "$TRIAL_SRC/rollback.sh" >/root/rb1.log 2>&1 && bad "rollback refuses" || ok "rollback refuses"
sovrn-trial-net check >/dev/null && ok "  ...and changed nothing" || bad "  ...and changed nothing"

echo "== rollback"
if bash "$TRIAL_SRC/rollback.sh" --remove-trial-peers >/root/rb2.log 2>&1; then
    ok "rollback --remove-trial-peers reports OK"
else
    bad "rollback --remove-trial-peers reports OK"; cat /root/rb2.log
fi
grep -qF "$tk" "$AWG_STATE" && bad "  ...trial peer removed" || ok "  ...trial peer removed"
cmp -s /usr/local/bin/pwa-add-peer "$here/fixtures/pwa-add-peer.node-2026-07-18" \
    && ok "  ...node's pwa-add-peer back" || bad "  ...node's pwa-add-peer back"
cmp -s /usr/local/bin/pwa-del-peer "$here/fixtures/pwa-del-peer.node-2026-09-20" \
    && ok "  ...node's pwa-del-peer back" || bad "  ...node's pwa-del-peer back"
[[ ! -e /usr/local/bin/sovrn-trial-net && ! -e /etc/systemd/system/sovrn-trial-net.service ]] \
    && ok "  ...trial files gone" || bad "  ...trial files gone"
paid_is_unaffected
cannot trial 203.0.113.10 "trial subnet gone"

echo "== rollback notices what it did not undo"
sleep 1; bash "$TRIAL_SRC/snapshot.sh" >/dev/null
ip rule add from 10.88.89.0/24 lookup 200 priority 101
bash "$TRIAL_SRC/rollback.sh" >/root/rb3.log 2>&1 && bad "a leftover rule fails the comparison" \
    || ok "a leftover rule fails the comparison"
grep -q 'ip-rule .*DIFFERS' /root/rb3.log && ok "  ...and names ip-rule" || bad "  ...and names ip-rule"

echo
echo "$pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
