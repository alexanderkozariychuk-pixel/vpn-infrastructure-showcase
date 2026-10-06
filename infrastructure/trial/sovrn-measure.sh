#!/usr/bin/env bash
# sovrn-measure.sh — read-only load sample: traffic per interface, CPU, peers.
# Changes nothing on the node.
#   bash sovrn-measure.sh [seconds]          default 60
#   IFACES="ens3 awg0" bash sovrn-measure.sh  on the exit node
DUR="${1:-60}"; STEP=5
read -r -a IFS_LIST <<< "${IFACES:-eth0 awg0 awg1}"

bytes() { sed 's/:/ /' /proc/net/dev | awk -v i="$1" '$1 == i { print $2, $10 }'; }
cpu()   { awk '/^cpu / { t = 0; for (k = 2; k <= 9; k++) t += $k; print t, $5 + $6, $8, $9 }' /proc/stat; }

echo "host $(hostname)  cores $(nproc)  $(date '+%F %T')  sample ${DUR}s"
free -m | awk '/^Mem/ { print "mem used " $3 " / " $2 " MiB" }'
if command -v awg >/dev/null; then
    for i in "${IFS_LIST[@]}"; do
        [[ "$i" == awg* ]] || continue
        sudo awg show "$i" latest-handshakes 2>/dev/null | awk -v now="$(date +%s)" -v i="$i" \
            '$2 > 0 && now - $2 < 180 { n++ } END { print i ": peers with handshake < 3 min: " n + 0 }'
    done
fi

declare -A prx ptx sumrx sumtx maxrx maxtx
for i in "${IFS_LIST[@]}"; do read -r "prx[$i]" "ptx[$i]" < <(bytes "$i"); done
read -r ct ci cs cst < <(cpu)

printf '\n%-8s' time; for i in "${IFS_LIST[@]}"; do printf '%18s' "$i rx/tx Mbit"; done; printf '%26s\n' "cpu busy/softirq/steal"
n=0
while (( n * STEP < DUR )); do
    sleep "$STEP"; n=$((n + 1))
    printf '%-8s' "$(date +%T)"
    for i in "${IFS_LIST[@]}"; do
        read -r r t < <(bytes "$i")
        rr=$(( (r - prx[$i]) * 8 / STEP / 1000000 )); tt=$(( (t - ptx[$i]) * 8 / STEP / 1000000 ))
        prx[$i]=$r; ptx[$i]=$t
        sumrx[$i]=$(( ${sumrx[$i]:-0} + rr )); sumtx[$i]=$(( ${sumtx[$i]:-0} + tt ))
        (( rr > ${maxrx[$i]:-0} )) && maxrx[$i]=$rr; (( tt > ${maxtx[$i]:-0} )) && maxtx[$i]=$tt
        printf '%18s' "$rr / $tt"
    done
    read -r t2 i2 s2 st2 < <(cpu)
    dt=$((t2 - ct)); (( dt > 0 )) || dt=1
    printf '%26s\n' "$(( 100 - 100 * (i2 - ci) / dt ))% / $(( 100 * (s2 - cs) / dt ))% / $(( 100 * (st2 - cst) / dt ))%"
    ct=$t2; ci=$i2; cs=$s2; cst=$st2
done

echo; echo "summary over ${DUR}s (Mbit/s)"
for i in "${IFS_LIST[@]}"; do
    printf '  %-6s rx avg %4d peak %4d   tx avg %4d peak %4d\n' "$i" \
        $(( sumrx[$i] / n )) "${maxrx[$i]:-0}" $(( sumtx[$i] / n )) "${maxtx[$i]:-0}"
done
