# Multi-Hop Obfuscated VPN Infrastructure

[![GitHub last commit](https://img.shields.io/github/last-commit/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)](https://github.com/alexanderkozariychuk-pixel/vpn-infrastructure-showcase)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED.svg?logo=docker&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-Ubuntu_24.04-FCC624.svg?logo=linux&logoColor=black)
[![WireGuard](https://img.shields.io/badge/AmneziaWG-88171A?logo=wireguard)](https://github.com/amnezia-vpn/amneziawg)

---

**Production-grade censorship-resistant VPN** with multi-hop routing, AmneziaWG obfuscation, and a self-hosted client portal with automated peer provisioning.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Current Status](#current-status)
- [Tech Stack](#tech-stack)
- [Client Portal](#client-portal)
- [Auto-Provisioning](#auto-provisioning)
- [Next Steps](#next-steps)
- [Troubleshooting](#troubleshooting)

---

## Project Overview

Sovereign is a production VPN service targeting users behind DPI-based censorship and allowlist filtering. The infrastructure is designed around AmneziaWG — a fork of WireGuard with traffic obfuscation parameters that defeat deep packet inspection — running across multiple VPS nodes and a residential home node.

The project includes a full client-facing PWA portal (registration, authentication, automated config delivery, subscription management) and a billing scaffold ready for crypto payment integration.

---

## Architecture

```
Standard tier (free / basic):
  Device → Bridge (St. Petersburg, RF IP) → Moldova (relay) → Internet

Premium tier (allowlist bypass):
  Device → Residential node (home RF IP) → Stockholm → Internet
```

### Nodes

| Node | Location | Provider | Role |
|------|----------|----------|------|
| Bridge | St. Petersburg | Beget | Entry node, AWG server for clients, hosts PWA |
| Moldova | Chișinău | Cloud4Box | Relay, standard-tier exit via NAT |
| Stockholm | Stockholm | AEZA | Exit node for residential chain |
| Residential | Home (RF) | ISP (dynamic IP) | Ubuntu 24.04 laptop — AWG server for premium clients, AWG client to Stockholm |

### Routing logic

All nodes run AmneziaWG with unique obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4) generated per server. Client configs include matching parameters — standard WireGuard clients cannot connect.

Standard-tier clients connect to Bridge on port 8443 and exit through Moldova's IP. The residential node (home ISP address) serves as a first hop that is indistinguishable from normal home traffic, providing the highest resilience against allowlist filtering. Traffic from the residential node exits through Stockholm.

---

## Current Status

| Component | Status | Details |
|-----------|--------|---------|
| Bridge (St. Petersburg) | ✅ Operational | Entry node, 20+ active client peers |
| Moldova | ✅ Operational | Relay, standard-tier NAT exit |
| Stockholm | ✅ Operational | Primary exit for residential chain |
| Residential node | ✅ Operational | AWG server :7443 + client to Stockholm |
| Client portal (PWA) | ✅ v0.8.0 deployed | Registration, auth, config delivery, subscription |
| Auto-provisioning | ✅ Implemented | Key generation, SSH peer addition, encrypted DB storage |
| Crypto billing (Heleket) | 🔧 Scaffolded | Awaiting domain + credentials |
| Client configs | ✅ 20+ peers | Standard tier (Bridge → Moldova) |

---

## Tech Stack

**Infrastructure:**
- AmneziaWG — obfuscated WireGuard fork, custom parameters per node
- Ubuntu 24.04 on all nodes
- Policy-based routing (ip rule / ip route / custom tables)
- iptables MASQUERADE for NAT at exit nodes

**Backend (PWA):**
- FastAPI (Python 3.12) — async REST API
- PostgreSQL — users, configs (Fernet-encrypted keys), payments
- Alembic — database migrations
- Docker Compose — container orchestration on Bridge
- Cryptography (Fernet) — symmetric encryption of private keys at rest

**Frontend:**
- Vanilla JS single-page application (no framework)
- Self-hosted, served from Bridge via Nginx
- RU/EN i18n, dark/light themes
- Tabbed setup instructions (iOS / Android / Windows)

**Billing:**
- Heleket crypto payment gateway (scaffolded)
- Webhook verification (MD5 signature with PHP-compatible serialization)
- Server-side price table — client amounts never trusted

---

## Client Portal

The PWA is accessible at the Bridge node's IP. It provides:

- Registration and JWT-based authentication
- **My Config** — displays the user's personal AmneziaWG `.conf` with syntax highlighting; one-click copy and download
- **Payment** — current subscription status, plan selection (Basic / Extended), order history
- **Support** — contact information
- **Admin SRE panel** — peer status, traffic, logs from Moldova, AI-assisted infrastructure analysis

After a successful payment, `provision_basic()` automatically:
1. Generates a fresh AWG keypair and PSK locally
2. Finds the next available IP from the Basic pool (`10.88.88.42–99`)
3. Adds the peer to Bridge via SSH (`awg set` + appends to `awg0.conf`)
4. Saves the encrypted config to PostgreSQL
5. Activates the 30-day subscription

---

## Auto-Provisioning

`services/provisioner.py` handles the full lifecycle of a new paid client without manual intervention. Private keys and PSKs are encrypted with Fernet (AES-128-CBC) before storage. The decrypted `.conf` is generated on-demand at `GET /api/client/config` and never stored in plaintext.

SSH access from the PWA container to Bridge uses the same key-based auth as manual administration, scoped to the `vpnadmin` user.

---

## Next Steps

- Purchase domain (`sovrn.nexus`) and configure DNS — required for HTTPS and Heleket `url_callback`
- Activate Heleket credentials and complete billing integration
- Complete residential chain routing: Phone → Residential → Stockholm (routing fix in progress)
- PostgreSQL automated backups
- Support form with email ticket delivery (`sovereign.support@gmail.com`)
- "Forgot password" flow (requires SMTP)
- Per-client iptables isolation (clients cannot reach each other's subnets)
- Uptime Kuma monitoring for all nodes

---

## Troubleshooting

The main real-world challenge driving this project is **allowlist-based filtering** on Russian mobile networks — only pre-approved domains/IPs are accessible, UDP is throttled or blocked entirely.

Key lessons from production:

- **Cloudflare proxy (orange cloud) is throttled to 16 KB/s** by Russian ISPs as of mid-2025. The site must resolve directly to a Russian IP — not through any CDN.
- **Standard WireGuard is blocked** by DPI on most Russian mobile networks. AmneziaWG with randomized obfuscation parameters passes as generic UDP traffic.
- **Debug iptables LOG rules** in PREROUTING can silently consume gigabytes of disk within hours on a relay node. Keep `iptables-save` clean.
- **Process substitution (`<(...)`) fails** when piped through SSH. Use temp files for passing secrets to `awg set preshared-key`.

Detailed notes are tracked in [`PROJECT-JOURNAL.md`](PROJECT-JOURNAL.md).
