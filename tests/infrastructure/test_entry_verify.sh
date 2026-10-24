#!/usr/bin/env bash
#
# Tests the read-only checks in the Ansible roles (roles/common/tasks/verify.yml,
# roles/entry/tasks/verify.yml) without a node.
#
#   bash tests/infrastructure/test_entry_verify.sh
#
# Needs ansible (pip install ansible). No root, nothing touched outside a
# temporary directory: every command the checks run (awg, ip, ipset,
# iptables, sysctl, systemctl, sshd, ufw) is a stub answering from a fixture.
#
# fixtures/good is an entry that is right in every checked respect: it must
# produce no findings. Each case below breaks it in one place and must
# produce exactly one finding, the expected one. A check that never fires
# fails here, which is the point: a clean report is only worth something if
# every check in it has been seen to fail.
#
# fixtures/good also guards the two parsing traps found while writing the
# checks: its awg0 peer section carries a `jc:` line (the peer list must be
# cut off before parsing), and its awg1 prints a header as a range `N-N`.

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DIR="$HERE/entry-verify"
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
    local extra=()
    [[ -f $1/extra.yml ]] && extra=(-e "@$1/extra.yml")
    if ! ansible-playbook "$DIR/play.yml" \
            -e "stub_dir=$DIR/stubs" -e "fixture=$1" -e "out=$2" "${extra[@]}" \
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

case_ good                ""                                                 ':'
case_ header-range        ""                                                 'sed -i "s/^  h1: .*/  h1: 1163059398-1163059398/" awg_show_awg0'

case_ awg0-jc             "awg0: jc is 4, want 3"                            'sed -i "s/^  jc: 3$/  jc: 4/" awg_show_awg0'
case_ awg0-s1-default     "awg0: s1 is 0, want 72"                           'sed -i "/^  s1: /d" awg_show_awg0'
case_ awg0-h4             "awg0: h4 is 4, want 133143559"                    'sed -i "/^  h4: /d" awg_show_awg0'
case_ awg0-key            "awg0: public key is"                              'sed -i "s/^  public key: .*/  public key: WFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFg=/" awg_show_awg0'
case_ awg0-port           "awg0: listening port is 8444, want 8443"          'sed -i "s/^  listening port: 8443/  listening port: 8444/" awg_show_awg0'
case_ awg0-down           "awg0: interface not up"                           'echo awg1 > awg_interfaces'
case_ link-key            "awg1: public key is"                              'sed -i "s/^  public key: .*/  public key: WFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFg=/" awg_show_awg1'
case_ link-stale          "awg1: no handshake in the last 180 s"             'echo 200 > awg_hs_age_awg1'
case_ rule-99-missing     "ip rule 99"                                       'sed -i "/^99:/d" ip_rule'
case_ rule-100-twice      "ip rule 100"                                      'sed -i "/^100:/p" ip_rule'
case_ table-200-empty     "table 200 has no default route"                   ': > ip_route_200'
case_ ipset-short         "ipset ru_nets: 7999 entries"                      'sed -i "s/Number of entries: .*/Number of entries: 7999/" ipset_ru_nets'
case_ ipset-missing       "ipset ru_nets: missing entries"                   'rm ipset_ru_nets'
case_ no-isolation        "FORWARD: no awg0 -> awg0 DROP"                    'sed -i "/-o awg0 -j DROP/d" iptables_forward'
case_ no-isolation-dst    "FORWARD: no DROP of awg0 -> 10.88.88.0/23"        'sed -i "/-d 10.88.88.0\/23 -i awg0 -j DROP/d" iptables_forward'
case_ isolation-dst-late  "FORWARD: no DROP of awg0 -> 10.88.88.0/23"        'sed -i "/-d 10.88.88.0\/23/d" iptables_forward; echo "-A FORWARD -d 10.88.88.0/23 -i awg0 -j DROP" >> iptables_forward'
case_ isolation-dst-wide  "FORWARD: no DROP of awg0 -> 10.88.88.0/23"        'sed -i "s#-d 10.88.88.0/23 #-d 10.88.0.0/16 #" iptables_forward'
case_ isolation-dst-order ""                                                 'sed -i "s#-d 10.88.88.0/23 -i awg0#-i awg0 -d 10.88.88.0/23#" iptables_forward'
case_ no-masquerade       "nat: no MASQUERADE out of eth0"                   'sed -i "/-o eth0/d" iptables_nat'
case_ rp-filter-strict    "rp_filter (all) = 1, want 2"                      'sed -i "s/rp_filter=2/rp_filter=1/" sysctl'
case_ no-bbr              "tcp_congestion_control = cubic, want bbr"         'sed -i "s/=bbr/=cubic/" sysctl'
case_ conntrack-a         "nf_conntrack_max = 65536, want >= 262144"         'sed -i "s/conntrack_max=.*/conntrack_max=65536/" sysctl'
case_ unit-inactive       "unit sov-split: inactive enabled"                 'sed -i "s/^sov-split=.*/sov-split=inactive enabled/" units'
case_ unit-disabled       "unit sovrn-trial-net: active disabled"            'sed -i "s/^sovrn-trial-net=.*/sovrn-trial-net=active disabled/" units'
case_ sshd-root           "sshd: permitrootlogin is yes, want no"            'sed -i "s/^permitrootlogin no/permitrootlogin yes/" sshd_T'
case_ sshd-password       "sshd: passwordauthentication is unset"            'sed -i "/^passwordauthentication/d" sshd_T'
case_ ufw-off             "ufw: Status: inactive"                            'echo "Status: inactive" > ufw_status'
case_ hop-port-in-list    ""                                                 'printf "entry_link:\n  if: awg1\n  port: 51821\n  hop_ports: [51821, 51831, 51841]\n  public_key: \"QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI=\"\n" > extra.yml; echo "sovrn-link-hop.timer=active enabled" >> units; sed -i "s/^  listening port: 51821/  listening port: 51841/" awg_show_awg1'
case_ hop-port-off-list   "awg1: listening port is 51900, want 51821"        'printf "entry_link:\n  if: awg1\n  port: 51821\n  hop_ports: [51821, 51831, 51841]\n  public_key: \"QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI=\"\n" > extra.yml; echo "sovrn-link-hop.timer=active enabled" >> units; sed -i "s/^  listening port: 51821/  listening port: 51900/" awg_show_awg1'
case_ hop-timer-stopped   "unit sovrn-link-hop.timer: inactive enabled"      'printf "entry_link:\n  if: awg1\n  port: 51821\n  hop_ports: [51821, 51831, 51841]\n  public_key: \"QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI=\"\n" > extra.yml; echo "sovrn-link-hop.timer=active enabled" >> units; sed -i "s/^sovrn-link-hop.timer=.*/sovrn-link-hop.timer=inactive enabled/" units'
case_ no-hop-port-moved   "awg1: listening port is 51841, want 51821"        'sed -i "s/^  listening port: 51821/  listening port: 51841/" awg_show_awg1'

echo
echo "$pass passed, $fail failed"
[[ $fail -eq 0 ]]
