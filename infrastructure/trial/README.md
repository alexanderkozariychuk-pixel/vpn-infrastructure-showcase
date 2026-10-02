# Trial subnet on the entry node

Trial clients get addresses in `10.88.89.0/24` — on the same `awg0`, the
same port 8443 and the same obfuscation as paying clients in
`10.88.88.0/24`, so a trial is the product that will later be bought. What
differs is applied by `sovrn-trial-net`:

| piece | why |
|---|---|
| `10.88.89.1/24` on `awg0` | the route back; `awg set` (used by `pwa-add-peer`) adds no routes |
| mangle mark + `ip rule 101 from 10.88.89.0/24 lookup 200` | the RU split. `sov-split-tunnel.sh` and `rc.local` match `10.88.88.0/24` only — without these, every trial packet would leave via `eth0` from a Russian address |
| chain `SOVRN-TRIAL`, jumped to first in `FORWARD` | kill switch; no reaching other clients; no SMTP; at most 150 new connections per address. Must sit before `-i awg0 -j ACCEPT`, which accepts everything from `awg0` |
| HTB on `awg0` egress, policer on its ingress | one ceiling for the whole trial pool (20 / 5 Mbit/s by default — set 2026-10-03 against an evening peak of 16 Mbit/s for all paying clients, until the port capacity is measured). Paying clients fall into the default class with no effective limit |

Nothing edits `awg0.conf`, `sov-split-tunnel.sh` or `rc.local`. Everything is
added alongside them by one systemd unit and removed by its `ExecStop`.

Files:

| file | installed as |
|---|---|
| `sovrn-trial-net` | `/usr/local/bin/sovrn-trial-net` |
| `sovrn-trial-net.service` | `/etc/systemd/system/sovrn-trial-net.service` |
| `../wrappers/pwa-add-peer`, `../wrappers/pwa-del-peer` | `/usr/local/bin/` — both accept the two client subnets |
| `snapshot.sh`, `capture.sh`, `rollback.sh` | run from a copy in the home directory |

`sovrn-measure.sh` (read-only) samples traffic per interface, CPU (busy,
softirq, steal) and active peers — how the defaults above were chosen, and
what to re-run before changing them. First reading, Saturday 2026-10-03 at
21:43 MSK: 15–16 active peers, 7–10 Mbit/s to clients on average, 16 at
peak, almost all of it foreign (`awg1 rx` ≈ `awg0 tx`); CPU 4–7 %, steal 0.

Limits live in `/etc/sovereign/trial.conf` (root-owned, not group/world
writable): `DOWN_RATE`, `UP_RATE` (`off` disables), `CONN_LIMIT`,
`LEAF_QDISC`. Change, then `systemctl restart sovrn-trial-net`.

Kill switch: `sovrn-trial-net off` / `on`. Persists in
`/etc/sovereign/trial.state`; a missing file reads as `off`.

## Install

Copy to the node:

```bash
ssh vpnadmin@<entry> mkdir -p sovrn-trial
scp -r infrastructure/trial infrastructure/wrappers/pwa-add-peer \
    infrastructure/wrappers/pwa-del-peer vpnadmin@<entry>:~/sovrn-trial/
```

On the node:

```bash
cd ~/sovrn-trial

# 0. Preflight — every line must look as described, or stop.
systemctl is-active awg-quick@awg0 awg-quick@awg1 sov-split   # active ×3
modinfo -F filename sch_htb sch_fq_codel act_police xt_connlimit  # four paths
sha256sum /usr/local/bin/pwa-add-peer /usr/local/bin/pwa-del-peer
# a8a59c0d023cedbfc9e5f5f990a8295300a3273cfe7ba5bb9363c8591f3023db  pwa-add-peer (2026-07-18)
# 7659000f5da132a1c976b56a2302c92161a99f23fb8f32ce51835311218e9dde  pwa-del-peer (2026-09-20)
ip -4 addr show awg0 | grep 10.88.89; ip rule | grep 10.88.89   # nothing
sudo awg show awg0 allowed-ips | grep -c '10\.88\.89\.'          # 0

# 1. Snapshot — before anything is installed.
sudo bash trial/snapshot.sh

# 2. Install.
sudo install -o root -g root -m 0755 pwa-add-peer pwa-del-peer /usr/local/bin/
sudo install -o root -g root -m 0755 trial/sovrn-trial-net /usr/local/bin/
sudo install -o root -g root -m 0644 trial/sovrn-trial-net.service /etc/systemd/system/
echo on | sudo tee /etc/sovereign/trial.state

# 3. Start. Prints its own check; every line must say ok.
sudo systemctl daemon-reload
sudo systemctl enable --now sovrn-trial-net
sudo sovrn-trial-net check
```

