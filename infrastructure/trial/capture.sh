# shellcheck shell=bash
# capture.sh — sourced by snapshot.sh and rollback.sh. Both must capture the
# same things in the same way, or the comparison after a rollback means
# nothing.
#
# Everything is normalised to drop what changes without anyone changing
# anything: packet counters, the timestamps iptables-save writes, interface
# indexes (a restarted awg0 gets a new one).

capture_state() {
    local iface="$1" out="$2"

    iptables-save \
        | grep -v '^#' \
        | sed -E 's/\[[0-9]+:[0-9]+\]//' \
        > "$out/iptables.rules"

    ip rule show > "$out/ip-rule"
    ip route show table 200 > "$out/table-200" 2>&1 || true
    ip -4 addr show dev "$iface" | sed -E 's/^[0-9]+: //' > "$out/addr-$iface"
    tc qdisc show dev "$iface" | sed -E 's/ refcnt [0-9]+//' > "$out/tc-qdisc-$iface"
}

compare_state() {
    local snap="$1" now="$2" bad=0 f
    for f in iptables.rules ip-rule table-200 "addr-$3" "tc-qdisc-$3"; do
        if diff -u "$snap/$f" "$now/$f" > "$now/$f.diff"; then
            printf '  %-22s identical\n' "$f"
        else
            printf '  %-22s DIFFERS\n' "$f"
            cat "$now/$f.diff"
            bad=1
        fi
    done
    return "$bad"
}
