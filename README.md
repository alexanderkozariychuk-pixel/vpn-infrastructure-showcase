# Sovereign — Multi-Hop Obfuscated VPN Infrastructure

[![GitHub last commit](https://img.shields.io/github/last-commit/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)](https://github.com/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)
![Ansible](https://img.shields.io/badge/Ansible-EE0000.svg?logo=ansible&logoColor=white)
[![AmneziaWG](https://img.shields.io/badge/AmneziaWG-88171A?logo=wireguard)](https://github.com/amnezia-vpn/amneziawg)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)

**A production VPN service designed, built, and operated solo**: multi-hop AmneziaWG routing resilient to DPI interference, a self-hosted client portal with automated crypto billing and peer provisioning, and a full Prometheus/Grafana/Alertmanager observability stack across four servers.

Every incident described below happened on a live system with real users. Each was diagnosed from its symptoms, fixed, and closed with a structural change that prevents the same class of mistake from recurring.

---

## What This Project Demonstrates

- **Linux administration** — systemd services, DKMS kernel-module management, cloud-init pitfalls, SSH hardening verified with `sshd -T`, fail2ban, unattended-upgrades
- **Networking** — WireGuard/AmneziaWG internals, multi-hop routing, NAT, iptables/UFW default-deny firewalling, DPI behavior analysis on mobile networks
- **Infrastructure as code** — Ansible roles for node provisioning (AmneziaWG, firewall), with documented lessons on idempotency and secret handling
- **Monitoring & alerting** — Prometheus, node_exporter, Grafana, Alertmanager → Telegram, with source-IP-restricted scrape paths
- **Backend engineering** — async FastAPI, PostgreSQL (asyncpg/SQLAlchemy), Alembic migrations, JWT auth, Docker Compose
- **Security engineering** — privilege separation for automated SSH access, secrets-at-rest encryption, HMAC webhook verification, incident response with public post-mortems
- **Operations discipline** — dated research log, runbook, honest archive of superseded approaches

---

## Architecture

```
Client device → Entry node (obfuscated AmneziaWG) → Backbone tunnel → Exit node (NAT) → Internet
```

| Node role | Function |
|---|---|
| **Entry** | Public-facing AmneziaWG endpoint clients connect to |
| **Exit** | Backbone endpoint; NATs client traffic out to the internet |
| **App server** | Client portal (FastAPI + PostgreSQL, Dockerized) — deliberately separate from the VPN data plane |
| **Monitoring** | Prometheus, Grafana, Alertmanager — scrapes all nodes over a firewalled, single-source-IP path |

The service targets hostile network environments: DPI-based protocol fingerprinting, throttling, and strict IP/domain allowlist filtering. All AmneziaWG interfaces run unique per-node obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4). Plain WireGuard clients can't connect by design — the standard WireGuard handshake is fingerprinted and throttled by DPI on some mobile networks (see [Research Log](#research-log)), while AmneziaWG's obfuscated stream passes as generic UDP.

The app server is intentionally separate from the VPN nodes: Docker's own iptables/NAT chains conflicted with WireGuard forwarding when co-located early on. The split resolved it cleanly and is now a standing rule.

---

## Security Model

Principles that emerged from real incidents, not from a checklist:

- **Nothing critical exists only at runtime.** Kernel modules go through DKMS, firewall rules through PostUp/PostDown and persisted rule files, peers into config files immediately. This rule exists because each of those three bit me once: a module lost on kernel upgrade, an "enabled" persistence service with an empty rules file, peers that vanished on reboot.
- **The web app never holds admin credentials.** The portal reaches VPN nodes through a dedicated low-privilege unix user and keypair, restricted by sudoers to a small set of validating wrapper scripts — no raw `awg`, `cat`, or `journalctl`. The write wrapper independently re-validates every argument server-side (key format, subnet membership, duplicate key, duplicate IP) before touching live WireGuard state.
- **Default-deny everywhere.** iptables/ip6tables default-deny on every node, verified before switching policy: a held-open SSH session survives, a fresh SSH connection succeeds, monitoring scrapes still pass. Exporters accept scrapes from exactly one source IP — confirmed with both a positive test (monitoring node succeeds) and a negative test (everything else times out).
- **Secrets encrypted at rest.** Client private keys are Fernet-encrypted in the database and decrypted only on demand for config delivery — never stored or logged in plaintext. Payment amounts come from a server-side price table; client-supplied values are never trusted.
- **Verification over assumption.** SSH hardening is confirmed with `sshd -T` (after discovering cloud-init silently overriding sshd_config), fixes are confirmed by reproducing the failure live, and firewall changes are tested from both sides.

---

## Engineering Highlights

**Privilege separation for automated SSH access.** The portal originally reached the entry node with the same personal key and passwordless sudo used for manual administration — a public web app with root-equivalent access to a production node. Rebuilt around a dedicated provisioning user and the validating-wrapper scheme described above. A newer sudo version on one node rejected a wildcard pattern an older sudo had silently accepted; instead of working around the stricter version, the looser node was brought up to its standard — the rejection was correctly closing a real hole.

**One-way traffic on mobile clients, traced through a WireGuard internal.** Symptom: handshake succeeds, "sent" climbs, "received" frozen except keepalive-sized bumps every 25s. Root cause: days earlier, a test peer had been assigned a live client's `AllowedIPs` — WireGuard permits one IP per peer and reassigns silently — and deleting the test peer never restored the original route. Diagnosed by diffing the server's live `AllowedIPs` table against the on-disk config. Closed structurally: the write wrapper now rejects duplicate IPs, so this class of mistake can't recur silently.

**Secrets exposure in this public repo — contained, rotated, documented.** A malformed `.gitignore` (a path glued onto a divider comment) caused real Ansible group_vars to be tracked and pushed, including two backbone tunnel private keys. Response: impact analysis first (only one key was still live; preshared keys and the live-user node were unaffected), then immediate rotation of everything exposed. Deliberate decision: rotate rather than rewrite git history — a secret that has been public must be treated as permanently compromised, so history-rewriting adds no security and only hides the lesson.

**An asyncio/asyncpg bug confirmed live, not assumed from a code read.** The provisioning path ran a blocking SSH call inside a fresh event loop (`asyncio.run()` in a thread executor), which bound database connections to a different loop than the one that created them — a hard runtime error in asyncpg. Before fixing, the failure was reproduced deliberately: a correctly signed synthetic webhook against a real pending invoice, watching the exact `RuntimeError` appear in production logs. Fix: only the blocking SSH call goes to the executor; database work stays in the request's own loop. Verified with a second live run showing successful provisioning end to end.

**Byte-level webhook signature compatibility, verified before the first real transaction.** The payment gateway signs webhooks over PHP's `json_encode` output, so signature verification required replicating its serialization quirks byte for byte — escaped forward slashes, exact numeric formatting. A mismatch would make every real webhook fail silently. The full path — signature check, provisioning, database state — was proven with a signed synthetic webhook against a real unpaid invoice before production credentials were wired in.

**"The fix isn't working" turned out to be a Docker deployment fact.** Several rounds of edits appeared to have no effect on the running app. Cause: the Dockerfile bakes code into the image at build time (`COPY . .`), and `docker compose restart` reuses the already-built image — it picks up `.env` changes (read at process start) but never code changes. Only `build` + `up --force-recreate` does. The deploy procedure now rebuilds unconditionally, and the distinction is documented in the runbook.

---

## Monitoring

Prometheus + node_exporter on all four nodes, Grafana dashboards, Alertmanager routing to Telegram. Every exporter is firewalled to a single scrape source; every alert path was verified end to end with a manual test alert before being trusted.

<!-- SCREENSHOT: Grafana Node Exporter Full dashboard, multiple nodes -->
<!-- SCREENSHOT: Alertmanager → Telegram alert delivery -->

Monitoring runs as native systemd services rather than in Docker — a deliberate choice, since Docker's iptables manipulation conflicts with WireGuard forwarding on VPN-adjacent hosts.

---

## Client Portal & Billing

A PWA (vanilla JS, RU/EN i18n, installable) backed by async FastAPI: registration, JWT auth, personal config delivery, subscription and payment history, support form. After a confirmed payment, provisioning runs unattended:

1. Generate a fresh keypair + preshared key
2. Allocate a free IP from the client pool, retrying against the entry node's live state if the local pool is stale
3. Add the peer through the validating wrapper — never a raw SSH command
4. Encrypt and store the config, activate the subscription

Billing is handled by a crypto payment gateway over an HTTPS API with HMAC-signed webhooks. Transactional email runs over an HTTPS API as well — chosen after diagnosing (via direct TCP tests against multiple providers) that all outbound SMTP ports were blocked at the hosting-network level.

---

## Research Log

[`docs/troubleshooting.md`](docs/troubleshooting.md) is a dated research log from earlier stages — real investigations into mobile-network DPI behavior, not a generic FAQ. Highlights:

- **Dynamic DPI blacklisting**: one mobile operator's DPI temporarily blacklisted the server IP/port for 10–30 seconds after detecting a VPN handshake attempt, then cleared automatically — established through a structured hypothesis → test matrix → conclusion process (ping/DNS/handshake retries under controlled conditions).
- **Strict allowlist filtering defeats protocol-level obfuscation**: even traffic shaped to mimic permitted domains fails under strict allowlist enforcement, because DNS/SNI reveal the true destination before obfuscation matters. This finding ruled out several alternative protocols and shaped the current architecture.
- **Tethering detection via TTL**: mobile operators can detect tethered devices from the TTL decrement added by the extra router hop — confirmed by direct TTL comparison, not assumption.

[`docs/runbook.md`](docs/runbook.md) covers day-to-day operations: diagnosing a failed provisioning, recovering a peer manually, safe node restart procedures.

[`archive/`](archive/README.md) preserves five superseded approaches with honest notes on why each was replaced — including a Docker-based monitoring bot prototype and four alternative-protocol deployments dropped after real-world DPI testing.

---

## Tech Stack

| Layer | Choices |
|---|---|
| VPN | AmneziaWG (obfuscated WireGuard fork), unique parameters per node, multi-hop backbone |
| OS / hardening | Ubuntu, iptables/UFW default-deny, SSH key-only, fail2ban, unattended-upgrades, DKMS |
| IaC | Ansible (node roles: AmneziaWG, firewall) |
| Monitoring | Prometheus, node_exporter, Grafana, Alertmanager (native systemd, not Docker) |
| Backend | FastAPI (Python 3.12, fully async), SQLAlchemy async + asyncpg, PostgreSQL, Alembic, JWT, Fernet encryption at rest |
| Frontend | Vanilla JS PWA, RU/EN i18n, dark theme |
| Billing & email | Crypto payment gateway (HMAC webhooks, server-side pricing), transactional email via HTTPS API |
| Web entry | nginx + Let's Encrypt (certbot), Docker Compose on the app server only |

---

## Current Status

| Component | Status |
|---|---|
| VPN infrastructure (obfuscated multi-hop) | ✅ Operational |
| Client portal (PWA) | ✅ Live, HTTPS, RU/EN |
| Auto-provisioning (payment → peer → config) | ✅ Verified end to end with a live test transaction |
| Crypto billing | ✅ Live, passed gateway moderation |
| Transactional email | ✅ Live (HTTPS API) |
| Monitoring (Prometheus/Grafana/Alertmanager) | ✅ Operational, all nodes |
| Admin panel | 🔧 Functional, UX polish in progress |

---

## Repository Layout

```
pwa/                      FastAPI client portal + billing + provisioning
infrastructure/ansible/   Server configuration as code (AmneziaWG roles, firewall)
monitoring/               Prometheus / Grafana / Alertmanager configuration
docs/                     Architecture, runbook, dated research log
archive/                  Superseded approaches, kept with honest post-mortems
```

---

## Roadmap

- Automated PostgreSQL backups
- Per-client network isolation (clients unable to reach each other's subnets)
- SSH access layer 3: forced-command dispatcher for the provisioning path
- CI secret scanning (gitleaks) and pre-push checks — turning the `.gitignore` incident into pipeline policy
- Exploring: AI-assisted incident diagnosis on top of Alertmanager events (read-only, wrapper-constrained)

---

## About

Solo project by Alexander — self-taught, currently looking for **Junior Linux SysAdmin / IT Support (L2)** roles.

- CONTACT: 
https://www.linkedin.com/in/alexander-kozariychuk/
alexanderkozariychuk@gmail.com


## License

MIT — see [LICENSE](LICENSE).
