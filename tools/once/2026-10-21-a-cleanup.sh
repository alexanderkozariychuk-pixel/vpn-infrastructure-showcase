#!/bin/bash
#
# One-off, 2026-10-21: entry A's leftovers out — docs/entry-spec.md, "Not
# carried to B (and to be removed from A)" and "Found on A", item 3 (Docker).
# A is changed by hand only; run on the node:
#
#   ssh sov-entry 'sudo -n true && sudo bash -s -- check'   < tools/once/2026-10-21-a-cleanup.sh
#   ssh sov-entry 'sudo -n true && sudo bash -s -- files'   < tools/once/2026-10-21-a-cleanup.sh
#   ssh sov-entry 'sudo -n true && sudo bash -s -- docker'  < tools/once/2026-10-21-a-cleanup.sh
#   ssh sov-entry 'sudo -n true && sudo bash -s -- rollback /root/sov-backup/cleanup-<stamp>' < ...
#
# check     read-only: what files and docker would do, and whether their
#           guards hold.
# files     moves the dead files into /root/sov-backup/cleanup-<stamp>/
#           (root only, paths kept), then purges node-exporter and the old
#           portal's nginx. Nothing is deleted: rollback moves the files back.
#           Shred that directory after a few quiet days — the copies of
#           awg0.conf in it hold every client's keys.
# docker    removes the old portal's volume, then Docker itself. No way back
#           for the volume: its dump is archived on the backup host
#           (journal, 2026-10-07). Docker's chains stay in FORWARD until the
#           next boot, doing nothing (no containers).
# rollback  files back from a backup directory; packages are listed to
#           reinstall by hand.
#
# Never touched: awg0.conf, awg1.conf, the running interfaces, ip rules,
# beget-agent (the provider's agent may serve the rescue console), sudoers,
# kernels (106 stays as a fallback), apt autoremove (it would take kernels).
# Prints no keys: files are only named and sized.
#
# Every apt-get and docker call reads /dev/null: under `bash -s` the script
# itself is stdin, and a command that reads it eats the rest of the script.
set -uo pipefail

ROOT=${SOV_ROOT:-}                 # tests run against a scratch tree
D=$ROOT/etc/amnezia/amneziawg
BACKUP_ROOT=$ROOT/root/sov-backup
VOLUME=pwa_postgres_data
PKGS=(prometheus-node-exporter prometheus-node-exporter-collectors nginx nginx-common)
DOCKER_PKGS=(docker.io docker-compose-v2 containerd)

die() { echo "STOP: $*"; exit 1; }

# The dead files, by name. Copies of awg0.conf/awg1.conf hold keys; so do the
# credentials files and params (the install script's state: the server key).
plan_files() {
    FILES=()
    local f
    shopt -s nullglob
    for f in "$D"/awg0.conf.bak* "$D"/awg1.conf.bak* "$D"/awg-ru.conf \
             "$D"/awg0-server-credentials.txt "$D"/awg1-client-credentials.txt \
             "$D"/params "$D"/privatekey \
             "$ROOT"/etc/udp2raw_client.conf "$ROOT"/usr/local/bin/udp2raw; do
        [[ -e $f ]] && FILES+=("$f")
    done
    shopt -u nullglob
}

# Each guard is a reason not to touch something that is still in use.
guard_files() {
    [[ -f $D/awg0.conf && -f $D/awg1.conf ]] || die "awg0.conf or awg1.conf missing — wrong host?"
    awg show awg0 peers >/dev/null 2>&1 || die "awg0 is not running"
    if [[ -e $D/privatekey && -s $D/privatekey ]]; then die "$D/privatekey is not empty"; fi
    if pgrep -x udp2raw >/dev/null; then die "udp2raw is running"; fi
    # node-exporter is not guarded: it runs, and nothing reads it (its Grafana
    # host is gone, its ufw rule was removed 2026-10-07). Running for nobody
    # is the reason it goes; apt stops it.
    local u
    for u in awg-quick@awg-ru nginx; do
        if systemctl is-active --quiet "$u"; then die "$u is active"; fi
    done
    if ss -ltn 2>/dev/null | grep -qE ':(80|443)\s'; then die "something listens on 80/443"; fi
}

guard_docker() {
    command -v docker >/dev/null || { DOCKER_GONE=1; return; }
    DOCKER_GONE=0
    local c v
    c=$(docker ps -aq </dev/null 2>&1) || die "docker ps failed: $c"
    [[ -z $c ]] || die "containers exist: $(docker ps -a --format '{{.Names}}' </dev/null | tr '\n' ' ')"
    v=$(docker volume ls -q </dev/null 2>&1) || die "docker volume ls failed: $v"
    [[ -z $v || $v == "$VOLUME" ]] || die "volumes other than $VOLUME: $(echo "$v" | tr '\n' ' ')"
    VOLUMES=$v
}

