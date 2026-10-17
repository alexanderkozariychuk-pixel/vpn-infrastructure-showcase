# Entry node — specification

What the entry node is made of, layer by layer, as found on entry A on
2026-10-12 (`tools/node-inventory.sh`, report kept off the repository). It is
the reference for two things: the Ansible roles that build an entry, and the
check that a newly built entry B matches A where it must and differs where it
must.

Addresses are written as roles (`<entry-A>`, `<exit>`), not IPs.

## Why B has to match A

A client's config carries four things that belong to the entry: its
**address** (`n1.sov3r3ign.com:8443`), the server's **public key**, the
client's **preshared key** and the **obfuscation parameters**. For a client to
move from A to B by a DNS change alone, B must present the same key, the same
parameters, the same port and the same set of peers. Everything below is
marked accordingly:

- **same** — must be identical on A and B;
- **own** — each entry has its own value;
- **not carried** — present on A, not built on B (and to be removed from A).

## Layers

| Layer | On A | B |
|---|---|---|
| OS | Ubuntu 24.04, kernel 6.8 generic, UTC, timesyncd, 2 GB swap file | same release; own host |
| AmneziaWG | `amneziawg`, `amneziawg-tools`, `amneziawg-dkms` 1.0.0 from the Amnezia PPA; `linux-headers-generic` installed so a kernel from unattended upgrades gets its module built | same |
| `awg0` — clients | port **8443/udp**; `10.88.88.1/24` + `10.88.89.1/24` (the second added by `sovrn-trial-net`); obfuscation `Jc 3, Jmin 50, Jmax 1000, S1 72, S2 146, S3 0, S4 0`, `H1–H4` = `AWG_PARAMS` in `pwa/services/provisioner.py`; no MTU set (clients use 1300) | **same** — including the private key (key-id `b15a1462aaac`) |
| `awg0` PostUp | `FORWARD -i awg0 ACCEPT`; `nat POSTROUTING -o eth0 MASQUERADE` (RU-bound traffic leaves locally) | same, interface name of B's uplink, **plus** the two isolation DROPs first (below, "Client isolation"). Written into `awg0.conf` when the file is created; the file is never rewritten after that, so on B the second DROP was added by hand (2026-10-17) |
| `awg0` peers | 58: portal-issued (pool `.42–.199`, trial `.10–.250` of `.89`) and hand-issued (below `.42`, `.200+`) | portal peers **same**, kept in step by the portal; hand-issued: not carried (moving to the portal or switched off) |
| `awg1` — link to exit | port 51821; `10.77.77.2/30`; `Table = off`; MTU 1300; own obfuscation; peer = exit `:51822`, keepalive 25, `AdvancedSecurity = on` (the default, also on the exit side) | **own**: a separate link — own keys, own /30, own port, to a separate interface on the exit (`awg2`), so the live `awg0` on the exit is never touched |
| `awg1` PostUp | default route via `10.77.77.1` into table **200**; `nat POSTROUTING -o awg1 MASQUERADE` — the exit sees one address per entry, which is what lets two entries share an exit | same pattern, B's own addresses |
| Split tunnel | ipset `ru_nets` (hash:net, ~11.4k RU prefixes from RIPE + Yandex/VK/Gosuslugi ranges), restored at boot from `/etc/sovereign/ru_nets.ipset` by `sov-split.service`; mangle marks client traffic to `ru_nets` with `0x64`; `ip rule 99 fwmark 0x64 → main`; `ip rule 100 from 10.88.88.0/24 → 200`; refreshed Sundays 04:00 UTC (`sov-update-ru-list.sh`, atomic `ipset swap`, floor of 8000 prefixes) | same; `ip rule 100` is set by `sov-split-tunnel.sh` next to rule 99, not by `rc.local`; the update script also works on a node with no set yet (first run) |
| Trial subnet | `sovrn-trial-net` + unit: `10.88.89.0/24` on awg0, `ip rule 101 → 200`, chain `SOVRN-TRIAL` (no reach into client subnets, no port 25, ≤150 new connections per device), shared bandwidth ceiling; kill switch in `/etc/sovereign/trial.state` | same, except the kill switch: the role leaves it alone (operational state), a missing file reads as `off` and drops all trial traffic — set by hand after the build, to whatever A has (`sovrn-trial-net on`/`off`) |
| sysctl | `ip_forward=1` (`awg.conf`), `rp_filter=2` (Ubuntu's own `10-network-security.conf`), bbr (`60-tcp-congestion-control.conf`, from the provider's image), qdisc `fq_codel` (systemd default), `ipv6 forwarding=1` (`awg.conf`), `nf_conntrack_max` 65536 — read 2026-10-13 | `awg.conf` sets `ip_forward`, `rp_filter=2` and bbr itself, since the routing depends on them; `nf_conntrack_max` 262144 (module loaded from `modules-load.d`); IPv6 forwarding **not carried** — awg0 has no IPv6, and forwarding makes the kernel ignore router advertisements on the uplink; ufw's own sysctl file sets no `rp_filter` on A (checked 2026-10-13), so it is left alone |
| Firewall | ufw: in 22/tcp, 8443/udp, link port/udp; default input DROP, forward ACCEPT | same, B's link port |
| Users | `vpnadmin` (sudo, workstation key); `pwa-provisioner` (key `from=<portal>,restrict`, sudo only for the four wrappers); `sovmon` (key `command=sov-probe,from=<am1>,restrict`) | same |
| Node scripts | `pwa-add-peer`, `pwa-del-peer`, `pwa-awg-show`, `pwa-logs` (`infrastructure/wrappers/`); `sovrn-trial-net` (`infrastructure/trial/`); `sov-probe` (`infrastructure/monitoring/`); split tunnel (`infrastructure/entry/as-found-2026-10-12/`) | same |
| sshd | key only, no root, no passwords | same, and `00-hardening.conf` with `X11Forwarding no` |
| fail2ban | `sshd` jail, 6 tries, 10 min ban, ipset action | same |
| Updates | unattended-upgrades from Ubuntu origins, no automatic reboot | same |

