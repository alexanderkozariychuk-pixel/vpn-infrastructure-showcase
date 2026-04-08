# Project Journal

This document logs the key milestones and decisions made during the development of the VPN infrastructure.

---

## 2026-03-29

- **Initial server setup**  
  - VPS (Moldova) provisioned, basic security (SSH keys, UFW).  
  - AmneziaWG installed, configured on UDP/443 with obfuscation (Jc, Jmin, Jmax, H1‑H4).  
  - First client config generated, tested over Wi‑Fi – connection established.

---

## 2026-03-30

- **Added Xray + 3X‑UI**  
  - Installed 3X‑UI panel, created VLESS+Reality inbound on TCP/443.  
  - Generated client links, tested with Hiddify.

- **Monitoring stack deployed**  
  - Docker compose with Uptime Kuma, Prometheus, Node Exporter, Alertmanager.  
  - Created push script (`check_awg.sh`) for AmneziaWG health, added cron job.

- **Mobile network experiments**  
  - Observed intermittent handshake failures on mobile network.  
  - Discovered that waiting 10–30 seconds or toggling Airplane mode often restores connectivity.  
  - Documented findings in `troubleshooting.md` (dynamic DPI / temporary blacklisting).

---

## 2026-03-31

- **Prepared public repository**  
  - Cloned private repository without history (`git clone --depth 1`).  
  - Cleaned all sensitive data: replaced IPs with `<VPS_IP>`, keys with `<PRIVATE_KEY>`, tokens with `<BOT_TOKEN>` etc.  
  - Created new public repository on GitHub, pushed cleaned code as first commit.

- **Documentation updates**  
  - Completed `architecture.md` with high‑level diagram, component tables, data flows, security considerations.  
  - Enhanced `troubleshooting.md` with detailed test table, results, and conclusion about dynamic filtering.  
  - Updated `README.md`: removed live status badges (to avoid exposing IP), kept static tech stack icons.

- **Project journal started**  
  - Added this file to track progress and decisions.
 
---

  ## 2026-04-01

- **Repository enrichment**  
  - Added configuration examples (`configs/amneziawg/`, `configs/xray/`, `configs/monitoring/`) with placeholders.  
  - Added utility scripts (`scripts/rotate-keys.sh`, `scripts/backup-configs.sh`, `scripts/healthcheck.sh`, `scripts/setup-new-vps.sh`, `scripts/check_awg.sh`, `scripts/install-amneziawg.sh`).  
  - Prepared initial templates for automation (`ansible/`, `terraform/`) – structure created, content to be filled tomorrow.  
  
- **Infrastructure expansion**  
  - Created two additional AmneziaWG clients.  
  - Now total of 6 clients configured and active.

- **Documentation**  
  - Added a **Scripts** section to `README.md` describing all scripts.  
  - Updated `PROJECT_JOURNAL.md` with today's work.

---

## 2026-04-02

- **Created a basic Ansible playbook for installing AmneziaWG**

- **Added project participation and security guidelines**
Created the CONTRIBUTING.md and SECURITY.md files to encourage collaboration and responsible disclosure.

- **Stability Experiments**
Run four tests on the entry node in Moldova (service restart, MTU change, temporary firewall blocking, push monitoring).
The results are documented in the troubleshooting.md file.
Key finding: Mobile clients do not automatically reconnect after service restart (requires switching to airplane mode).
Monitoring and recovery from temporary blocking work as expected.

- **Documentation Updates**
Revised the README.md file to reflect planned automation for Aeza (Python API script).
Updated the PROJECT_JOURNAL.md file to reflect current progress.

- **Plan Change**
Terraform/Python integration for Aeza has been postponed until tomorrow. The focus remains on reliability and observability.

---

## 2026-04-03
- **Aeza API script**: Added `scripts/aeza_create_vps.py` – Python script using official Aeza client to automate VPS creation (France exit node).
- **New architectural decision**: Introduced a **Russian retranslator (bridge) node** with an IP from a subnet associated with whitelisted domains (VK, Yandex, etc.). This node will be the first hop for clients, masking the entire multi‑hop chain.
- **Provider selection for RU node**: Preferred – **4VPS.SU** (small, low‑profile, unlimited traffic). Fallback – Aeza Moscow (unified API).
- **Updated Future Roadmap** (see below).

---

## 2026-04-04

- **API integration for 4VPS.SU**  
  - Added official `FourVps` API client and discovery script.  
  - Successfully tested the script (data centers, tariffs) but Russian locations were not returned by the public API.  
  - Sent a support request asking for Russian DC and tariff IDs; waiting for reply.

