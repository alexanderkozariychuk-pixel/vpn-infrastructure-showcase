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
| `awg0` PostUp | `FORWARD -i awg0 ACCEPT`; `nat POSTROUTING -o eth0 MASQUERADE` (RU-bound traffic leaves locally) | same, interface name of B's uplink |
| `awg0` peers | 58: portal-issued (pool `.42–.199`, trial `.10–.250` of `.89`) and hand-issued (below `.42`, `.200+`) | portal peers **same**, kept in step by the portal; hand-issued: not carried (moving to the portal or switched off) |
| `awg1` — link to exit | port 51821; `10.77.77.2/30`; `Table = off`; MTU 1300; own obfuscation; peer = exit `:51822`, keepalive 25, `AdvancedSecurity = on` (the default, also on the exit side) | **own**: a separate link — own keys, own /30, own port, to a separate interface on the exit (`awg2`), so the live `awg0` on the exit is never touched |
| `awg1` PostUp | default route via `10.77.77.1` into table **200**; `nat POSTROUTING -o awg1 MASQUERADE` — the exit sees one address per entry, which is what lets two entries share an exit | same pattern, B's own addresses |
| Split tunnel | ipset `ru_nets` (hash:net, ~11.4k RU prefixes from RIPE + Yandex/VK/Gosuslugi ranges), restored at boot from `/etc/sovereign/ru_nets.ipset` by `sov-split.service`; mangle marks client traffic to `ru_nets` with `0x64`; `ip rule 99 fwmark 0x64 → main`; `ip rule 100 from 10.88.88.0/24 → 200`; refreshed Sundays 04:00 (`sov-update-ru-list.sh`, atomic `ipset swap`, floor of 8000 prefixes) | same |
| Trial subnet | `sovrn-trial-net` + unit: `10.88.89.0/24` on awg0, `ip rule 101 → 200`, chain `SOVRN-TRIAL` (no reach into client subnets, no port 25, ≤150 new connections per device), shared bandwidth ceiling | same |
| sysctl | `ip_forward=1`, `rp_filter=2` (loose — required by the policy routing), bbr | same, plus `nf_conntrack_max` raised (A has 65536) |
| Firewall | ufw: in 22/tcp, 8443/udp, link port/udp; default input DROP, forward ACCEPT | same, B's link port |
| Users | `vpnadmin` (sudo, workstation key); `pwa-provisioner` (key `from=<portal>,restrict`, sudo only for the four wrappers); `sovmon` (key `command=sov-probe,from=<am1>,restrict`) | same |
| Node scripts | `pwa-add-peer`, `pwa-del-peer`, `pwa-awg-show`, `pwa-logs` (`infrastructure/wrappers/`); `sovrn-trial-net` (`infrastructure/trial/`); `sov-probe` (`infrastructure/monitoring/`); split tunnel (`infrastructure/entry/as-found-2026-10-12/`) | same |
| sshd | key only, no root, no passwords | same, and `00-hardening.conf` with `X11Forwarding no` |
| fail2ban | `sshd` jail, 6 tries, 10 min ban, ipset action | same |
| Updates | unattended-upgrades from Ubuntu origins, no automatic reboot | same |

The as-found copies are byte for byte what the node runs; they are excluded
from shellcheck and become linted role files when Ansible takes them over.

## Secrets an entry needs, and where they come from

| Secret | A | B |
|---|---|---|
| `awg0` private key | on A | copied from A (vault) — the one thing that makes B a drop-in |
| client PSKs and public keys | in `awg0.conf` and, encrypted, in the portal DB | written by the portal to both entries |
| link keys, link PSK | A's own | generated for B; the exit's `awg2` gets the other half |
| `pwa-provisioner`, `sovmon`, admin public keys | — | public halves only |

## Found on A, to fix there

1. **A broken peer block in `awg0.conf`.** Lines 219–220 hold a
   `PresharedKey` and `AllowedIPs = 10.88.88.49/32` with no `[Peer]` or
   `PublicKey` of their own, so the parser folds them into the previous peer
   (`.48`): on the next restart that peer would get a second PSK — the last
   one wins — and an extra address. The running interface is correct; the
   file is not. Fix the file, not the runtime.
2. **`ip rule 100` is created by something not yet found.** Neither the units
   nor the PostUp lines on A create it, yet it is present. If it lives only at
   runtime, a reboot would send paying clients' traffic out through the RU
   uplink instead of the exit. To be traced before any restart.
3. Docker is installed and running on the entry, its chains first in FORWARD.
   Docker is never co-located with a VPN node; to be removed from A.

## Not carried to B (and to be removed from A)

`awg-ru.conf` (a dead link config); eleven `awg0.conf.bak*` holding keys of
long-removed peers; `*-credentials.txt` and an empty `privatekey` from May;
`udp2raw`, `rar`, `unrar`; `prometheus-node-exporter` and its timers (its
Grafana host is gone); an nginx logrotate entry from the old portal; a sudoers
line for a non-existent `ubuntu` user; `beget-agent` (the provider's own).