The as-found copies are byte for byte what A runs and are excluded from
shellcheck. The split-tunnel files now live, linted and amended, in
`infrastructure/ansible/roles/entry/files/`; the as-found copies stay as the
record of what A had on 2026-10-12.

## Client isolation

Clients must not reach each other's devices. Two rules, both inserted first
in FORWARD by `awg0`'s PostUp:

```
-A FORWARD -d 10.88.88.0/23 -i awg0 -j DROP     # by destination: the one that works
-A FORWARD -i awg0 -o awg0 -j DROP              # by interface: a peer outside the client nets
```

Why by destination (modelled on B with two phones, 2026-10-17):

- **`awg1` up.** Rule 100 sends everything from `10.88.88.0/24` to table 200,
  which holds only the default via the exit, so a packet for another client
  leaves through `awg1`, masqueraded. The exit has no route to the client
  nets (each link's AllowedIPs is the entry's `/32`) and sends it out of its
  uplink to the provider's gateway. Nothing comes back: clients do not reach
  each other, but `-o awg0` never matches, and private-address packets leak
  past the exit.
- **`awg1` down** (stopped, restarting, not up after a boot): table 200 is
  empty, the lookup falls through to main, and the packet goes back out of
  `awg0` to the neighbour. ufw's forward chains accept it (new TCP/UDP,
  established, ICMP echo), long before the `-i awg0 -j ACCEPT`. Measured with
  the DROPs removed: both phones answered each other.
- **`-d 10.88.88.0/23`** dropped the packet on the way in in both states — the
  counter rose by exactly what tcpdump saw, no answers, internet and the split
  unchanged — and is back after a reboot from `awg0.conf`.

Both rules must sit above ufw's chains; the trial chain's jump may sit above
them (it drops trial → client traffic itself). `roles/entry/tasks/verify.yml`
checks both and the position of the first. On an existing entry the lines are
added by `tools/once/2026-10-17-client-isolation.sh` (`check`, `apply`,
`rollback`), which never restarts `awg0`.

Separate finding from the same model: with `awg1` down, clients' internet
traffic leaves from the entry's own address (table 200 is empty, main's
default route takes over) — no kill switch for paying clients. Not fixed here.

## Secrets an entry needs, and where they come from

| Secret | A | B |
|---|---|---|
| `awg0` private key | on A | copied from A (vault) — the one thing that makes B a drop-in |
| client PSKs and public keys | in `awg0.conf` and, encrypted, in the portal DB | written by the portal to both entries |
| link keys, link PSK | A's own | generated for B; the exit's `awg2` gets the other half |
| `pwa-provisioner`, `sovmon`, admin public keys | — | public halves only |

## Found on A, to fix there

