# Operational Runbook

Incident response procedures for the Sovereign VPN infrastructure.

Every procedure here comes from a real production incident. Each one is written
symptom-first, because that is how an incident actually starts: something is
broken and the cause is unknown. The full chronology of each incident, with the
wrong hypotheses included, is in [`PROJECT-JOURNAL.md`](../PROJECT-JOURNAL.md).

For client-side installation and setup problems, see
[`troubleshooting.md`](troubleshooting.md). This document is for the
infrastructure.

---

## Operating principles

These were learned by violating them.

**Measure, don't reason.** Every hypothesis gets killed by a command, not by an
argument. Four plausible explanations were ruled out in the September 2026
outage before the packet capture showed what was actually happening — and the
capture contradicted all four.

**Nothing is done until it survives a reboot.** Four consecutive incidents
traced to the same root cause: state that existed only at runtime. A peer added
with `awg set` but never written to the config, an `iptables` rule added by
hand, a kernel module installed with `make install` instead of DKMS. Each
worked perfectly until the next boot.

**"No errors in the log" is not "it works."** A Grafana dashboard provisioned
cleanly, logged success, and displayed nothing. An Alertmanager config passed
`amtool check-config` and the service still would not start. Open the thing and
look at it.

**When the box is healthy from inside, diagnose from outside.** A server can
have a live interface, 0% packet loss outbound, and every service listening —
and still be unreachable. The evidence for that case does not exist on the
machine.

**Check the runtime, the config, and the database — they disagree.** A tunnel
can be up while its systemd unit is `failed`. A firewall can be `enabled` with
an empty rules file. Verify the layer that actually serves traffic, then verify
that it can be reproduced from disk.

---

## Triage index

