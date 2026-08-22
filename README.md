# Sovereign — Multi-Hop Obfuscated VPN Infrastructure

[![GitHub last commit](https://img.shields.io/github/last-commit/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)](https://github.com/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)
![Ansible](https://img.shields.io/badge/Ansible-EE0000.svg?logo=ansible&logoColor=white)
[![AmneziaWG](https://img.shields.io/badge/AmneziaWG-88171A?logo=wireguard)](https://github.com/amnezia-vpn/amneziawg)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)

**A production VPN service designed, built, and operated solo**: multi-hop AmneziaWG routing resilient to DPI interference, policy-based split tunneling, and a self-hosted client portal with automated crypto billing and peer provisioning.

Every incident described below happened on a live system with real users. Each was diagnosed from its symptoms, fixed, and closed with a structural change that prevents the same class of mistake from recurring. Where a diagnosis was wrong, that is stated too.

---

## What This Project Demonstrates

- **Linux administration** — systemd services and oneshot units, DKMS kernel-module management, cloud-init pitfalls, SSH hardening verified with `sshd -T`, fail2ban, unattended-upgrades
- **Networking** — WireGuard/AmneziaWG internals, multi-hop routing, policy routing (`ip rule` / multiple tables), ipset-based split tunneling, NAT, PMTU and MSS behavior, iptables/UFW default-deny firewalling, packet-level diagnosis with `tcpdump`, DPI behavior analysis on mobile carriers
- **Infrastructure as code** — Ansible roles for node provisioning; Terraform modules and a GitHub Actions validation pipeline in an earlier phase (see [Project Phases](#project-phases)); documented lessons on idempotency, secret handling, and what happens when live state isn't in code
- **Monitoring & alerting** — Prometheus, node_exporter, Grafana, Alertmanager → Telegram, Loki/Promtail log aggregation, source-IP-restricted scrape paths, email alerting from health checks
- **Backend engineering** — async FastAPI, PostgreSQL (asyncpg/SQLAlchemy), Alembic migrations, JWT auth, Docker Compose
- **Security engineering** — privilege separation for automated SSH access, secrets-at-rest encryption, HMAC webhook verification, incident response with public post-mortems
- **Operations discipline** — staged rollouts with prepared rollbacks, reboot-readiness audits, a dated research log, and an honest archive of superseded approaches

---

## Architecture

```
Client device → Entry node (obfuscated AmneziaWG) → Backbone tunnel → Exit node (NAT) → Internet
                      │
                      └─→ RU-destined traffic → local exit (split tunnel, ipset + policy routing)
```

| Node role | Function |
|---|---|
| **Entry** | Public-facing AmneziaWG endpoint clients connect to; holds client peers and split-tunnel policy |
| **Exit** | Backbone endpoint; NATs client traffic out to the internet |
| **App server** | Client portal (FastAPI + PostgreSQL, Dockerized) — deliberately separate from the VPN data plane |

The service targets hostile network environments: DPI-based protocol fingerprinting, throttling, and strict IP/domain allowlist filtering. All AmneziaWG interfaces run unique per-node obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4). Plain WireGuard clients can't connect by design — the standard WireGuard handshake is fingerprinted and throttled by DPI on some mobile networks (see [Research Log](#research-log)), while AmneziaWG's obfuscated stream passes as generic UDP.

Two placement rules came out of real failures rather than design preference:

**The app server is never co-located with a VPN node.** Docker's own iptables/NAT chains conflicted with WireGuard forwarding when they shared a host. The split resolved it cleanly and is now a standing constraint — which in turn means "spare VPN node" and "app host" are mutually exclusive roles when allocating servers.

**Monitoring runs as native systemd services, not in Docker,** for the same reason on VPN-adjacent hosts.

---

## Security Model

Principles that emerged from real incidents, not from a checklist:

- **Nothing critical exists only at runtime.** Kernel modules go through DKMS, firewall rules through PostUp/PostDown and persisted rule files, peers into config files and the Ansible inventory immediately. This rule exists because each of those bit me: a module lost on kernel upgrade, an "enabled" persistence service with an empty rules file, peers that vanished on reboot, and 35 peers wiped by a playbook run because they lived in the live file instead of in code.
- **The web app never holds admin credentials.** The portal reaches VPN nodes through a dedicated low-privilege unix user and keypair, restricted by sudoers to a small set of validating wrapper scripts — no raw `awg`, `cat`, or `journalctl`. The write wrapper independently re-validates every argument server-side (key format, subnet membership, duplicate key, duplicate IP) before touching live WireGuard state.
- **Default-deny everywhere.** iptables/ip6tables default-deny on every node, verified before switching policy: a held-open SSH session survives, a fresh SSH connection succeeds, monitoring scrapes still pass. Exporters accept scrapes from exactly one source IP — confirmed with both a positive test (monitoring node succeeds) and a negative test (everything else times out).
- **Secrets encrypted at rest.** Client private keys are Fernet-encrypted in the database and decrypted only on demand for config delivery — never stored or logged in plaintext. Payment amounts come from a server-side price table; client-supplied values are never trusted.
- **A shared resource is never changed blind.** Anything touching all users is tested on a single `/32` first, with the rollback command written out before the change is made.
- **Verification over assumption.** SSH hardening is confirmed with `sshd -T` (after discovering cloud-init silently overriding sshd_config), fixes are confirmed by reproducing the failure live, firewall changes are tested from both sides, and persistence is confirmed by simulating a reboot rather than trusting an exit code.

---

## Engineering Highlights

### Infrastructure & networking

**A three-day connectivity failure traced to a PMTU black hole, proven at packet level.** Symptom: SSH to a newly rented node failed with "timeout during banner exchange," while ping, `nc` to port 22, and the TCP handshake itself all succeeded. Suspects were DPI, IP blocking, and cross-border transit. The decisive move was buying a second node from the *same provider* inside RU to remove the inter-provider and cross-border variables — the failure reproduced, ruling all three out. A paired `tcpdump` on both ends then showed it exactly: TCP established, the 42-byte SSH banner passed and was ACKed, then the server's 1082-byte key-exchange packets were retransmitted forever and never acknowledged. Packets above roughly 1000 bytes were being dropped silently with no ICMP fragmentation-needed getting back, so PMTU discovery could not self-correct. **MSS clamping did not fix it** — `tcpdump` confirmed the reduced MSS in the SYN-ACK, but the key-exchange packets bypassed the clamp and still black-holed, which located the fault at the link/route layer rather than in TCP configuration. Rather than force a low interface MTU (which would have to be re-solved for the tunnel's own encapsulation overhead and stay fragile), the diagnosis was written up as a provider support ticket with reproducible evidence. The provider refunded the node and supplied one in a different city. The replacement was tested with the same large-packet suite *before* anything was built on it.

**Cutover of 18 live users with a one-client canary and a rollback in hand.** Users were online but egressing domestically — no foreign exit. Reading both ends of the backbone rather than guessing found it: the exit node's peer showed `0 B received, 271 MiB sent` — a one-way tunnel — and the entry node's backbone interface had the correct key and address but an `Endpoint` still pointing at a decommissioned relay, with drifted preshared keys on top. Bring-up then failed with `RTNETLINK answers: File exists`, caused by a stale default route left in the policy-routing table by an earlier emergency workaround. With the path repaired, the cutover was staged rather than flipped: a narrow `ip rule from <test-client>/32 lookup 201 priority 40` moved **one** client to the foreign exit while the other 17 stayed untouched; only after verifying the exit IP from that client was the whole subnet switched, with the rollback command prepared beforehand. All 18 users back on the foreign exit, zero dropped during the operation.

**Split tunneling by real IP, with an atomic weekly refresh.** Goal: domestic banking and government services reachable without users turning the VPN off, with no change to client configs. Implementation is entirely server-side — an ipset (`hash:net`) of ~11.4k country prefixes from RIPE, a mangle rule marking client traffic destined to those networks, and an `ip rule` at priority 99 (ahead of the rule that sends everything to the foreign exit) routing marked traffic out locally. The weekly refresh is built to fail safe: it assembles a temporary set, refuses to proceed if the fetched list contains fewer than 8000 prefixes (guarding against a registry outage returning garbage), then uses an atomic `ipset swap` so the tunnel is never without a list mid-update. **A reboot simulation caught a silent bug the exit code hid:** the first restore script did a manual `ipset create` + `flush` before `ipset restore`, which aborted on the pre-existing set — the systemd unit reported `SUCCESS` and restored nothing. Only exercising the real boot path exposed it.

**35 production peers wiped by my own playbook run.** After a port change, `deploy-awg.yml` rebuilt the server config from its template and 35 client peers vanished — they had been added earlier by a script writing directly into the live file, never into the Ansible inventory. Only the five inventory-defined peers survived. Nothing was lost (client configs were archived), and all 40 peers were rebuilt into the inventory, each peer's public key **derived from the private key in its own client config** via `awg pubkey` so that server-side peer and client config cannot drift — the exact mismatch that had caused an earlier outage, now prevented by construction. The server keypair was also pinned in inventory so the role's key-generation task can never fire on a redeploy and silently invalidate every client.

### Backend & delivery

**Privilege separation for automated SSH access.** The portal originally reached the entry node with the same personal key and passwordless sudo used for manual administration — a public web app with root-equivalent access to a production node. Rebuilt around a dedicated provisioning user and the validating-wrapper scheme described in the security model. A newer sudo version on one node rejected a wildcard pattern an older sudo had silently accepted; instead of working around the stricter version, the looser node was brought up to its standard — the rejection was correctly closing a real hole.

**Secrets exposure in this public repo — contained, rotated, documented.** A malformed `.gitignore` (a path glued onto a divider comment) caused real Ansible group_vars to be tracked and pushed, including two backbone tunnel private keys. Response: impact analysis first (only one key was still live; preshared keys and the live-user node were unaffected), then immediate rotation of everything exposed. Deliberate decision: rotate rather than rewrite git history — a secret that has been public must be treated as permanently compromised, so history-rewriting adds no security and only hides the lesson.

**An asyncio/asyncpg bug confirmed live, not assumed from a code read.** The provisioning path ran a blocking SSH call inside a fresh event loop (`asyncio.run()` in a thread executor), which bound database connections to a different loop than the one that created them — a hard runtime error in asyncpg. Before fixing, the failure was reproduced deliberately: a correctly signed synthetic webhook against a real pending invoice, watching the exact `RuntimeError` appear in production logs. Fix: only the blocking SSH call goes to the executor; database work stays in the request's own loop. Verified with a second live run showing successful provisioning end to end.

**Byte-level webhook signature compatibility, verified before the first real transaction.** The payment gateway signs webhooks over PHP's `json_encode` output, so signature verification required replicating its serialization quirks byte for byte — escaped forward slashes, exact numeric formatting. A mismatch would make every real webhook fail silently. The full path — signature check, provisioning, database state — was proven with a signed synthetic webhook against a real unpaid invoice before production credentials were wired in.

**One-way traffic on mobile clients, traced through a WireGuard internal.** Symptom: handshake succeeds, "sent" climbs, "received" frozen except keepalive-sized bumps every 25s. Root cause: days earlier, a test peer had been assigned a live client's `AllowedIPs` — WireGuard permits one IP per peer and reassigns silently — and deleting the test peer never restored the original route. Diagnosed by diffing the server's live `AllowedIPs` table against the on-disk config. Closed structurally: the write wrapper now rejects duplicate IPs, so this class of mistake can't recur silently.

### Recurring lessons

Several incidents were the same mistake wearing different clothes. They are listed together because the pattern is the point:

| Symptom | What was actually true |
|---|---|
| `netfilter-persistent` enabled and reporting fine | `rules.v4` was empty — nothing would have restored on boot |
| systemd unit exits `SUCCESS` after restoring the ipset | It restored nothing; the restore aborted on a pre-existing set |
| Grafana dashboard provisioned with no errors in the log | Every panel showed *No data* — 127 unresolved datasource references |
| Alert sender tested directly and "worked" | It read the recipient from a variable only its caller sets; a real run sent nothing |
| Code edits deployed with `docker compose restart` | The image bakes code at build time; only `build` + `--force-recreate` picks it up |
| `awg-quick@awg0` unit `failed` while the interface was up | Brought up by hand after a boot-time module miss; systemd holds `failed` until something tries to start it again |

The common thread: **a green exit code is not evidence.** Each of these was found by exercising the real path — simulating the reboot, calling the integrated chain, rebuilding the container — rather than by testing the component in isolation and trusting the result.

---

## Project Phases

The stack changed substantially as the architecture found its shape. This table is here so that tooling visible in the repository's history isn't mistaken for what runs today.

| Phase | Focus | Notable tooling | Status |
|---|---|---|---|
| **1 — Single node** | First obfuscated endpoint, first clients, initial DPI observations | AmneziaWG, Xray/VLESS-Reality (evaluated), Uptime Kuma | Superseded |
| **2 — Infrastructure as code** | Reproducible provisioning, validation in CI | Ansible roles, Terraform modules (Yandex Cloud + VPS provider), GitHub Actions pipeline validating Terraform/Ansible/shell/Python | Ansible retained; Terraform archived when Yandex Cloud was dropped for direct VPS providers |
| **3 — Multi-hop & observability** | Entry→exit chain, log aggregation, alerting | IPIP and AmneziaWG backbone, Prometheus + Grafana + Alertmanager + Loki/Promtail | Backbone retained; the monitoring host was decommissioned and the stack is being rebuilt |
| **4 — Product** | Client portal, billing, provisioning, split tunneling | FastAPI + PostgreSQL, crypto gateway, ipset split tunnel, transactional email over HTTPS API | Current |

The [`archive/`](archive/README.md) directory preserves superseded approaches with notes on why each was replaced.

---

## Monitoring

**Status: being rebuilt.** The host that ran the observability stack was decommissioned in August 2026; a replacement is being provisioned and the stack redeployed. What is described here is the configuration that ran, and what is being restored.

Prometheus + node_exporter on every node, Grafana dashboards, Alertmanager routing to Telegram, plus an independent email alert path driven by a five-minute health cron (rate-limited to one notice per problem per six hours, with a RECOVERED notice when the condition clears). Every exporter is firewalled to a single scrape source; every alert path was verified end to end with a manual test alert before being trusted.

Monitoring runs as native systemd services rather than in Docker — a deliberate choice, since Docker's iptables manipulation conflicts with WireGuard forwarding on VPN-adjacent hosts.

<!-- SCREENSHOT: Grafana Node Exporter Full dashboard, multiple nodes -->
<!-- SCREENSHOT: Alertmanager → Telegram alert delivery -->

---

## Client Portal & Billing

A PWA (vanilla JS, RU/EN i18n, installable) backed by async FastAPI: registration, JWT auth, personal config delivery, subscription and payment history, support form with a client-facing FAQ. After a confirmed payment, provisioning runs unattended:

1. Generate a fresh keypair + preshared key
2. Allocate a free IP from the client pool, retrying against the entry node's live state if the local pool is stale
3. Add the peer through the validating wrapper — never a raw SSH command
4. Encrypt and store the config, activate the subscription

Billing is handled by a crypto payment gateway over an HTTPS API with HMAC-signed webhooks. Transactional email also runs over an HTTPS API — chosen after diagnosing, via direct TCP tests against multiple providers, that all outbound SMTP ports were blocked at the hosting-network level.

---

## Research Log

[`docs/troubleshooting.md`](docs/troubleshooting.md) is a dated research log from earlier stages — real investigations into mobile-network DPI behavior, not a generic FAQ. Highlights:

- **Dynamic DPI blacklisting**: one mobile operator's DPI temporarily blacklisted the server IP/port for 10–30 seconds after detecting a VPN handshake attempt, then cleared automatically — established through a structured hypothesis → test matrix → conclusion process.
- **Strict allowlist filtering defeats protocol-level obfuscation**: even traffic shaped to mimic permitted domains fails under strict allowlist enforcement, because DNS/SNI reveal the true destination before obfuscation matters. This finding ruled out several alternative protocols and shaped the current architecture.
- **Carrier-level asymmetric blocking, distinguished from an MTU problem**: on one mobile carrier the handshake completed but real traffic died. `tcpdump` showed every packet flowing server → client and none returning — and `ping -M do` failed at *every* size including small ones, which ruled out MTU. The server was encrypting and sending correctly; the carrier was cutting the client's return path. Narrowed to the obfuscation parameter set and the IP range's reputation, and explicitly classified as carrier behavior rather than an infrastructure bug.
- **Tethering detection via TTL**: mobile operators can detect tethered devices from the TTL decrement added by the extra router hop — confirmed by direct TTL comparison, not assumption.

[`archive/`](archive/README.md) preserves superseded approaches with honest notes on why each was replaced — including a Docker-based monitoring bot prototype and several alternative-protocol deployments dropped after real-world DPI testing.

---

## Tech Stack

| Layer | Choices |
|---|---|
| VPN | AmneziaWG (obfuscated WireGuard fork), unique parameters per node, multi-hop backbone |
| Routing | Policy routing (`ip rule` + multiple tables), ipset-based split tunneling, NAT, MSS/MTU tuning |
| OS / hardening | Ubuntu, iptables/UFW default-deny, SSH key-only, fail2ban, unattended-upgrades, DKMS |
| IaC | Ansible (roles: `common`, `amneziawg`, `amneziawg-backbone`, `amneziawg-bridge`) |
| Monitoring | Prometheus, node_exporter, Grafana, Alertmanager, email alerting (native systemd, not Docker) — currently being rebuilt |
| Backend | FastAPI (Python 3.12, fully async), SQLAlchemy async + asyncpg, PostgreSQL, Alembic, JWT, Fernet encryption at rest |
| Frontend | Vanilla JS PWA, RU/EN i18n, dark theme |
| Billing & email | Crypto payment gateway (HMAC webhooks, server-side pricing), transactional email via HTTPS API |
| Web entry | nginx + Let's Encrypt (certbot), Docker Compose on the app server only |
| Earlier phases | Terraform (Yandex Cloud + VPS modules), GitHub Actions validation pipeline, Loki/Promtail, Xray/VLESS-Reality — see [Project Phases](#project-phases) |

---

## Current Status

| Component | Status |
|---|---|
| VPN infrastructure (obfuscated multi-hop) | ✅ Operational |
| Split tunneling (domestic services exit locally) | ✅ Operational, weekly automatic prefix refresh |
| Client portal (PWA) | ✅ Live, HTTPS, RU/EN |
| Auto-provisioning (payment → peer → config) | ✅ Verified end to end with a live test transaction |
| Crypto billing | ✅ Live, passed gateway moderation |
| Transactional email | ✅ Live (HTTPS API) |
| Monitoring (Prometheus/Grafana/Alertmanager) | 🔧 Rebuilding — host decommissioned, replacement being provisioned |
| Admin panel | 🔧 Functional, UX polish in progress |

---

## Repository Layout

```
pwa/                      FastAPI client portal + billing + provisioning
infrastructure/ansible/   Server configuration as code (roles, inventories, playbooks)
monitoring/               Prometheus / Grafana / Alertmanager configuration
docs/                     Architecture and dated research log
archive/                  Superseded approaches, kept with honest post-mortems
```

---

## Roadmap

- Rebuild the observability stack on a new host
- Automated PostgreSQL backups
- Per-client network isolation (clients unable to reach each other's subnets)
- SSH access layer 3: forced-command dispatcher for the provisioning path
- CI secret scanning (gitleaks) and pre-push checks — turning the `.gitignore` incident into pipeline policy
- Default-deny FORWARD policy on the production nodes
- Exploring: AI-assisted incident diagnosis on top of Alertmanager events (read-only, wrapper-constrained)

---

## About

Solo project by Alexander — self-taught, currently looking for **Linux SysAdmin / IT Support (L2–L3) / Junior DevOps** roles.

- https://www.linkedin.com/in/alexander-kozariychuk/
- alexanderkozariychuk@gmail.com

## License

MIT — see [LICENSE](LICENSE).