installed() { dpkg-query -W -f='${Status}\n' "$1" 2>/dev/null | grep -q '^install ok installed$'; }

show_state() {
    echo "== awg0 peers running: $(awg show awg0 peers | wc -l)"
    echo "== FORWARD (head)"; iptables -S FORWARD | head -6
    echo "== links"; awg show awg1 latest-handshakes | awk '{print "awg1", systime()-$2 " s"}'
}

check() {
    plan_files
    echo "== files would move (${#FILES[@]}):"
    local f p
    for f in "${FILES[@]}"; do printf '  %8s  %s\n' "$(stat -c %s "$f")" "${f#"$ROOT"}"; done
    echo "== packages files would purge:"
    for p in "${PKGS[@]}"; do installed "$p" && echo "  $p"; done
    echo "== files guards:"
    ( guard_files && echo "  OK" )
    echo "== docker:"
    ( guard_docker
      if (( DOCKER_GONE )); then echo "  not installed"; exit 0; fi
      echo "  volume to remove: ${VOLUMES:-(none)}"
      for p in "${DOCKER_PKGS[@]}"; do installed "$p" && echo "  purge $p"; done
      echo "  guards OK" )
    show_state
}

files() {
    guard_files
    plan_files
    local stamp dir f p purge=()
    stamp=$(date +%Y%m%d-%H%M%S)
    dir=$BACKUP_ROOT/cleanup-$stamp
    umask 077
    mkdir -p "$dir" || die "cannot create $dir"
    chmod 700 "$BACKUP_ROOT" "$dir"
    for f in "${FILES[@]}"; do
        mkdir -p "$dir$(dirname "${f#"$ROOT"}")"
        mv -- "$f" "$dir${f#"$ROOT"}" || die "could not move $f (moved so far are in $dir)"
    done
    echo "files: moved ${#FILES[@]} into $dir"
    [[ -d $ROOT/etc/nginx ]] && cp -a "$ROOT/etc/nginx" "$dir/etc-nginx"
    for p in "${PKGS[@]}"; do installed "$p" && purge+=("$p"); done
    if (( ${#purge[@]} )); then
        printf '%s\n' "${purge[@]}" > "$dir/purged-packages"
        DEBIAN_FRONTEND=noninteractive apt-get purge -y -q "${purge[@]}" </dev/null >"$dir/apt-purge.log" 2>&1 \
            || die "apt-get purge failed, see $dir/apt-purge.log"
        echo "packages: purged ${purge[*]}"
    else
        echo "packages: nothing to purge"
    fi
    echo "backup: $dir"
    show_state
}

docker_out() {
    guard_docker
    (( DOCKER_GONE )) && { echo "docker: not installed"; return; }
    local p purge=()
    if [[ -n $VOLUMES ]]; then
        docker volume rm "$VOLUME" </dev/null >/dev/null || die "could not remove volume $VOLUME"
        echo "docker: volume $VOLUME removed"
    fi
    for p in "${DOCKER_PKGS[@]}"; do installed "$p" && purge+=("$p"); done
    systemctl disable --now docker.socket docker.service containerd.service >/dev/null 2>&1
    DEBIAN_FRONTEND=noninteractive apt-get purge -y -q "${purge[@]}" </dev/null >/dev/null 2>&1 \
        || die "apt-get purge ${purge[*]} failed"
    rm -rf -- "$ROOT/var/lib/docker" "$ROOT/var/lib/containerd"
    echo "docker: purged ${purge[*]}; /var/lib/docker and /var/lib/containerd removed"
    show_state
}

rollback() {
    local dir=${1:-} f n=0
    [[ -n $dir && -d $dir/etc ]] || die "usage: rollback <backup dir from 'files'>"
    while IFS= read -r -d '' f; do
        mv -- "$f" "$ROOT${f#"$dir"}" && n=$((n + 1))
    done < <(find "$dir/etc" "$dir/usr" -type f -print0 2>/dev/null)
    echo "files: moved $n back from $dir"
    [[ -f $dir/purged-packages ]] && echo "packages to reinstall by hand: $(tr '\n' ' ' < "$dir/purged-packages")"
    show_state
}

case "${1:-check}" in
    check)    check ;;
    files)    files ;;
    docker)   docker_out ;;
    rollback) rollback "${2:-}" ;;
    *)        die "usage: check | files | docker | rollback <dir>" ;;
esac
true
