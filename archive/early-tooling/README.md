# Scripts

Utility and automation scripts for the Sovereign VPN infrastructure.

## Status legend

- ✅ **Production-active** — used in current operations
- 🔧 **Available** — works, used occasionally
- 📦 **Reference** — kept for documentation, not actively used

---

## install/

| Script | Status | Description |
|--------|--------|-------------|
| `install-amneziawg.sh` | 🔧 Available | One-click AmneziaWG install on fresh Ubuntu server |
| `provision-new-vps.sh` | 🔧 Available | Base VPS setup: user, SSH keys, firewall hardening |
| `install-monitoring.sh` | 📦 Reference | Monitoring stack (Uptime Kuma, Prometheus) — not deployed |

---

## monitors/

| Script | Status | Description |
|--------|--------|-------------|
| `awg-status.py` | 📦 Reference | Collects AWG peer metrics — was used with Uptime Kuma |
| `healthcheck.sh` | 🔧 Available | Checks AWG and critical ports health |

---

## utils/

| Script | Status | Description |
|--------|--------|-------------|
| `rotate-keys.sh` | 🔧 Available | Rotate keys for an existing client peer |
| `backup-configs.sh` | 🔧 Available | Timestamped backup of critical config files |
| `generate-config.sh` | 📦 Reference | Client config generation (superseded by auto-provisioning) |

---

## providers/

| Script | Status | Description |
|--------|--------|-------------|
| `aeza/create-aeza-vps.py` | 🔧 Available | Provision VPS on AEZA via API (Stockholm node provider) |

---

## Production operations

Day-to-day operations (adding peers, fixing PSK, clearing disk) are covered in [`docs/runbook.md`](../docs/runbook.md).

Auto-provisioning of new client peers after payment is handled by `pwa/services/provisioner.py`.
