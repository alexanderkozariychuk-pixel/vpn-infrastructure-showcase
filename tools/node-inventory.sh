#!/usr/bin/env bash
#
# node-inventory.sh — everything a VPN node is made of, as one text report.
#
# Read-only. Written for the entry node, works on any of them. Its output is
# the specification the Ansible roles are written against, and the way a newly
# built node is compared with the one it must match: run it on both, diff.
#
#   ssh sov-entry 'sudo bash -s' < tools/node-inventory.sh > entry-A.txt
#
# Nothing secret leaves the node: every 44-character base64 string (private
# keys, preshared keys, public keys alike) is replaced with <key> on the way
# out. Where two nodes must share a key, compare the `key-id` lines instead —
# a short hash, enough to tell same from different, useless to an attacker.

set -uo pipefail
export LC_ALL=C PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

redact() { sed -E 's#[A-Za-z0-9+/]{42,43}=#<key>#g'; }
keyid() { printf '%s' "$1" | sha256sum | cut -c1-12; }
h() { printf '\n######## %s\n' "$*"; }
run() { printf '\n$ %s\n' "$*"; bash -c "$*" 2>&1 | redact; }

{
h "system"
run 'hostnamectl 2>/dev/null | grep -E "Static hostname|Operating System|Kernel|Virtualization"'
run 'uptime; timedatectl 2>/dev/null | grep -E "Time zone|NTP service|synchronized"'
run 'nproc; free -h; swapon --show; df -h /'

h "packages"
run 'dpkg -l | awk "/^ii/ {print \$2, \$3}" | grep -E "amnezia|wireguard|ufw|fail2ban|ipset|iptables|nftables|netfilter|unattended|dkms|docker|linux-headers-$(uname -r)"'
run 'dkms status'
run 'apt-cache policy amneziawg 2>/dev/null | head -5; ls /etc/apt/sources.list.d/'

h "interfaces"
run 'ip -br link; ip -br addr'
run 'awg show interfaces'
for i in $(awg show interfaces 2>/dev/null); do
    pub=$(awg show "$i" public-key 2>/dev/null)
    printf '\n-- %s key-id %s, listen %s, peers %s\n' "$i" "$(keyid "$pub")" \
        "$(awg show "$i" listen-port)" "$(awg show "$i" peers | wc -l)"
    # The interface section only: obfuscation, port, MTU, PostUp/Down.
    run "awg showconf $i | sed '/^\[Peer\]/,\$d' | grep -viE '^(privatekey)'"
    if [ "$(awg show "$i" peers | wc -l)" -le 2 ]; then
        run "awg showconf $i | sed -n '/^\[Peer\]/,\$p' | grep -viE '^(presharedkey)'"
    fi
done

h "amneziawg config files"
run 'ls -la /etc/amnezia/amneziawg/'
for f in /etc/amnezia/amneziawg/*.conf; do
    [ -f "$f" ] || continue
    printf '\n-- %s: %s [Peer] sections\n' "$f" "$(grep -c '^\[Peer\]' "$f")"
    run "sed '/^\[Peer\]/,\$d' '$f' | grep -viE '^privatekey'"
done
run 'diff <(awg showconf awg0 2>/dev/null | grep -E "^(PublicKey|AllowedIPs)" | sort) <(grep -E "^(PublicKey|AllowedIPs)" /etc/amnezia/amneziawg/awg0.conf | sed "s/ *= */ = /" | sort) && echo "awg0: runtime peers == file peers"'

h "routing"
run 'ip rule'
run 'ip route show table all | grep -vE "^(local|broadcast|multicast|fe80|ff00)" '
run 'ipset list -t 2>/dev/null'
run 'sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter net.ipv4.conf.default.rp_filter net.core.default_qdisc net.ipv4.tcp_congestion_control net.netfilter.nf_conntrack_max 2>/dev/null'
run 'ls /etc/sysctl.d/; grep -hvE "^\s*(#|$)" /etc/sysctl.conf /etc/sysctl.d/*.conf 2>/dev/null'

h "firewall"
run 'ufw status verbose'
run 'grep -E "^DEFAULT_" /etc/default/ufw'
run 'iptables-save'
run 'ip6tables-save | grep -vE "^#" | head -60'

h "services"
run 'systemctl list-unit-files --state=enabled --no-pager | grep -vE "^(UNIT|$)" '
run 'systemctl list-units --type=service --state=running --no-pager --no-legend'
run 'systemctl list-units --state=failed --no-pager --no-legend'
for u in $(systemctl list-unit-files --no-legend --no-pager | awk '{print $1}' | grep -E "^(sov|sovrn|pwa)"); do
    run "systemctl cat $u"
done
run 'systemctl is-active docker 2>/dev/null; command -v docker && docker ps --format "{{.Names}} {{.Image}}" 2>/dev/null'

h "scripts and state"
run 'ls -la /usr/local/bin /usr/local/sbin'
run 'sha256sum /usr/local/bin/* /usr/local/sbin/* 2>/dev/null'
run 'ls -la /etc/sovereign/ 2>/dev/null'
run 'ls /etc/cron.d/; grep -hvE "^\s*(#|$)" /etc/cron.d/* 2>/dev/null; crontab -l 2>/dev/null'
run 'ls /etc/logrotate.d/'

h "users and access"
run 'getent passwd | awk -F: "\$3 >= 1000 && \$3 < 60000 || \$1 ~ /^(pwa|sov)/ {print \$1, \$3, \$6, \$7}"'
run 'getent group sudo'
run 'ls -la /etc/sudoers.d/; grep -hvE "^\s*(#|$)" /etc/sudoers.d/* 2>/dev/null'
for d in /root /home/*; do
    f="$d/.ssh/authorized_keys"
    [ -f "$f" ] || continue
    printf '\n-- %s: %s key(s)\n' "$f" "$(grep -c . "$f")"
    # Options (forced command, from=) and comment kept; the key itself is redacted.
    run "sed -E 's#(ssh-[a-z0-9-]+|ecdsa-[a-z0-9-]+) [A-Za-z0-9+/=]+#\1 <key>#' '$f'"
    run "ssh-keygen -lf '$f'"
done
run 'sshd -T | grep -Ei "^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|allowusers|maxauthtries|x11forwarding) "'
run 'ls /etc/ssh/sshd_config.d/'

h "hardening"
run 'fail2ban-client status 2>/dev/null; grep -hvE "^\s*(#|$)" /etc/fail2ban/jail.local 2>/dev/null'
run 'grep -hvE "^\s*(//|$)" /etc/apt/apt.conf.d/20auto-upgrades 2>/dev/null; grep -hE "Automatic-Reboot|Origins-Pattern|Allowed-Origins" -A3 /etc/apt/apt.conf.d/50unattended-upgrades 2>/dev/null | grep -v "^\s*//"'
} | redact