## Verify

1. A paying client (your own phone): sites open, the external address is the
   exit node, a speed test matches the one taken before step 3. The HTB root
   carries paying traffic too, through a class with no effective ceiling;
   this is the step that proves that.
2. A test trial peer: a copy of a working client config with a new key,
   `Address = 10.88.89.10/32`, added with
   `sudo pwa-add-peer <pub> <psk> 10.88.89.10/32 trial-test`.
   - external address is the exit node; a Russian service sees the entry's
     address (the split works);
   - a speed test tops out near `DOWN_RATE`;
   - `sudo sovrn-trial-net off` → the test client loses connectivity, the
     paying one does not; `on` → back;
   - `sudo tc -s class show dev awg0` — class `1:20` counts the test
     client's traffic, `1:10` everyone else's.
3. Remove the test peer: `sudo pwa-del-peer <pub>`.
4. At night, when a few seconds without tunnels costs little:
   `sudo systemctl restart awg-quick@awg0`, then
   `sudo sovrn-trial-net check` — `PartOf=` must have brought the trial
   subnet back with the interface.

## Rollback

```bash
sudo bash ~/sovrn-trial/trial/rollback.sh                       # refuses if trial peers exist
sudo bash ~/sovrn-trial/trial/rollback.sh --remove-trial-peers  # removes them first
```

It stops and disables the unit (whose `down` removes everything it added),
puts the snapshot's wrappers back, deletes the trial files, then captures
iptables, `ip rule`, table 200, `awg0`'s addresses and qdiscs again and diffs
them against the snapshot. It ends with `ROLLBACK OK` only when every file is
identical and the wrappers match their checksums. A difference is shown as a
diff; a Docker container restarted in between rewrites its own chains, so
read it before assuming the rollback failed.

If `up` fails at any step it removes what it had applied: a half-applied
subnet — routed, but without its ceiling — is worse than none.

## Tests

```bash
bash tests/infrastructure/test_wrappers.sh         # no root needed
sudo bash tests/infrastructure/test_trial_net.sh   # network namespaces
```

`test_trial_net.sh` builds the entry node as it was observed on 2026-10-02
(FORWARD, nat, mangle, `ip rule` 99/100, table 200 via `awg1`) in throwaway
namespaces, with a paying and a trial client, a "RU" host behind `eth0` and
an "exit" host behind `awg1`, and checks reachability end to end: before
install, after `up`, with the kill switch off and on, after a failed `up`,
and after rollback — including that rollback's diff is empty and that it
notices a leftover rule.

Each check was shown to fail when the code it guards is broken. The suite
caught all of these deliberate breakages:

| broken | caught by |
|---|---|
| no `ip rule 101` / no RU mark for trials | `check`, trial reachability |
| kill switch returns instead of dropping; missing state read as on | "cannot reach (switched off)" |
| jump appended instead of first in FORWARD; lateral drop removed | `check` |
| bandwidth filter matches the wrong subnet | class `1:20` byte counter |
| `down` leaves the chain or the address behind | snapshot comparison, rollback |
| no cleanup after a failed `up` | snapshot comparison, reachability |
| rollback skips the comparison / ignores trial peers | rollback tests |
| `pwa-add-peer`: config-only duplicate IP allowed, no restore after a runtime failure, substring IP match, leading zeros, trial subnet dropped | `test_wrappers.sh` |

Run against the node's current wrappers (`tests/infrastructure/fixtures`),
`test_wrappers.sh` also shows what the 2026-07-18 `pwa-add-peer` let
through: `10.88.88.042/32`, and keys and addresses present in the config but
not the runtime.

## Found while preparing this, not changed here

- `-A FORWARD -i awg0 -j ACCEPT` also forwards `awg0 → awg0`: paying clients
  can reach each other's devices. Trials are blocked from it by their chain;
  paying clients are not.
- `ip rule 100` exists only in `/etc/rc.local` (after `sleep 5`), and the
  default route in table 200 is added both there and by `awg1`'s PostUp.
  Harmless today; belongs in `sov-split-tunnel.sh`.
