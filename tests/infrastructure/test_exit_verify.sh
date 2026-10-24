#!/usr/bin/env bash
#
# Tests the read-only checks of the exit role (roles/exit/tasks/verify.yml)
# without a node, the way test_entry_verify.sh tests the entry's.
#
#   bash tests/infrastructure/test_exit_verify.sh
#
# Needs ansible (pip install ansible). No root, nothing touched outside a
# temporary directory: every command the checks run (awg, ip, ipset,
# iptables, sysctl, systemctl, sshd, ufw) is a stub answering from a fixture.
#
# fixtures/good is exit-2 as built on 2026-10-24: it must produce no
# findings. Each case breaks it in one place and must produce exactly one
# finding, the expected one. Its awg0 peer section carries a `jc:` line (the
# peer list must be cut off before parsing).

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DIR="$HERE/exit-verify"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

export ANSIBLE_ROLES_PATH="$ROOT/infrastructure/ansible/roles"
export ANSIBLE_LOCALHOST_WARNING=False
export ANSIBLE_INVENTORY_UNPARSED_WARNING=False
export ANSIBLE_NOCOLOR=1

pass=0
fail=0

# run <fixture dir> <output file>; prints ansible's output on failure.
run() {
    if ! ansible-playbook "$DIR/play.yml" \
            -e "stub_dir=$DIR/stubs" -e "fixture=$1" -e "out=$2" \
            </dev/null >"$2.log" 2>&1; then
        echo "  ansible failed:"; sed 's/^/    /' "$2.log" | tail -20
        return 1
    fi
}

# case <name> <expected finding, or "" for none> <shell edit run inside the fixture copy>
case_() {
    local name=$1 want=$2 edit=$3 fx="$WORK/$1" out="$WORK/$1.out" got
    cp -r "$DIR/fixtures/good" "$fx"
    (cd "$fx" && eval "$edit")
    if ! run "$fx" "$out"; then
        echo "FAIL $name"; fail=$((fail + 1)); return
    fi
    got="$(grep -c . "$out" || true)"
    local ok=0
    if [[ -z $want ]]; then
        [[ $got -eq 0 ]] && ok=1
    else
        [[ $got -eq 1 ]] && grep -qF -- "$want" "$out" && ok=1
    fi
    if (( ok )); then
        echo "ok   $name"; pass=$((pass + 1))
    else
        echo "FAIL $name — want ${want:-no findings}, got:"
        sed 's/^/    /' "$out"
        fail=$((fail + 1))
    fi
}

case_ good                ""                                                  ':'
case_ awg0-jc             "awg0: jc is 4, want 8"                             'sed -i "s/^  jc: 8$/  jc: 4/" awg_show_awg0'
case_ awg0-s4-default     "awg0: s4 is 0, want 8"                             'sed -i "/^  s4: /d" awg_show_awg0'
case_ awg0-h2             "awg0: h2 is 200000000-200200001"                   'sed -i "s/200200000/200200001/" awg_show_awg0'
case_ awg0-no-i1          "awg0: i1 is absent"                                'sed -i "/^  i1: /d" awg_show_awg0'
case_ awg0-key            "awg0: public key is"                               'sed -i "s/^  public key: .*/  public key: WFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFg=/" awg_show_awg0'
case_ awg0-port           "awg0: listening port is 40002, want 40001"         'sed -i "s/^  listening port: 40001/  listening port: 40002/" awg_show_awg0'
case_ awg0-down           "awg0: interface not up"                            ': > awg_interfaces'
case_ link-stale          "awg0: no handshake in the last 180 s"              'echo 200 > awg_hs_age_awg0'
case_ policy-accept       "FORWARD policy is not DROP"                        'sed -i "s/^-P FORWARD DROP/-P FORWARD ACCEPT/" iptables_forward'
case_ no-accept           "FORWARD: awg0 -> eth0 not accepted"                'sed -i "/-i awg0 -o eth0 -j ACCEPT/d" iptables_forward'
case_ no-replies          "FORWARD: replies eth0 -> awg0 not accepted"        'sed -i "/-i eth0 -o awg0/d" iptables_forward'
case_ no-nat              "nat: no MASQUERADE of 10.77.77.8/30 out of eth0"   'sed -i "/MASQUERADE/d" iptables_nat'
case_ no-bt-jump          "FORWARD: no SOVRN_BT jump for awg0"                'sed -i "/-j SOVRN_BT/d" iptables_forward'
case_ bt-jump-late        "FORWARD: SOVRN_BT jump for awg0 after its ACCEPT"  'sed -i "/-j SOVRN_BT/d" iptables_forward; echo "-A FORWARD -i awg0 -j SOVRN_BT" >> iptables_forward'
case_ bt-short            "SOVRN_BT: 7 DROP rules, want 8"                    'sed -i "/get_peers/d" iptables_bt'
case_ bt-missing          "SOVRN_BT: 0 DROP rules, want 8"                    'rm iptables_bt'
case_ no-forwarding       "ip_forward = 0"                                    'sed -i "s/ip_forward=1/ip_forward=0/" sysctl'
case_ conntrack-small     "nf_conntrack_max = 65536, want >= 262144"          'sed -i "s/conntrack_max=.*/conntrack_max=65536/" sysctl'
case_ unit-disabled       "unit awg-quick@awg0: active disabled"              'sed -i "s/=active enabled/=active disabled/" units'

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
