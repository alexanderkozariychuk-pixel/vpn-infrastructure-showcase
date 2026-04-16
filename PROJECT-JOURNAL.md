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

- ### API integration for 4VPS.SU  
  - Added official `FourVps` API client and discovery script.  
  - Successfully tested the script (data centers, tariffs) but Russian locations were not returned by the public API.  
  - Sent a support request asking for Russian DC and tariff IDs; waiting for reply.

- ### Documentation and repository updates  
  - Updated `PROJECT_JOURNAL.md` with progress.  
  - Created `configs/xray/chain-ru-to-moldova.json.example` – template for Xray chain (RU bridge → Moldova entry).  
  - Refactored `README.md`:  
    - Redesigned **Architecture** with mermaid diagram including Russian retranslator.  
    - Merged `Scripts` and `Automation (planned)` into a single **Automation and Scripts** section.  
    - Added links to provider scripts (`create_aeza_vps.py`, `create_vps.py`).  
    - Fixed table of contents.

- ### Learning outcomes  
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

---

## 2026-04-08

### Client configuration and documentation improvements

- Recreated and updated configuration files for several clients after connection issues.
- Successfully resolved Android 10 import problem caused by long filename — shortened the filename and recreated the config.
- Tested connection stability on newly created client configurations.
- Updated README.md:
  - Added badges for better visual presentation
  - Improved overall structure and Current Status section

### Progress:
- Client configuration process stabilized. Documentation quality noticeably improved.

---

## 2026-04-09

### Project Structure Audit & Refactoring

- Conducted a full audit of the repository structure.
- Reorganized the scripts/ directory for better separation of concerns:
    - install/ – installation and provisioning scripts
    - monitors/ – monitoring and healthcheck scripts
    - providers/ – provider-specific automation (Aeza, 4VPS)
    - utils/ – utility scripts (backup, key rotation, config generation)
- Renamed several scripts and folders for improved clarity and consistency.
- Created .github/workflows/ directory as a placeholder for future CI/CD.
- Added scripts/README.md with overview of the scripts directory.
- Cleaned up deprecated files and improved overall project organization.

### Progress: 
- The repository structure is now cleaner, more logical, and better prepared for further development and presentation.

---

## 2026-04-10
### Visual improvements and documentation update

- Created docs/screenshots/ directory for project visuals
- Added screenshots of the monitoring system:
    - Uptime Kuma dashboard overview
    - Live AmneziaWG status (awg show)
- Updated README.md with monitoring screenshots placed in a two-column table

### Progress: 
- Significantly improved visual presentation of the project. The README now better demonstrates the current state of monitoring and live tunnel status.

---

## 2026-04-11
### Terraform infrastructure preparation for Yandex Cloud

- Created Terraform module for Russian Bridge in infrastructure/terraform/yandex/
- Configured resources:
    - yandex_compute_instance (2 vCPU, 4 GB RAM, Ubuntu 24.04)
    - VPC network and subnet
    - Cloud-init for basic hardening (SSH key, UFW, package updates)

- Added proper .gitignore rules to protect sensitive files (terraform.tfvars, state files, credentials)
- Created terraform.tfvars.example template
- Successfully ran terraform init and terraform validate
- terraform plan completed without errors (3 resources to create)

### Progress: 
- Infrastructure code for Russian Bridge is ready for deployment.

---

## 2026-04-12
### Terraform modules development

- Created Terraform module for Aeza provider (infrastructure/terraform/aeza/)
- Configured aeza_service resource for France Exit Node
- Added aeza_products data source and fixed validation issues
- Improved .gitignore to protect sensitive Terraform files
- Prepared module for simpler Exit Node (2 vCPU, 4 GB RAM)

### Progress:
- Aeza Terraform module is ready for testing.

---

## 2026-04-14

### Architecture simplification: primary focus on AmneziaWG

- **Decision**: Xray (VLESS+XHTTP) removed from the main multi‑hop chain. The primary protocol is now **AmneziaWG** on all hops (client → Russia → Moldova → France). Xray remains only as an **optional fallback** for clients that cannot use AmneziaWG (e.g., UDP‑restricted mobile networks).
- **Updated documentation**:
  - `architecture.md` – rewrote Overview, Node Roles, Data Flows, Technology Stack, Monitoring, Security, Planned Extensions to reflect the new design.
  - `README.md` – updated Current Status, Tech Stack, Planned automation; removed references to Xray from the core description.
  - `PROJECT-JOURNAL.md` – added this entry.

### Ansible automation for AmneziaWG chain

- **Enhanced role `amneziawg`**:
  - Added automatic key generation (`wg genkey` / `wg pubkey`) when private key is not provided.
  - Created Jinja2 template `awg0.conf.j2` that supports multiple peers (via `awg_peers` list).
  - Added tasks for enabling IP forwarding, NAT (for exit node), and starting the service.
  - Handlers for restarting `awg-quick@awg0`.
