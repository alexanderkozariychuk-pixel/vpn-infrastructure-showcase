# Architecture

## Overview

Sovereign is a multi-hop AmneziaWG VPN service with two traffic tiers and a self-hosted client portal.

---

## Node topology

```
Standard tier:
  Client device → Bridge (St. Petersburg, RF IP) → Moldova (Chișinău) → Internet

Residential tier (high-resilience):
  Client device → Residential node (home RF IP) → Stockholm → Internet
```

---

## Nodes

| Node | IP | Provider | OS | Role |
|------|-----|----------|-----|------|
| Bridge | 212.67.14.85 | Beget | Ubuntu 24.04 | Entry node, AWG server :8443, hosts PWA |
| Moldova | 45.140.146.134 | Cloud4Box | Ubuntu 24.04 | Relay, standard-tier NAT exit |
| Stockholm | 185.104.151.175 | AEZA | Ubuntu 24.04 | Exit node for residential chain |
| Residential | 192.168.3.134 (LAN) | Home ISP | Ubuntu 24.04 (Samsung laptop) | AWG server :7443 + AWG client to Stockholm |

SSH access: `~/.ssh/id_ed25519` for all nodes.

---

## AmneziaWG configuration

All nodes run AmneziaWG (obfuscated WireGuard fork) with unique per-server obfuscation parameters. Standard WireGuard clients cannot connect.

**Bridge awg0 — standard tier entry:**
- Port: 8443/UDP
- Client subnet: 10.88.88.0/24
- Client pool (Basic): 10.88.88.42–99
- Obfuscation: Jc=3, Jmin=50, Jmax=1000, S1=72, S2=146

**Moldova awg0 — relay:**
- Receives forwarded traffic from Bridge
- MASQUERADE via ens3 — clients exit as 45.140.146.134
- NAT rules restored via PostUp on startup (no netfilter-persistent needed)

**Stockholm awg0 — residential exit:**
- Receives traffic from residential node
- MASQUERADE via enp0s3 — exits as 185.104.151.175

**Residential awg0 (client) + awg1 (server):**
- awg0: client to Stockholm, 10.200.200.2/32
- awg1: server for premium-tier client devices, port 7443, subnet 10.111.111.0/24

---

## Client portal (PWA)

Hosted on Bridge at `/opt/pwa`, served via Nginx.

```
pwa/
├── main.py           FastAPI app, v0.8.0
├── api/
│   ├── auth.py       JWT login/register
│   ├── config.py     GET /api/client/config (returns .conf)
│   ├── payment.py    Heleket webhook + plan management
│   └── clients.py    Admin peer status
├── services/
│   ├── provisioner.py  AWG keygen → Bridge SSH → DB → activate
│   └── heleket.py      Crypto payment gateway (scaffolded)
├── db/models.py      Users, Configs, Payments
└── static/index.html Single-page PWA (RU/EN, dark/light)
```

**Auto-provisioning flow (Basic plan):**
```
Payment confirmed
  → generate AWG keypair + PSK locally
  → find free IP from pool (10.88.88.42–99)
  → SSH to Bridge: awg set peer + append to awg0.conf
  → encrypt private key with Fernet, save to DB
  → activate 30-day subscription
  → client opens portal → GET /api/client/config → downloads .conf
```

---

## Policy routing (Bridge)

```
ip rule: from 10.88.88.0/24 lookup 200
table 200: default via <Moldova tunnel IP>
```

All client traffic enters Bridge via awg0, policy routing sends it to Moldova.

---

## IP addressing

| Subnet | Usage |
|--------|-------|
| 10.88.88.0/24 | Standard tier clients (Bridge awg0) |
| 10.88.88.1 | Bridge awg0 interface |
| 10.88.88.2–41 | Legacy / manually assigned peers |
| 10.88.88.42–99 | Auto-provisioning pool (Basic plan) |
| 10.200.200.0/30 | Bridge between residential node and Stockholm |
| 10.111.111.0/24 | Premium-tier client subnet (residential awg1) |

---

## Security notes

- Private keys stored Fernet-encrypted in PostgreSQL
- `.env` contains FERNET_KEY, DB credentials, Heleket keys — never committed
- SSH access scoped to `vpnadmin` user on Bridge for provisioner
- HTTPS/SSL pending domain purchase (sovrn.nexus)