- **Documentation and repository updates**  
  - Updated `PROJECT_JOURNAL.md` with progress.  
  - Created `configs/xray/chain-ru-to-moldova.json.example` – template for Xray chain (RU bridge → Moldova entry).  
  - Refactored `README.md`:  
    - Redesigned **Architecture** with mermaid diagram including Russian retranslator.  
    - Merged `Scripts` and `Automation (planned)` into a single **Automation and Scripts** section.  
    - Added links to provider scripts (`create_aeza_vps.py`, `create_vps.py`).  
    - Fixed table of contents.

- **Learning outcomes**  
  - Gained hands‑on experience with Python virtual environments (`venv`), third‑party API integration, async debugging, and structuring automation scripts. 
---

## 2026-04-05

### Ansible role for Russian bridge node
- Created complete Ansible role `xray-relay`:
  - Tasks: install Xray, generate Reality keys and UUID, deploy config template, open firewall port, start service.
  - Handlers: restart Xray on config change.
  - Template: `config.json.j2` with inbound from clients (VLESS+Reality) and outbound to Moldova entry node (VLESS+XHTTP).
  - Playbook `deploy-bridge.yml` and updated inventory example (`production.yml.example`) with `ru_bridge` group.
  - Group variables example (`all.yml.example`) for Moldova node parameters (IP, UUID, public key, shortId).
- Role is ready for testing as soon as a Russian VPS is provisioned.

### Monitoring enhancement (Uptime Kuma)
- Replaced old bash script `check_awg.sh` with Python script `awg_status.py`.
- Script collects extended metrics: number of peers, total received/transmitted bytes, latest handshake age.
- Sends status and detailed message to Uptime Kuma push monitor using only standard library (no extra dependencies).
- Added example file `awg_status.py.` to repository (placeholders for IP and token).
- Updated `.gitignore` to exclude local secrets (`awg_status_local.py`, `.env`, etc.).

### Documentation and housekeeping
- Updated `README.md`:
  - Reflected new architecture with Russian bridge, Moldova entry, France exit.
  - Merged `Scripts` and `Automation (planned)` into a single `Automation and Scripts` section.
  - Corrected script paths according to new `scripts/` structure (maintenance/, monitoring/, setup/, providers/).
- Updated `architecture.md` with detailed three‑hop chain description, data flows, and planned extensions.
- Polished `.gitignore` to exclude Python cache, IDE files, logs, and local secrets.
- Updated `PROJECT_JOURNAL.md` (this entry) and prepared future roadmap.

### Current blockers
- Still waiting for 4VPS.SU support reply (Russian DC and tariff IDs). If no answer by mid‑week, will switch to alternative provider (Beget or FirstVDS).

---
## 2026-04-06
- Full migration to Pop!_OS 24.04 LTS as primary workstation
  - Successfully installed Pop!_OS 24.04 (COSMIC DE) on ASUS laptop.
  - Resolved multiple installation issues:
  - Fixed MokListRT: Volume Full error by resetting Secure Boot keys in BIOS.
  - Handled Rufus ISOHybrid limitations (DD Image mode).

- Installed and configured AmneziaVPN.
  - Switched from GUI client to CLI (awg-quick) due to better stability and control.

### Result: Main working machine is now fully on native Linux. VPN client operates via command line.

---

## 2026-04-07
- Major documentation overhaul – **Architecture v2**
- Completely reworked docs/architecture.md:
  - Updated main Mermaid diagram to reflect Architecture v2 with Russian Bridge and Policy-Based Routing.
  - Improved overall document structure and readability.
  - Added new sections: Overview, Key Design Decisions, enhanced Node Roles, Data Flows, and better Technology Stack explanation.

- Worked extensively with VS Code + Markdown Preview Enhanced for proper Mermaid rendering.

### Result: Architecture documentation is now significantly more structured, visual, and presentation-ready.

## Short-term Plans (next 3–4 days)

- Finalize and activate Russian Bridge node (provisioning + testing)
- Implement and test full Policy-Based Routing on the Russian Bridge (selective routing)
- Migrate all clients from Moldova node to Russian Bridge
- Complete Ansible roles for AmneziaWG and Xray deployment
- Add GitHub Actions (basic linting + validation)

## Long-term Plans

- Deploy dedicated Monitoring node in the Netherlands
- Implement automatic failover using residential proxy pool
- Develop custom Prometheus exporter for AmneziaWG metrics
- Achieve full GitOps workflow for the entire infrastructure
- Prepare detailed portfolio materials based on this project for Junior DevOps / Linux SysAdmin positions
