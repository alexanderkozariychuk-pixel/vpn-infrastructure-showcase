# Multi-Hop VPN Infrastructure

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE(MIT))
[![Project Status](https://img.shields.io/badge/Status-Active-green.svg)](README.md)

---

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Current Status](#current-status-)
- [Tech Stack](#tech-stack)
- [Key Features](#key-features)
- [Next Steps](#next-steps)
- [Setup](#setup)
- [Scripts](#scripts)
- [Troubleshooting](#troubleshooting)

---

## Project Overview
Multi-hop VPN infrastructure for stable, private connectivity, designed to bypass DPI restrictions and provide monitoring and failover capabilities.

---

## Architecture

```mermaid
graph LR
    Clients["Clients: 4 devices"] --> Entry["VPS Moldova – Entry\nAmneziaWG + Xray + 3X-UI"]
    Entry --> Monitoring["Monitoring Node\nUptime Kuma\nNode Exporter\nPrometheus"]
    Entry --> Future["Future Relay Node\nGermany – Routing & NAT"]
    Future --> Proxy["Proxy Pool\nResidential IPs"]
```
---

## Current Status ✅
- VPS1 configured and running (Moldova)
- VPN tunnel (AmneziaWG) established
- Config files created for 4 clients
- Monitoring setup:
    - Uptime Kuma + Telegram alerts
    - Node Exporter + Prometheus (metrics)
    - Custom script for AmneziaWG UDP:443 check

---

## Tech Stack
- **Networking**: WireGuard, AmneziaWG
- **Infrastructure & Automation**: Terraform (planned), Ansible (planned)
- **Monitoring**: Prometheus, Node Exporter, Uptime Kuma
- **Scripting**: Bash

---

## Key Features
- DPI bypass via obfuscation layer
- Multi-client VPN configuration
- Observability with metrics and alerts
- Failover testing scripts

## Next Steps
- Add Relay Node in Germany
- Automate deployment via Terraform + Ansible
- Expand Grafana dashboards
- Implement proxy pool for failover

## Setup
See [docs/setup-tutorial.md](docs/setup-tutorial.md)

## Scripts

Utility scripts to automate common tasks. All scripts are located in the [`scripts/`](scripts/) directory and require execution on the VPS with appropriate permissions.

| Script | Description |
|--------|-------------|
| [`rotate-keys.sh`](scripts/rotate-keys.sh) | Generate new keys for an existing AmneziaWG client, update the server config, and restart the service. |
| [`backup-configs.sh`](scripts/backup-configs.sh) | Create a timestamped archive of all critical configuration files (AmneziaWG, Xray, monitoring). |
| [`install-monitoring.sh`](scripts/install-monitoring.sh) | Deploy the full monitoring stack (Uptime Kuma, Prometheus, Node Exporter, Alertmanager) via Docker on a fresh VPS. |
| [`deploy-client.sh`](scripts/deploy-client.sh) | Wrapper around the AmneziaWG installer to create a new client and print its configuration. |
| [`healthcheck.sh`](scripts/healthcheck.sh) | Verify the status of AmneziaWG, Xray, and essential ports. Returns exit code 0 if all healthy. |
| [`setup-new-vps.sh`](scripts/setup-new-vps.sh) | Perform base setup on a new VPS: create a user, configure SSH keys, disable password authentication, set up firewall. |
| [`check_awg.sh`](scripts/check_awg.sh) | Monitor AmneziaWG health and push status to Uptime Kuma (used in cron). |
| [`install-amneziawg.sh`](scripts/install-amneziawg.sh) | One‑click installation of AmneziaWG on a fresh Ubuntu server (based on the official installer). |

All scripts are provided as examples – adjust variables, paths, and placeholders to match your environment. Run them with `sudo` where required.

## Troubleshooting

### Real-World Challenge

During testing, I encountered mobile network restrictions where only whitelisted websites were accessible.

This project includes troubleshooting and analysis of:
- DPI filtering behavior
- UDP traffic instability
- VPN protocol blocking

See details in [docs/troubleshooting.md](docs/troubleshooting.md)