1. **A headerless peer fragment in `awg0.conf`.** Lines 219–220 hold a
   `PresharedKey` (fingerprint `d4fb054e`, matching no running peer) and
   `AllowedIPs = 10.88.88.49/32` with no `[Peer]` or `PublicKey` of their
   own, inside the block of `client18` (`.48`). The running interface is
   correct; only the file is wrong. On the next start of `awg0` from the file,
   `client18` would most likely get the stray PSK — a repeated key overwrites
   the first in the WireGuard parser; not yet confirmed on this
   amneziawg-tools build — and stop connecting. `.49`'s own block comes later
   and keeps its address.
   **Deferred (2026-10-12) to the hand-issued peers review**, a few days out:
   no client is affected until `awg0` is restarted, and removing `client18`
   through `pwa-del-peer` takes the fragment with it (the wrapper drops a
   block up to the next `[Peer]`). If `awg0` has to restart first, run
   `tools/once/2026-10-12-awg0-orphan-psk.sh` before it, then
   `tools/awg-conf-check.sh`.
2. **`ip rule 100` lives in `/etc/rc.local`** (run at boot by
   `rc-local.service`), next to a `table 200` default route that also comes
   from `awg1`'s PostUp. It survives a reboot, but in a place nobody looks; on
   B both rules go where the rest of the policy routing is.
3. Docker is installed and running on the entry, its chains first in FORWARD.
   Docker is never co-located with a VPN node; to be removed from A.

## Not carried to B (and to be removed from A)

`awg-ru.conf` (a dead link config); eleven `awg0.conf.bak*` holding keys of
long-removed peers; `*-credentials.txt` and an empty `privatekey` from May;
`udp2raw`, `rar`, `unrar`; `prometheus-node-exporter` and its timers (its
Grafana host is gone); an nginx logrotate entry from the old portal; a sudoers
line for a non-existent `ubuntu` user; `beget-agent` (the provider's own).

## Comparing B with A

A is not managed by Ansible, not even with `--check`: it carries paying
clients and is changed by hand. After B is built, both are inventoried the
same way and the reports compared:

```bash
ssh sov-entry   'sudo bash -s' < tools/node-inventory.sh > entry-A.txt
ssh sov-entry-b 'sudo bash -s' < tools/node-inventory.sh > entry-B.txt
diff entry-A.txt entry-B.txt
```

Every difference should be one of these; anything else is a defect in the
roles or in this specification.

- **own** — host name, addresses, link keys and port, uplink name.
- The two isolation DROPs ("Client isolation") on B only, until A gets them.
- sysctl: on B `rp_filter`, bbr and `nf_conntrack_max` (262144) come from
  `/etc/sysctl.d/awg.conf` and `modules-load.d/sovereign.conf`; IPv6
  forwarding is on A only.
- `ip rule 100` set by `sov-split-tunnel.sh` on B, by `rc.local` on A; A's
  `rc.local` also adds a second `table 200` route.
- Split-tunnel scripts: B runs the linted versions (temp files, first-run
  support, rule 100); the unit and cron file differ by a header comment.
- `sshd_config.d/00-hardening.conf` on B only; the effective `sshd -T` values
  should already agree.
- Admin user `sovadmin` on B, `vpnadmin` on A; sudoers drop-in names differ.
- Amnezia PPA source file name (`amnezia-ppa.sources` on B,
  `add-apt-repository`'s on A).
- Everything under "Not carried", Docker and `beget-agent`: on A only.
  B's provider image shipped Docker too; the role purges it and reboots
  once (`roles/common/tasks/no-containers.yml`).
- `net.core.default_qdisc`: `fq` on B (set by the provider image), `fq_codel`
  on A. Kept: `fq` is the pacing qdisc bbr is designed for. The trial
  script sets its own leaf qdiscs either way.
- AmneziaWG build: B gets the current PPA build (2026-08/09), A runs the
  one installed in 2026-02/03. Same parameters, same key; that a client
  configured for A connects to B is what the warm-up through `n2` proves.
  `awg showconf` on the newer tools also prints parameters left at their
  defaults (`RekeyAfterTime = 0` and so on).
- Users: `sovmon` has `/bin/bash` on B, `/bin/sh` on A (its key is
  `command=`-restricted either way). Root has no `authorized_keys` on either.
- Provider-image leftovers on B not touched by the roles: `snapd`,
  `gpu-manager`, `thermald`, `upower`, `fwupd`.

First diff, 2026-10-13: 738 lines, every one accounted for by this list, and
`awg0 key-id b15a1462aaac, listen 8443` on both.
