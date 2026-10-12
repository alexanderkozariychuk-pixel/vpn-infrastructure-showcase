#!/usr/bin/env bash
#
# dpi-test-node.sh — does a candidate entry address get through mobile DPI?
#
# Turns a fresh Ubuntu 24.04 VPS into a bare AmneziaWG server that looks to a
# censor exactly like our entry: same port, same obfuscation parameters, same
# client MTU. One peer, for a test phone; traffic leaves straight from this
# server, no exit, no portal. The only thing that differs from the real entry
# is the address — which is the thing under test.
#
#   ssh root@<candidate> 'bash -s' < tools/dpi-test-node.sh
#
# Prints the phone's config as a QR code (and leaves it in /root/dpi-test.conf).
# The QR holds the test peer's private key: scan it, do not screenshot or
# paste it anywhere.
#
# It uses keys of its own, never the entry's. A candidate that passes is
# reinstalled from a clean image before it is built into an entry, so nothing
# here is meant to last.

set -euo pipefail
export LC_ALL=C DEBIAN_FRONTEND=noninteractive

PORT=8443
NET=10.99.0
DIR=/etc/amnezia/amneziawg
# Must match AWG_PARAMS in pwa/services/provisioner.py.
PARAMS='Jc = 3
Jmin = 50
Jmax = 1000
S1 = 72
S2 = 146
H1 = 1163059398
H2 = 1787455160
H3 = 970047041
H4 = 133143559'

die() { echo "dpi-test: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
. /etc/os-release
[ "${VERSION_ID:-}" = "24.04" ] || echo "dpi-test: warning: written for Ubuntu 24.04, this is ${PRETTY_NAME:-unknown}" >&2
[ -e "$DIR/awg0.conf" ] && die "$DIR/awg0.conf already exists — not overwriting"

virt=$(systemd-detect-virt || true)
echo "virtualization: $virt"
case "$virt" in
    openvz|lxc|lxc-libvirt|docker|podman) die "$virt is a container: no own kernel, AmneziaWG cannot load" ;;
esac

uplink=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}')
[ -n "$uplink" ] || die "cannot find the uplink interface"
addr=$(ip -4 -o addr show dev "$uplink" scope global | awk '{split($4, a, "/"); print a[1]; exit}')
[ -n "$uplink" ] && [ -n "$addr" ] || die "cannot find the uplink interface or its address"
echo "uplink: $uplink $addr"

echo "== packages"
apt-get update -q
apt-get install -yq software-properties-common
add-apt-repository -y ppa:amnezia/ppa
apt-get install -yq amneziawg amneziawg-tools "linux-headers-$(uname -r)" qrencode iptables
modprobe amneziawg || die "the amneziawg module did not load (dkms status: $(dkms status 2>&1))"

echo "== keys and config"
umask 077
mkdir -p "$DIR"
srv_priv=$(awg genkey); srv_pub=$(printf '%s' "$srv_priv" | awg pubkey)
cli_priv=$(awg genkey); cli_pub=$(printf '%s' "$cli_priv" | awg pubkey)
psk=$(awg genpsk)

cat > "$DIR/awg0.conf" <<EOF
[Interface]
PrivateKey = $srv_priv
Address = $NET.1/24
ListenPort = $PORT
$PARAMS
PostUp = sysctl -q -w net.ipv4.ip_forward=1
PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -m state --state RELATED,ESTABLISHED -j ACCEPT
PostUp = iptables -t nat -A POSTROUTING -s $NET.0/24 -o $uplink -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -m state --state RELATED,ESTABLISHED -j ACCEPT
PostDown = iptables -t nat -D POSTROUTING -s $NET.0/24 -o $uplink -j MASQUERADE

[Peer]
# test phone
PublicKey = $cli_pub
PresharedKey = $psk
AllowedIPs = $NET.2/32
EOF

cat > /root/dpi-test.conf <<EOF
[Interface]
PrivateKey = $cli_priv
Address = $NET.2/32
DNS = 1.1.1.1
MTU = 1300
$PARAMS

[Peer]
PublicKey = $srv_pub
PresharedKey = $psk
Endpoint = $addr:$PORT
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF

if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow "$PORT/udp" >/dev/null
    ufw route allow in on awg0 out "$uplink" >/dev/null
    echo "ufw: opened $PORT/udp and forwarding awg0 -> $uplink"
fi

echo "== start"
systemctl enable --now awg-quick@awg0
awg show awg0 | grep -E "^interface|listening port"

echo
echo "== scan this with the AmneziaVPN / AmneziaWG app (do not screenshot it)"
qrencode -t ansiutf8 < /root/dpi-test.conf
echo
echo "After connecting on mobile data, on the server:  awg show awg0 latest-handshakes"