- **Created inventory and group variables**:
  - `inventory/production.yml.example` – groups `bridge`, `entry`, `exit`.
  - `group_vars/bridge.yml.example`, `entry.yml.example`, `exit.yml.example` – node‑specific variables (IPs, keys, peers, NAT flag).
- **Playbook `site.yml`** – applies role `amneziawg` to all nodes.

### Terraform backend setup (attempt)

- Created a temporary configuration to set up Yandex Object Storage bucket for remote state.
- Faced `PermissionDenied` errors due to cloud account restrictions (trial period ended, no active billing). Bucket creation via CLI also failed.
- **Decision**: Postpone backend setup until account is activated (or use Terraform Cloud / local state for now). Documented the issue in journal.

### Progress

- All Terraform modules (Aeza, Yandex Cloud) are ready and validated.
- Ansible roles for AmneziaWG and common base setup are ready.
- The architecture is simplified and focused on performance.
- Next steps: provision VPS (when funds available), run Ansible, test the full chain.

---

## 2026-04-15

### CI/CD pipeline with GitHub Actions

#### Initial setup
- Created `.github/workflows/lint.yml` to automate code quality checks on every push and pull request.
- Workflow includes:
  - Terraform formatting check (`terraform fmt -check`)
  - Terraform validation (without backend init) for Aeza and Yandex modules
  - Ansible syntax check for all playbooks
  - ShellCheck for `.sh` scripts
  - Ruff linting for Python scripts

#### Fixes and adjustments
- **Terraform**: ran `terraform fmt -recursive` locally to fix formatting issues; committed changes.
- **Ansible**:
  - Moved `ansible.cfg` to repository root and configured `roles_path = ./infrastructure/ansible/roles`.
  - Fixed misplaced `handlers` section in `common` role – moved to `handlers/main.yml`.
  - Corrected `vars` syntax in `deploy-bridge.yml` (list → dictionary).
  - Removed empty `wireguard.yml` playbook.
- **Python** (ruff):
  - Removed unused import `os` in `create-aeza-vps.py`.
  - Removed extraneous `f`‑prefix from f‑strings without placeholders in `create-vps.py`.
  - Deleted unused variable `result` in `create-vps.py`.
- **CI execution**: All steps passed successfully after fixes.

#### CI badge
- Added a status badge to `README.md`:

### Progress:
- The repository now has a fully functional CI pipeline that validates Terraform, Ansible, shell, and Python code automatically.
- The green badge in README demonstrates project maturity and adherence to quality standards.
- Any future pull request will be checked automatically, reducing the risk of broken code.

--- 

## 2026-04-16

### CI/CD pipeline improvements

- Enhanced `.github/workflows/lint.yml`:
  - Added caching for Terraform plugins and pip dependencies to speed up runs.
  - Integrated `terraform plan` with real API keys (Aeza, Yandex Cloud) using GitHub Secrets.
  - Set `continue-on-error: true` for `plan` steps to avoid false failures.
  - Added `terraform init` and `validate` without backend for both modules.
- Fixed all linting errors:
  - Terraform formatting (`terraform fmt -recursive`).
  - Ansible syntax: moved `handlers` to separate file, corrected `vars` in `deploy-bridge.yml`, removed empty `wireguard.yml`.
  - Python: removed unused import, extraneous `f`-prefix, unused variable.
- CI now runs successfully on every push/PR, providing a green badge in README.

### Documentation update

- Rewrote `docs/setup-tutorial.md` to reflect the primary AmneziaWG‑only chain:
  - Removed Xray from the core installation steps (moved to optional fallback).
  - Added key generation step for AmneziaWG.
  - Clarified IP addressing for bridge/entry/exit nodes.
  - Added note about optional Xray fallback.

### Progress: 

- All Terraform modules (Aeza, Yandex Cloud) validated with `plan`.
- Ansible roles for AmneziaWG and common base setup ready.
- CI/CD pipeline fully functional.
- Documentation aligned with the simplified architecture.

---

## Next steps (planned for 2026-04-17)

- Add more detailed badges to README.md
- Refine `docs/troubleshooting.md` with real‑world issues and solutions.
- Prepare for actual deployment when cloud funds become available.


## Long-term Plans

- Activate Russian Bridge node with full Policy-Based Routing
- Migrate all clients from Moldova to Russian Bridge
- Complete automation of deployment and configuration processes
- Migrate monitoring stack to a dedicated VPS in the Netherlands
- Implement automatic failover using residential proxy pool
- Develop custom Prometheus exporter for AmneziaWG metrics
- Achieve full GitOps workflow for the infrastructure
- Prepare detailed portfolio materials for Junior DevOps / Linux SysAdmin positions