| Symptom | Section |
|---|---|
| Handshake succeeds, traffic does not pass | [1](#1-handshake-succeeds-traffic-does-not-pass) |
| Tunnel down after reboot or kernel upgrade | [2](#2-tunnel-down-after-reboot-or-kernel-upgrade) |
| Node healthy inside, unreachable from outside | [3](#3-node-healthy-inside-unreachable-from-outside) |
| Locked out of SSH | [4](#4-locked-out-of-ssh) |
| Peers vanished after reboot | [5](#5-peers-vanished-after-reboot) |
| Monitoring reports success, shows nothing | [6](#6-monitoring-reports-success-shows-nothing) |
| Deploy succeeded, service wrong or 502 | [7](#7-deploy-succeeded-service-wrong-or-502) |

---

## 1. Handshake succeeds, traffic does not pass

The most common failure class, and the most misleading one: a live handshake
looks like a working tunnel. It is not. **The handshake does not depend on
`AllowedIPs`, on MTU, or on NAT — data does.** A green handshake only proves
the two ends can exchange small encrypted packets.

### Triage

Work down the layers. Stop at the first check that fails.

```bash
# 1. Which direction is broken? Watch the transfer counters, not the handshake.
sudo awg show

# A client whose "sent" climbs while "received" only ticks up every ~25s is
# receiving nothing but keepalives — the return path is gone. See 1a.
```

```bash
# 2. Does the runtime routing match the config?
sudo awg show awg0 allowed-ips
sudo diff <(sudo awg showconf awg0) /etc/amnezia/amneziawg/awg0.conf
```

```bash
# 3. Can the hops still reach each other at IP level, with real packet sizes?
ping -c 5 <peer-node-ip>                  # small packets
ping -M do -s 1400 -c 5 <peer-node-ip>    # near-full MTU, no fragmentation
```

```bash
# 4. Is NAT/forwarding actually in place, and is it counting?
sudo iptables -t nat -L POSTROUTING -nv
sudo iptables -L FORWARD -nv
```

```bash
# 5. Is policy routing intact? (entry node, split tunneling)
ip rule
ip route show table 200
sudo ipset list -t ru_nets
```

```bash
# 6. If everything above is clean, capture. Both ends, simultaneously.
sudo tcpdump -ni <iface> host <other-end-ip>
```

### 1a. Duplicate `AllowedIPs` — return route stolen

**Seen:** 2026-07-20. Mobile clients handshook normally, `sent` climbed,
`received` advanced only at the `PersistentKeepalive` interval. Independent of
carrier and of location, which ruled out DPI and mobile shaping.

**Cause:** a throwaway test peer had been assigned a live client's
`AllowedIPs` (`10.88.88.44`) two days earlier, before the provisioning wrapper
validated duplicates. Deleting the test peer did not restore the route — the
server simply had nowhere to send that client's return traffic.

**Fix:**

```bash
sudo awg set awg0 peer <client-pubkey> allowed-ips 10.88.88.44/32
# then write it into the config immediately — see principle 2
```

**Prevention (in place):** `pwa-add-peer` now rejects a duplicate IP as well as
a duplicate key, so the same collision cannot be provisioned again.

### 1b. MTU mismatch and encapsulation overhead

**Seen:** 2026-05-27. Clients lost the internet progressively — Telegram first,
then YouTube, then Google. TCP sites worked; UDP-heavy services did not.

**Cause chain:** entry `awg0` MTU was 1220 and fragmenting; clients were at the
1420 default; and the exit path at the time ran IPIP+FOU on top of two AWG
hops, so cumulative header overhead pushed large UDP packets (QUIC on
UDP/443) past the path MTU. They were dropped silently, which is why only
UDP-heavy services broke.

**Fix:**

```bash
sudo ip link set dev awg0 mtu 1300
sudo iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
```

Client configs carry `MTU = 1300`.

**Prevention:** the IPIP+FOU layer was retired entirely in favour of a second
AWG hop — obfuscated by design, and one less set of headers. Encapsulation
depth is now a design constraint, not something discovered under load.

> **Note:** MSS clamping fixes TCP only. It does not help UDP, and it does not
> help SSH key exchange, which bypasses it. If large packets are dropping and
> clamping changes nothing, the problem is below TCP — go to section 3.

### 1c. IP connectivity between hops disappeared

**Seen:** 2026-07-04. Both ends showed live handshakes and no traffic moved.
Port changes, key regeneration and `udp2raw` all failed to help — because the
packets were not crossing between the two providers' networks at all. Both
servers remained reachable from a third location, which is what localized it.

**Check:** if the two nodes cannot ping each other but both answer from
elsewhere, the fault is between the providers, not in the tunnel. Nothing on
either server will fix it.

**Emergency response used:** a three-hop relay through a workstation that had
connectivity to both ends, restoring service in hours. This is a valid
stop-the-bleeding move and an unacceptable steady state — it puts a laptop in
the production path and exposes a residential IP as transit. It was replaced
with a relay VPS as soon as service was stable.

**Prevention:** a provider that causes repeated incidents gets dropped. This
one had caused three (disk exhaustion, kernel/DKMS, connectivity) before the
decision was made — which was two too many.

---

## 2. Tunnel down after reboot or kernel upgrade

**Seen:** 2026-06-30, and three times before that in other forms.

### Triage

```bash
systemctl status awg-quick@awg0
journalctl -u awg-quick@awg0 -b --no-pager
dkms status
lsmod | grep amneziawg
```

### Root causes seen

**Kernel module not registered with DKMS.** Installed once with `make install`,
which binds it to the kernel it was built against. Every kernel upgrade breaks
the tunnel again. The log line is `Unknown device type` or
`Protocol not supported` from `ip link add`.

```bash
# Sources must live somewhere permanent — /tmp is wiped on reboot,
# which is why recovery once required re-cloning the module at 3am.
sudo mv amneziawg-linux-kernel-module /usr/src/amneziawg-1.0.0
sudo dkms add    -m amneziawg -v 1.0.0
sudo dkms build  -m amneziawg -v 1.0.0
sudo dkms install -m amneziawg -v 1.0.0
dkms status   # expect: built for the running kernel AND any installed kernel
```

**`iptables` not found under systemd.** `awg-quick` failed with
`line 295: iptables: command not found` — systemd's `PATH` does not include
`/usr/sbin`. Use absolute paths in `PostUp`/`PostDown`, or verify:

```bash
sudo systemctl show-environment | grep PATH
```

**Interface up but unit `failed`.** The most dangerous variant, because nothing
appears broken. The tunnel was brought up by hand after a failed boot and has
been running unmanaged ever since — in one case for 59 days. It will not come
back on the next reboot.

```bash
systemctl is-active awg-quick@awg0   # may say "failed" while awg0 carries traffic
```

### Before restarting a unit that is `failed` while the interface is live

The running config and the file on disk may have diverged, because the
interface was configured by hand. Diff them first.

```bash
sudo awg showconf awg0 > /root/awg0-runtime-$(date +%F).conf   # rollback copy
sudo diff /root/awg0-runtime-$(date +%F).conf /etc/amnezia/amneziawg/awg0.conf
```

Resolve every difference deliberately. Prefer the version that is reproducible
from the config file, even where the runtime value looks "better" — a setting
that only exists because someone typed it once will not survive the next
restart either, and asymmetric settings between the two ends of a backbone are
a latent failure.

Then restart during low traffic, with the console (VNC) already open.

### Reboot-readiness checklist

Nothing counts as fixed until all seven are green:

1. DKMS rebuilds the module for new kernels
2. Module autoloads (`/etc/modules-load.d/`)
3. `awg-quick@awgN` enabled **and proven to start from config**
4. `net.ipv4.ip_forward` persistent
5. All `iptables` rules live in `PostUp`/`PostDown`, none added by hand
6. Config parses clean
7. Handshake alive after the restart, with traffic

**Prevention in place:** `unattended-upgrades` installs security patches
automatically, but automatic reboot is explicitly disabled. Kernel transitions
happen manually, under supervision, with DKMS verified first.

---

## 3. Node healthy inside, unreachable from outside

The hardest class to diagnose, because every check run on the machine passes.

**Seen twice:** 2026-07-07 (Vienna node) and 2026-09-05 (app server, three-day
outage). Both presented as `Connection timed out during banner exchange`.

### What the machine will tell you — and why it is useless

Interface UP, `ping 8.8.8.8` at 0% loss, `sshd` and `nginx` listening,
containers running, `nc` to port 22 reporting `succeeded`. All true, all
irrelevant. TCP completes; everything after it does not.

### Triage, from outside in

```bash
# 1. Split the external check: TCP connect vs full HTTP.
#    A TCP connect that succeeds everywhere while HTTP times out from half the
#    probe nodes — inconsistently within the same city — is the signature.
#    (check-host.net or any multi-vantage prober.)

# 2. Capture on the server while connecting from outside.
sudo tcpdump -ni <iface> host <your-source-ip>
```

### Read the packet sizes

This is the whole diagnosis:

```
SYN → SYN-ACK → ACK                       handshake completes, ~11 ms
<node>.22 > <client>: length 42
  SSH-2.0-OpenSSH_10.2p1                  the banner
... six more retransmits, exponential backoff, never ACKed
```

**Forty-two bytes.** A packet that small kills MTU, fragmentation and
size-based filtering simultaneously — there is nothing to fragment. The
connection establishes and the return path is gone for everything after it.

In the Vienna case the number was different and the conclusion was the
opposite: small packets passed and were ACKed, key-exchange packets at
**1082 bytes** were retransmitted and never ACKed. That is a PMTU black hole —
large packets dropped, with the ICMP `fragmentation needed` not getting back,
so PMTU discovery cannot self-correct.

**One capture distinguishes the two.** Look at the size of the packet that
stops being acknowledged.

### What each finding means

| Evidence | Diagnosis | Action |
|---|---|---|
| Small packets ACKed, large ones retransmitted | PMTU black hole on the path | Do not paper over it with MSS — it bypasses key exchange and will resurface inside the tunnel. Move the server. |
| Even a 42-byte packet never ACKed | Return path gone entirely | Not fixable from the server. Provider or transit. |
| `ping -M do` fails at *every* size, 1400 down to 900 | ICMP is not passing at all | The MTU test is inconclusive, not positive. It rules nothing out. |

### Tests that produced nothing

Recorded because they cost days:

- **`traceroute` dying at a fixed hop with `!X`.** The same hop refused probes
  on the route to a *working* server. It proves only that the hop drops
  traceroute.
- **MSS clamping.** `tcpdump` confirmed the reduced MSS in the SYN-ACK; the SSH
  key-exchange packets still went out oversized and still black-holed.
- **Changing the IP.** Four addresses on the same provider, same behaviour on
  three of them. A replacement address is not a diagnosis.

### Decision rule

Do not build a tunnel on a link with a PMTU black hole. Encapsulation adds
headers to a path that already cannot carry full-size packets, and the problem
resurfaces inside the tunnel, under client traffic, at a worse time. Fix the
foundation or move the server.

**Verify the path before building anything on a new node:**

```bash
ping -M do -s 1400 -c 10 <new-node>   # from every source that matters
ssh <new-node>                        # a real session — not nc, not ping
```

`nc` succeeding is not connectivity. Both incidents had `nc` succeeding.

---

## 4. Locked out of SSH

Recovery is always via the provider's VNC console. Keep it open in a tab before
doing anything on this list.

### Causes seen

**The tunnel hijacked the routing table.** After a reboot, `awg1` captured
inbound SSH along with everything else.

```ini
# /etc/amnezia/amneziawg/awg1.conf
Table = off      # then route client traffic explicitly via policy routing
```

**`ssh.socket` holding the port.** Socket activation ignores the `Port`
directive in `sshd_config`, so `nc` reports the port open while no real session
can start.

```bash
sudo systemctl disable --now ssh.socket
sudo systemctl enable  --now ssh
```

**UFW enabled without staging the rules.** Enable only after every rule is in
place, and set the forward policy first or all client traffic stops:

```bash
# /etc/default/ufw
DEFAULT_FORWARD_POLICY="ACCEPT"
```

**`ansible` playbook locked the node out.** Run access-affecting changes with a
second SSH session held open, and verify before closing it.

### The cloud-init trap

**Seen:** 2026-07-01, on a production node that had been exposed since
provisioning.

`sshd_config` said `PasswordAuthentication no`. Password authentication was on.
Cloud-init's `/etc/ssh/sshd_config.d/50-cloud-init.conf` set it to `yes`, and
because the `Include` directive sits at line 12 and **sshd honors the first
value it sees**, a higher-numbered drop-in could not override it.

Never trust the main config file. Check what sshd actually resolved:

```bash
sudo sshd -T | grep -iE 'passwordauth|permitrootlogin|pubkeyauth'
```

Fix at the source — edit the cloud-init drop-in itself — and re-check with
`sshd -T` before restarting. Validate syntax with `sshd -t` first, always, with
the VNC console open.

---

## 5. Peers vanished after reboot

**Seen:** 2026-06-24. Five clients lost access after an unplanned reboot. Their
configs were still valid; the server no longer had their peers.

**Cause:** the peers had been added with `awg set` at runtime and never written
into `awg0.conf`. They worked for weeks, then the boot wiped them.

### Recovery

The client's private key is enough to reconstruct the peer:

```bash
echo "<client-private-key>" | wg pubkey     # derive the public key
sudo awg set awg0 peer <pubkey> allowed-ips 10.88.88.X/32
```

Then **write it into the config in the same minute**, and verify both:

```bash
sudo awg show awg0 peers | wc -l
grep -c '^\[Peer\]' /etc/amnezia/amneziawg/awg0.conf
# the two numbers must match
```

**Prevention in place:** peers are provisioned through `pwa-add-peer`, which
writes to the config file rather than to runtime only, and client names come
from the database instead of being read back off the server.

This failure mode appeared four times in different disguises — missing PSKs,
lost peers, a hand-added `MASQUERADE` rule, a non-DKMS kernel module. They are
one bug: **runtime-only state.** The rule that closed the class:

> Modules go to DKMS. Firewall rules go to `PostUp`/`PostDown`. Peers go to
> the config file immediately. Sources never live in `/tmp`.

---

## 6. Monitoring reports success, shows nothing

### Grafana: dashboard provisioned cleanly, every panel says "No data"

**Seen:** 2026-07-23. File provisioning logged
`finished to provision dashboards` with no errors. Nothing rendered.

**Cause:** file provisioning does not resolve the `${ds_prometheus}` datasource
variable — only a manual UI import does. The community dashboard (id 1860)
referenced it in **127 separate places**.

**Fix:** replace every reference with the literal datasource UID before
provisioning.

```bash
sed -i 's/${ds_prometheus}/<datasource-uid>/g' dashboard.json
grep -c 'ds_prometheus' dashboard.json   # expect 0
```

### Alertmanager: config valid, service will not start

**Seen:** 2026-07-24. `amtool check-config` passed. The unit still failed.

**Cause:** `alertmanager.yml` was `600 root:root`; the service runs as
`prometheus`. Config syntax being valid says nothing about whether the process
can read the file.

Two fix attempts failed first, both by copying the permissions of a
*similar* working file instead of checking who actually reads this one:

```bash
id prometheus                       # check the real uid/gid — do not assume
sudo chown root:prometheus /etc/alertmanager/alertmanager.yml
sudo chmod 640 /etc/alertmanager/alertmanager.yml
```

### Firewall persistence: "enabled" with an empty ruleset

**Seen:** 2026-07-23. `netfilter-persistent` was enabled and
`/etc/iptables/rules.v4` was **0 bytes** — the same class of bug as a `failed`
unit with a live interface.

```bash
sudo systemctl is-enabled netfilter-persistent
sudo wc -c /etc/iptables/rules.v4          # zero means nothing is persisted
sudo iptables-save | head                  # what is actually loaded right now
```

Check the artifact, not the service state. After every firewall change:

```bash
sudo netfilter-persistent save
sudo wc -c /etc/iptables/rules.v4
```

### Verifying an exporter is actually restricted

Each node's `node_exporter` accepts scrapes only from the monitoring host.
Test both directions — a positive test alone proves nothing about exposure:

```bash
curl -s -m 5 http://<node>:9100/metrics | head -1   # from the scraper: succeeds
curl -s -m 5 http://<node>:9100/metrics | head -1   # from anywhere else: times out
```

---

## 7. Deploy succeeded, service wrong or 502

### Static files did not change

**Cause:** the Dockerfile does `COPY . .` at build time. `docker compose
restart` restarts the old image, so edits to `static/` never reach the
container. `.env` changes *do* take effect on restart, because those are read
at process start — which is what masks the problem.

```bash
docker compose build && docker compose up -d --force-recreate
```

### 502 immediately after deploy

**Cause:** `deploy.sh` returns as soon as the container reports `Started`, and
the verification `curl` fires before uvicorn is listening. Not a failure — a
race. Check the container log before diagnosing anything:

```bash
docker compose logs --tail=50 pwa    # migrations applied? "startup complete"?
```

Add a readiness wait to the end of the deploy script rather than diagnosing
this twice.

### The server and the repository have diverged

**Seen:** 2026-09-02. Edits had been made directly on the server over SSH for
several weeks. `deploy.sh` rsyncs *from* the workstation, so running it would
have overwritten every one of those fixes with a stale copy.

Before any deploy that has not run in a while:

```bash
rsync -avn --delete <server>:/opt/pwa/<app>/ ./   # dry run — read every line
```

Reconcile into git first. Then deploy.

### Deployed to the wrong host

With more than one server holding the same application directory, verify where
the code landed before concluding the change did not work:

```bash
hostname; curl -s localhost:8000/health
```

---

## Provisioning access model

Referenced above; documented in full in
[`architecture.md`](architecture.md).

The portal never holds a personal SSH key. It authenticates as a dedicated
`pwa-provisioner` user whose `sudoers` entry permits three wrapper scripts and
nothing else:

| Wrapper | Purpose | Validation |
|---|---|---|
| `pwa-add-peer` | add a client peer | key format, `/32` inside the client subnet, duplicate key, duplicate IP |
| `pwa-awg-show` | read tunnel state | read-only |
| `pwa-logs` | read service logs | read-only |

No direct `awg`, `cat` or `journalctl`. The wrappers exist because a newer
`sudo` rejected wildcards in command arguments — which closed a wildcard hole
that had gone unnoticed under an older `sudo` on another node.

---

## When an incident is closed

An incident is not closed when service is restored. It is closed when:

1. The root cause is identified — not the trigger, the cause.
2. The fix is structural and lives in code or config, not in a shell session.
3. It survives a reboot, verified rather than assumed.
4. The journal entry is written, including the hypotheses that were wrong.
5. Where a check would have caught it in seconds instead of days, the check
   exists.

Point 4 is not ceremony. Four of the incidents in this document were diagnosed
quickly the second time because the first time had been written down — and the
September outage was recognized by a single error string that matched an entry
from July.
