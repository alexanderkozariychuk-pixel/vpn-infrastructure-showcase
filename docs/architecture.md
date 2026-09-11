# Architecture

Current as of September 2026. Addresses are shown as placeholders
throughout — operational IPs are not published.

## Overview

Sovereign is a multi-hop AmneziaWG VPN service with policy-based split
tunnelling and a self-hosted client portal. Three hosts, each with a
single responsibility.

---

## Node topology

```
Client device
   → Entry node    (RF, obfuscated AmneziaWG endpoint)
   → Backbone      (AmneziaWG tunnel between the two nodes)
   → Exit node     (DE, NAT to the internet)

Domestic-destined traffic diverges at the entry node and exits locally,
bypassing the backbone entirely.
```

| Role | Location | Responsibility |
|------|----------|----------------|
| **Entry** | RF | Public AmneziaWG endpoint, client peers, split-tunnel policy |
| **Exit** | DE | Backbone endpoint, NAT to the internet |
| **App server** | RF | Client portal and database — deliberately separate from the data plane |

The app server is never co-located with a VPN node. Docker's own
iptables and NAT chains conflict with WireGuard forwarding when they
share a host; this was established by failure, not by preference, and is
now a standing constraint on how servers are allocated.

---

## AmneziaWG configuration

Every interface runs unique per-node obfuscation parameters
(Jc, Jmin, Jmax, S1, S2, H1–H4). Standard WireGuard clients cannot
connect by design: the plain WireGuard handshake is fingerprinted and
throttled by DPI on some mobile carriers, while the obfuscated stream
passes as generic UDP.

**Entry — `awg0`, client-facing**

- UDP, non-standard port
- Client subnet `10.88.88.0/24`
- Auto-provisioning pool `10.88.88.42–99`
- Client MTU 1300

**Entry — `awg1`, backbone**

- Point-to-point `10.77.77.2/30` toward the exit node
- `AllowedIPs = 0.0.0.0/0`, persistent keepalive

**Exit — `awg0`, backbone endpoint**

- Point-to-point `10.77.77.1/30`
- MASQUERADE to the internet; NAT rules applied through PostUp/PostDown
  rather than a persistence service

---

## Split tunnelling

Domestic services stay reachable without the client disabling the VPN,
and without any change to client configuration — the whole mechanism is
server-side.

```
ipset  ru_nets        hash:net, ~11.4k country prefixes from RIPE
mangle PREROUTING     mark 0x64 on client traffic destined to ru_nets
ip rule  99           fwmark 0x64 → main table   (local exit)
ip rule 100           from 10.88.88.0/24 → table 200  (backbone)
table  200            default via the backbone peer
```

Rule 99 sits ahead of rule 100, so marked traffic leaves locally and
everything else goes through the tunnel.

The weekly prefix refresh is built to fail safe: it assembles a temporary
set, refuses to proceed if the fetched list contains fewer than 8000
prefixes — guarding against a registry outage returning garbage — and
then swaps atomically, so the tunnel is never without a list mid-update.

---

## Client portal

FastAPI application and PostgreSQL, both in Docker on the app server.
The application binds to loopback only and is reached through nginx;
it is never exposed directly.

```
pwa/
├── main.py             FastAPI app, route definitions
├── api/
│   ├── auth.py         registration, JWT login, password reset
│   ├── config.py       config delivery to the authenticated owner
│   ├── payment.py      order creation and gateway webhooks
│   └── support.py      support form
├── services/
│   ├── provisioner.py  keygen → free address → wrapper call → DB → activate
│   ├── freekassa.py    card/SBP gateway: signing and notification checks
│   ├── heleket.py      crypto gateway
│   └── mailer.py       transactional mail over an HTTPS API
├── db/models.py        users, configs, payments
└── static/             landing, policy pages, single-page portal
```

**Provisioning flow**

```
payment notification verified
  → generate keypair and preshared key
  → read the peer list from the entry node, pick a free address
  → add the peer through the validating wrapper
  → encrypt the private key, store the config
  → activate the subscription
```

The address search is seeded from the node's live state rather than the
local table: that table is a mirror, and it is empty after a fresh
migration and stale after any peer issued by hand.

---

## Access model

The portal never holds administrative credentials on the VPN nodes.

- A dedicated low-privilege user exists on each node solely for
  provisioning, with its own keypair.
- `sudoers` restricts that user to a small set of validating wrapper
  scripts — no raw `awg`, no `cat`, no `journalctl`.
- The write wrapper re-validates every argument server-side: key format,
  subnet membership, duplicate key, duplicate address. A caller cannot
  reach live WireGuard state except through those checks.
- Host key checking is enforced with a pre-populated `known_hosts`
  mounted read-only into the container.

---

## Addressing

| Subnet | Usage |
|--------|-------|
| `10.88.88.0/24` | Client subnet on the entry node |
| `10.88.88.1` | Entry node `awg0` interface |
| `10.88.88.2–41` | Manually issued peers |
| `10.88.88.42–99` | Auto-provisioning pool |
| `10.77.77.0/30` | Backbone between entry and exit |

---

## Security notes

- Client private keys are Fernet-encrypted at rest and decrypted only on
  demand for delivery to their owner. They are never logged.
- Passwords are stored as argon2 hashes.
- `.env` holds encryption keys, database credentials and gateway
  secrets. It is excluded from the repository and from deployment sync,
  and exists only on the server.
- Payment amounts come from a server-side price table; values supplied
  in a request are never trusted.
- Gateway notifications are verified by signature, by source address
  read from a header nginx sets rather than forwards, and by
  idempotency on the order id.
- Every node runs a default-deny firewall, verified before the policy is
  switched: a held-open session survives, a fresh connection succeeds,
  monitoring scrapes still pass.
- Kernel modules are registered with DKMS so they survive kernel
  upgrades; firewall rules and peers live in configuration files rather
  than only in runtime state.

---

## Earlier topologies

The repository history contains references to a relay chain through
additional countries and a residential-exit tier. Both were retired in
July 2026 after real-world testing; see `archive/` for the approaches
that were dropped and why.
