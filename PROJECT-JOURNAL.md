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

## 2026-04-17

### README badges enhancement
- Added new badges to `README.md`:
  - Terraform version badge
  - Prometheus badge
  - Grafana badge
  - WireGuard badge
  - GitHub last commit badge
- These badges improve the project's visual appeal and provide quick status information.

### Troubleshooting section expansion
- Added a detailed troubleshooting entry about VPN failures when using an iPhone as a Personal Hotspot.
- The new section (1.5 `docs/troubleshooting.md`) covers:
  - Problem description and environment
  - Hypothesis (iOS NAT + carrier DPI)
  - Test methodology including TTL analysis
  - Results and conclusions
  - Recommended solutions (VPN on each client device, TTL adjustment, dedicated router)
- This addition demonstrates systematic problem analysis and practical troubleshooting skills.

## 2026-04-18

### Next‑generation Telegram bot with AI integration

- **Monitoring migration**:
  - Created a new Telegram bot with Google Gemini integration (`ai-bot.py`).
  - Configured a systemd service for automatic startup.
  - Updated Uptime Kuma notification settings (replaced old bot token with the new one).
  - Removed the old bot instance, resolved `Conflict: terminated by other getUpdates request`.

- **Sudoers configuration**:
  - Added `/etc/sudoers.d/ai-bot` rules to allow `awg show`, `journalctl`, `systemctl restart` without password.

- **Currently implemented commands**:
  - `/status` – shows AmneziaWG status (peers, handshake).
  - `/logs [N]` – returns last N lines of `awg-quick@awg0` log.
  - `/restart` – restarts the service after confirmation.
  - `/help` – usage instructions.
  - Natural language queries are handled by Gemini (log analysis, advice).

- ### Progress:
  - The bot is running; notifications now come from the new bot.
  - Basic monitoring commands are operational.

---

## 2026-04-19
### AI Integration & Security Foundations

  #### AI Diagnostics Engine:
  - Successfully integrated Google Gemini 3.0 (Flash Preview) as the core brain for system analysis.
  - Implemented the /analyze command, enabling the bot to process system metrics and logs to provide SRE-level recommendations.
  - Configured bilingual (EN/RU) output for AI-generated reports.

  #### Security & Access Control:
  - Implemented a centralized auth_filter for the entire bot.
  - Hardened Security: Secured all entry points, including text commands and inline button callbacks (preventing unauthorized service restarts).
  - Configured sudoers rules for the bot's operation.

  ### Ongoing Development (In Progress):
  - Client Management: Module logic developed but currently blocked by file system permissions (access to private/public keys).
  - Log System: Encountered an issue where /logs returns outdated data (dated April 2nd). Investigating the source of the cache/log rotation issue.
  - Filtration: Advanced log filtering (priority-based) is planned but not yet deployed.

### Progress:
  - The bot is now "AI-aware" and secure.
  - Core communication channel with Gemini is stable and functional.

### Next steps:
  - Debug the /logs command to ensure real-time data fetching.
  - Fix permission issues for the /addclient module to allow key generation and config writing.
  - Implement granular log filtering (-p flags).

---

## [2026-04-20] — Phase: Monitoring & AI Integration

### 🛠 Done Today:
- **Telegram Bot Core:** Re-engineered the bot to work with AmneziaWG (AWG). 
- **Infrastructure:**
    - Integrated `subprocess` calls for `awg show`, `journalctl`, and `dmesg`.
    - Implemented a secure authentication filter (LDAP-style ID check) to prevent unauthorized access.
- **Async Transformation:** - Moved all blocking system calls and AI requests to `asyncio.run_in_executor`. 
    - This fixed the "Timed out" issues and `409 Conflict` errors by keeping the Telegram event loop alive.
- **Peer Management:** Added functionality to add/delete clients directly from the Telegram UI (including automatic config generation for the client).
- **Project Structure:** Migrated the codebase from `Downloads` to the official repository path: `monitoring/ai-bot-monitoring/`. Sanitized all sensitive API keys and tokens.

### 🧠 AI Analysis Progress:
- Configured **Gemini 3 Flash** as the primary diagnostic engine.
- Implemented a "Fallback" mechanism: if the AI times out, the bot now sends raw system logs instead of an error message.
- Tested connectivity; server-side access to Google API confirmed (HTTP 200/404).

---

## 2026-04-21

### 🛠 Done Today

#### AI Bot Monitoring — Refactoring
Started splitting monolithic `main.py` into a modular structure:

- `config.py` — centralized configuration via environment variables
- `utils/telegram.py` — auth filter and long message helper
- `services/wireguard.py` — all AWG logic (parse, add/remove peer, key generation)
- `services/gemini.py` — Gemini API wrapper with prompt templates

Goal: make the bot easier to extend and maintain
as the infrastructure scales from 1 to 30 nodes.

### 📋 Plans for Tomorrow (2026-04-22)

- Create `handlers/` (status, clients, ai, system)
- Refactor `main.py` — registration only
- Test the refactored bot end-to-end

---

## 2026-04-22

### 🛠 Done Today

#### AI Bot Monitoring — Refactoring complete

Finished splitting monolithic `main.py` into a modular structure:

- `handlers/system.py` — start, menu, restart + inline callbacks
- `handlers/status.py` — status, logs (switched dmesg → journalctl)
- `handlers/clients.py` — clients, addclient (parallel gather), delclient
- `handlers/ai.py` — analyze, free-form chat
- `main.py` — entry point only: validate → init → register → run

### 📋 Plans for Tomorrow (2026-04-23)

- Create `__init__.py` for all packages
- Verify imports end-to-end
- Run bot and test all commands live

---

## 2026-04-23

### 🛠 Done Today

#### AI Bot Monitoring - Manual import verification

- Created `__init.py__` for `services/`, `handlers/`, `utils/`
- Installed dependencies in venv: 
  `python-telegram-bot`, `google-genai`, `python-dotenv`, `aiohttp`
- Ran import checks module by module, fixed two issues found:
  -`get_awg_params()` was missing from `services/wireguard.py`
  - Migrated Gemini SDK: `google-generativeai`—> `google-genai`
    (new Client-based API, model name without 'models/' prefix)
- Started writting CI/CD lint workflow for bot (`bot-lint.yml`)

#### Result
All modules import successfully:
`config`, `utils`, `wireguard`, `gemini`, `handlers.*`, `main`

### 📋 Plans for Tomorrow (2026-04-24)
- Finish and push `bot-lint.yml` GitHub Actions workflow
- Run bot live on server, test all commands end-to-end
- Fix any runtime errors found during live test

---

## 2026-04-24

### 🛠 Done Today

#### VPN Infrastructure: Upgrade Attempt & "Dirty IP" Discovery

- **Server Provisioning (Upgrade Attempt):** - Accessed and verified the new high-performance VPS in Moldova (**2 Core, 2 GB RAM**). This was intended to replace the aging Moldova (1/1) node which is currently operating at peak capacity.
- **Ansible Automation & Deployment:**
  - Fully automated the deployment of `common` and `amneziawg` roles on the new 2/2 node.
  - Successfully resolved environment-specific issues (UFW port syntax, PPA integration, and configuration paths).
- **Network Diagnostics (DPI Interference):**
  - **Finding:** Connectivity tests confirmed that the new 2/2 server's IP address is flagged by **DPI (Deep Packet Inspection)** filters and resides in a "dirty" IP range.
  - **Observation:** Despite a perfect software configuration, the IP itself is blocked/throttled at the ISP level, making it unusable as a direct entry point for clients.
- **Current Status:**
  - The new 2/2 node is technically configured but network-restricted.
  - The "old" stable Moldova node (1/1) remains the sole operational gateway to ensure 16+ clients maintain internet access.

---

## 2026-04-25

### 🛠 Done Today

#### Infrastructure — Bulgaria Exit Node preparation

- Designed two-hop architecture:
  Clients → Moldova (AWG Entry) → Bulgaria (Xray Exit) → Internet
- Created Ansible role exit-node:
  - Xray VLESS/Reality inbound (accepts from Moldova)
  - Freedom outbound (direct to internet)
  - Saves Reality keys + UUID to /etc/xray-credentials.txt
- Created Ansible role monitoring:
  - Prometheus + Loki + Grafana + node-exporter via Docker Compose
  - Prometheus scrapes Bulgaria and Moldova nodes
  - Loki receives logs from all nodes via Promtail
- Created playbooks/deploy-bulgaria.yml
- Created group_vars/bulgaria.yml.example

**Security**
- Caught hosts.ini and entry.yml before push — added to .gitignore
- Removed both files from git tracking via git rm --cached

### 📋 Plans for Tomorrow (2026-04-26)

- Write Promtail role

---

## 2026-04-26

### 🛠 Done Today

#### Infrastructure — Bulgaria Exit Node deployed

- Received Bulgaria server (2GB/2Core), deployed via Ansible in one command
- Fixed critical issue: group_vars not picked up by Ansible —
  moved to inventory/group_vars/ (Ansible looks relative to inventory)
- Fixed role common: added NOPASSWD sudo for new_user via sudoers.d
- Bulgaria stack running: Xray + Prometheus + Loki + Grafana + node-exporter

#### Moldova → Bulgaria tunnel

- Established WireGuard tunnel between Moldova and Bulgaria (wg1)
- Both servers see each other, packets confirmed via tcpdump
- Attempted policy routing for client subnet 10.66.66.0/24 → failed
  Clients lost internet — asymmetric routing issue on Bulgaria NAT
- Rolled back to stable state — old Moldova VPN working, 15 clients online
- Xray relay abandoned on Moldova — wrong tool, too complex for this use case

#### Key decisions
- WireGuard tunnel is the right approach for Moldova → Bulgaria
- Need to fix NAT on Bulgaria for 10.66.66.0/24 subnet before retry
- Will test on single client before touching production routing

### 📋 Plans for Tomorrow (2026-04-27)

- Debug NAT on Bulgaria for client subnet 10.66.66.0/24
- Test routing on single client first (workstation config)
- Fix ip rule / ip route configuration on Moldova
- Verify end-to-end: client → Moldova → Bulgaria → internet
- Push working wg1 configs to Ansible roles
- Update client configs if Bulgaria IP becomes exit point

---

## 2026-04-27

### 🛠 Done Today

#### Infrastructure — Exit Node Migration & Pivot to Proxy
- **Cleanup & Reset:** Completely purged legacy traces of the failed dual-WireGuard experiments. This included removing `wg0/wg1` interfaces, routing tables `100/200`, and cascading `ip rule` entries. Process fully automated via an Ansible cleanup playbook.
- **Bulgaria Exit Node:** Deployed `shadowsocks-rust` (server) as the new, high-performance egress point. Port opened for both TCP/UDP; functionality verified.
- **Moldova Entry Node:** Implemented a **Transparent Proxying** architecture. Installed `shadowsocks-libev` (client) and `tun2socks` to bridge the L3/L4 gap.
- **MTU/Fragmentation Fix:** Resolved the "ping works, browser fails" bottleneck by pivoting from an L3 tunnel (WireGuard) to an L4 stream (Shadowsocks). This eliminated the MTU overhead and encapsulation conflicts that were dropping large TCP packets.

#### Routing & Testing
- **Policy Based Routing (PBR):** Initialized a virtual `tun0` interface. Successfully routed specific traffic through this interface using a dedicated routing table.
- **Isolated Testing:** Enabled the Bulgarian route **for a single test client only** to prevent service disruption for the other 15 active users on the Moldova node.
- **Success Criteria:** Confirmed end-to-end connectivity from the workstation. The client now exits to the internet via the Bulgarian node with stable page loading and expected latency.

#### Key Decisions
- **L3 → L4 Pivot:** Adopted `tun2socks` as the primary transport mechanism between nodes. This sidesteps the "VPN-inside-VPN" MTU issues by re-streaming traffic rather than re-encapsulating raw packets.
- **Persistence:** Routing rules were temporarily committed to `rc.local` on the Moldova node to ensure survival across reboots during the final testing phase before full Ansible role integration.

### 📋 Plans for Tomorrow (2026-04-28)

- **Stability Marathon:** 12-hour monitoring of the current connection to check for packet drops or memory leaks in the `tun2socks` user-space process.
- **Mobile Network Test:** Verify the tunnel's resilience over cellular networks, where carrier-grade DPI and varying MTU values often cause instability.
- **Global Rollout:** Upon successful testing, expand the `ip rule` mask via Ansible to transition all clients to the Bulgarian exit point.
- **Observability:** Integrate `shadowsocks` and `tun2socks` metrics into the existing Grafana dashboard on the Exit Node.
- **Documentation:** Finalize traffic flow diagrams in the PROJECT-JOURNAL to reflect the new hybrid L3/L4 architecture.

---

## 2026-04-28

### 🛠 Done Today

#### Infrastructure — IPIP Tunnel Moldova → Bulgaria (Production)

**Architecture Pivot**
* **Abandoned WireGuard Site-to-Site**: Double UDP encapsulation caused MTU fragmentation, leading to instability on mobile devices (iOS/Android).
* **Abandoned tun2socks + Shadowsocks**: Eliminated excessive encapsulation and user-space overhead that hampered mobile performance.
* **Final Solution**: IPIP tunnel (kernel-space, 20-byte overhead).
  Moldova (10.0.0.1) ↔ Bulgaria (10.0.0.2).

**Debugging & Fixes**
* **Resolved Routing Conflict**: Identified that the client subnet `10.66.66.0/24` on the Bulgaria node was incorrectly bound to the `wg0` interface.
* **Fixed Return Route**: Configured the correct route: `10.66.66.0/24 via 10.0.0.1 dev ipip0` to ensure traffic returns to Moldova.
* **Firewall Configuration**: Added explicit `FORWARD` rules for the `ipip0` interface on the Bulgaria node.
* **TCP Optimization**: Applied `TCPMSS --clamp-mss-to-pmtu` to automatically adjust segment sizes for the tunnel capacity.

**Verification**
* **Android Client**: Full internet connectivity confirmed.
* **Speed Test**: ~33 Mbit/s — stable performance for the current setup.
* **Security Audit**: Confirmed `UFW DEFAULT_FORWARD_POLICY=ACCEPT` is active and stable.

**Moldova Node Cleanup**
* **Service Optimization**: Stopped and disabled `tun2socks`, `ss-local`, and `shadowsocks-libev`.
* **AWG Status**: Remains operational as the entry point; achieved zero downtime for users during the migration.

### 📋 Plans for Tomorrow (2026-04-29)

* **iOS Integration**: Add one test iOS client to verify tunnel stability and MTU compatibility.
* **Stability Stress-Test**: Perform long-term connectivity checks (MTR/Latency) from mobile clients.
* **SRE Stack Deployment (v2.0)**: Deploy advanced monitoring (Prometheus/Grafana/VictoriaMetrics) on the Bulgaria Exit Node, integrated with the AI Monitoring bot.
* **Entry Node Optimization**: Decommission legacy monitoring services on the Moldova node to minimize CPU/RAM overhead, leaving only lightweight metric exporters.

---

## 2026-04-29

### Done Today

#### Infrastructure - AI Monitoring and SRE Stack (v2.0 Deployment)

**Architecture Pivot**
* Containerization (Docker): Successfully migrated the monitoring bot from a manual Python script to a Docker-based architecture. This ensures dependency isolation and environment consistency across different hosts.
* Artifact-Based Deployment: Adopted the SRE workflow of local builds and remote deployment (Build -> Save -> SCP -> Load). The bot is now a portable artifact, independent of the host system Python version.

**Debugging and Environment Stabilization**
* Resource Audit (Workstation): Used the bot to identify abnormal load on the local Pop OS environment (Load Average 1.9, Swap > 4GB). Closing background processes and browser tabs recovered 3GB of RAM.
* Bulgaria Exit Node Deployment: Successfully launched the bot container in Bulgaria. Observed near-perfect baseline metrics: Load Average 0.08 and RAM sage 300MB.
* Dependency Resolution: Identified a missing aiohttp module within the containerized environment. Mapped the fix for the next build cycle.

**Current Deployment State**
* Docker Networking: Container running with --network host to ensure visibility of the awg0 interface and the local network stack.
* Volume Mapping: Implemented volume passthrough for /var/log and /run/systemd/journal to allow the bot to access host logs (pending permission finalization).

### 📋 Plans for Tomorrow (2026-04-30)

* iOS Integration (Priority 1): Add and test the first iOS client. Verify IPIP tunnel stability and MTU compatibility for Apple mobile devices.
* Bot and Image Refinement: 
    - Update Dockerfile to include the systemd package to resolve the journalctl missing command issue.
    - Rebuild and redeploy the image with aiohttp and necessary system utilities.
* Permission Elevation: Configure sudoers on the Bulgaria node to allow the vpnadmin user (via the container) to execute awg and journalctl without a password.
* Interactive Fixes: Begin implementing the Human-in-the-loop feature—adding Telegram buttons for one-click VPN interface restarts.

---

## 2026-04-30

### Done Today

#### Infrastructure — AI Monitoring and SRE Stack (v3.0 Stability & Refactoring)

**Architecture Refactoring**
- Decoupling Logic: Fully separated data extraction (SSH/Parsing in `net_manager.py`) from presentation (UI/Formatting in `status.py`). Eliminated architectural confusion and simplified future scaling.
- Data Modeling: Introduced `PeerStatus` dataclass for typed AmneziaWG data, ensuring stable object passing between modules.
- Centralized SSH Logic: Unified all remote calls to the Moldova node. Added timeout protection and proper error handling to prevent bot freezes on network issues.

**Debugging and Environment Stabilization**
- Async Resolution: Fixed critical `TypeError` and `NameError` in async handlers. Heavy system calls now correctly run via `run_in_executor` without blocking the main thread.
- Syntax & Import Fixes: Resolved f-string syntax errors and circular imports. Bot successfully passes initialization and responds in Telegram.
- LLM Integration: Connected and tested Gemini-2.0-Flash engine via OpenRouter. Bot is ready for autonomous log and metric analysis.

**Current State**
- Local MVP: Bot is fully operational in local Pop!_OS environment.
  Basic monitoring of `awg0` interface and remote Moldova node polling are implemented.
- Security: All sensitive data (IPs, tokens, SSH keys) moved to environment variables (`.env`) with startup validation.

### 📋 Plans for Tomorrow (2026-05-01)

- System Health Module (Priority 1): Add CPU load, swap, and disk space monitoring for both nodes (Bulgaria & Moldova). Implement metric visualization in Telegram.
- IPIP Migration: Switch two clients to `ipip0` tunnel. Set up RX/TX packet monitoring to verify traffic flow.
- Dockerization & Deployment: Build final bot image and deploy it as a container on Bulgaria server for permanent operation.
- Operational Monitoring: Final stability testing of the link and AI-agent behavior under real load after client migration.

---
## 2026-05-01

### Done Today

#### Infrastructure — Dockerization and SRE Deployment (Production Readiness)

**Architecture & Container Stabilization**
- Docker Deployment: Successfully built and deployed the `vpn-bot:latest` container to the Bulgaria exit node for permanent operation.
- Base Image Optimization: Updated the `Dockerfile` to include essential system tools (`procps`, `systemd`, `iproute2`), resolving critical missing command errors (`uptime`, `journalctl`) within the `python:3.12-slim` environment.
- Log Passthrough: Configured volume mounts in `docker-compose.yml` (`/var/log/journal`) to expose host system logs directly to the AI analysis module.

**Debugging and Privilege Escalation Fixes**
- Sudo Dependency Elimination: Completely refactored `net_manager.py` and `ai.py` to remove `sudo` calls. Commands now execute natively under the container's root user, resolving `[Errno 2] No such file or directory: 'sudo'` crashes.
- Network Permissions: Added `privileged: true` and `network_mode: "host"` to the Docker Compose configuration. This resolved the `RTNETLINK answers: Operation not permitted` error, granting the bot full management rights over the `ipip0` and `awg0` interfaces.
- System Health Resolution: Fixed the "N/A" data parsing issue. The bot now successfully collects and visualizes CPU load, RAM, Swap, and Disk metrics for the local Bulgarian node.

**Current State**
- Production MVP: The monitoring bot is fully operational directly on the Bulgarian server.
- Link Stability: The IPIP tunnel between Bulgaria and Moldova is active, monitored, and currently reporting 0% packet loss.
- AI Diagnostics: Gemini-2.0 is now fully capable of reading both cross-node metrics and local system journals to autonomously identify hardware pressure or network anomalies.

### 📋 Plans for Tomorrow (2026-05-02)

- Canary Deployment (Priority 1): Pivot from mass client migration to a targeted "Canary" test. Route a test iPhone and the primary workstation (Pop!_OS) through the `ipip0` tunnel to isolate risks.
- Load & MTU Testing: Monitor RX/TX packet flow, connection stability, and potential fragmentation issues under real-world workloads via the newly deployed bot.
- Operational Observation: Establish a baseline for system resource consumption (CPU/RAM) on the Bulgaria node while the tunnel handles active traffic, utilizing the `/analyze` function to catch any early warnings.

---

## 2026-05-02

### 🛠 Done Today

#### Observability Stack — Full Setup

- Loki: fixed config (tsdb v13, delete_request_store, permissions)
- Promtail on Moldova: collecting awg, sshd, ipip, fail2ban → Loki
- fail2ban on Moldova: maxretry=3, bantime=24h — active, detecting attacks
- Grafana: Loki + Prometheus datasources connected
- Prometheus: scraping Moldova + Bulgaria node-exporters (all 4 targets up)

#### IPIP Migration — 3 clients on Bulgaria exit

- Fixed routing conflict on Bulgaria: removed stale wg0 route for 10.66.66.6
- Switched workstation (10.66.66.6) to IPIP → Bulgaria
- Switched iOS client Kristina (10.66.66.3) to IPIP → Bulgaria
- Android (10.66.66.12) already on IPIP for several days — stable

**Speed test results (workstation):**
- Moldova direct:  30.59 / 16.98 Mbps, ping 184ms
- Bulgaria (IPIP): 36.87 / 14.49 Mbps, ping 188ms
- Conclusion: +6 Mbps download, only +4ms latency overhead — acceptable

#### Priority Decision

- Bot code too raw for GitHub push
- Daily commits continue via PROJECT-JOURNAL.md
- Focus: stable infrastructure first, then bot v1.0, then showcase

### 📋 Plans for Tomorrow (2026-05-03)

- Monitor iOS client stability overnight — check Loki logs in the morning
- If iOS stable: migrate remaining clients to IPIP gradually
- Bot v1.0:
  - Fix System Health display for both nodes
  - Stable Analyze command with Loki integration
  - Fix operations: AWG restart, IPIP restart
- Make IPIP routing rules persistent across Moldova reboots (rc.local or systemd)
- Grafana: first dashboard (node metrics Bulgaria + Moldova)

---

## 2026-05-03
### 🛠 Done Today
#### Bot v1.0 — Deployed to Production
- Refactored net_[manager.py](http://manager.py): unified SSH helper, all remote calls via _ssh()
- Fixed fix_awg_interface(): now runs via SSH on Moldova instead of local call
- Fixed get_logs_text(): real logs from Moldova via SSH, --since '24 hours ago'
- Fixed clear_logs(): vacuum runs on Moldova via SSH
- Fixed AI prompt: added infrastructure context, removed false journalctl advice
- Removed systemd volumes from docker-compose — not needed, logs via SSH
- Built vpn-bot:v1.0, deployed to Bulgaria via SCP + docker load
- All menu buttons operational: Status, Health, Fix, Analyze
- Pending: Logs button returns no entries — debug tomorrow
#### PWA — Started
- Initial landing page built, running in container on Bulgaria
- RAM footprint: 15-20MB — acceptable
- Foundation for Web API layer above bot services
#### Architecture Decision — Russian Bridge Strategy
- Dual-track approach adopted:
- Normal mode:
    - Client → RU Bridge (VPS, major RU provider) → Moldova → Bulgaria → Internet
- Hard mode (Cheburanet scenario):
    - Client → RU Bridge (Raspberry Pi, residential IP) → Moldova → Bulgaria → Internet
- RU VPS: stable, handles DPI bypass for all clients by default
- Raspberry Pi: residential IP, allowlist bypass, deployed at 3 locations
  (home SPb, brother, Kristina Moscow) — activated when VPS gets blocked
- 2 EU nodes: Moldova (relay/entry) + Bulgaria (NAT/exit) — stays the same
- Architecture is adaptive, not locked into single solution

### 📋 Plans for Tomorrow (2026-05-04)

- Deploy and configure Russian Bridge (RU VPS)
- Fix Logs button (journalctl no entries via SSH)

---

## 2026-05-04

### 🛠 Done Today

#### Russian Bridge — First deployment attempt (Beget VPS)

**Server provisioned:**
- Provider: Beget (Saint Petersburg)
- Spec: 2 vCPU, 2GB RAM, 30GB NVMe, 1Gbit
- OS: Ubuntu 24.04
- Cost: ~980 RUB/month

**Ansible roles created:**
- `wireguard-bridge`: WireGuard server for clients (port 51820)
- `amneziawg-client`: AmneziaWG client for Moldova tunnel
- `playbooks/deploy-bridge.yml`

**Issues encountered:**
- Beget uses internal apt mirror — `noble-backports` not available
  Fixed: rewrote `ubuntu.sources` to use `public-mirrors.beget.ru/apt/ru.archive.ubuntu.com`
- AmneziaWG PPA (Launchpad) blocked on RU servers
  Fixed: copied binaries from Moldova, built kernel module via DKMS
- UFW blocked SSH after first successful deploy
  Root cause: `deny incoming` applied before SSH rule
  Fix: added explicit `Allow SSH before enabling UFW` task to common role
- System reinstalled twice due to locked SSH + no VNC access

**Result:** Ansible playbook completes successfully (56 tasks, 0 errors)

---

## 2026-05-05

### 🛠 Done Today

#### Russian Bridge — AWG tunnel to Moldova

**AWG kernel module:**
- Built amneziawg DKMS module (v1.0.20241112) on Bridge
- Source compiled against kernel 6.8.0-106-generic
- Module persistent across reboots via `/etc/modules-load.d/amneziawg.conf`

**Moldova awg1 interface:**
- Created second AWG interface `awg1` on Moldova (port 51820)
- Separate subnet: `10.77.77.0/30`
- Moldova: `10.77.77.1`, Bridge: `10.77.77.2`
- Separate obfuscation parameters from `awg0`

**Tunnel established:**
- Bridge → Moldova `awg1` handshake confirmed
- Ping `10.77.77.1` from Bridge: 65-67ms, stable
- Peer exchange completed manually (credentials saved to file)

**Issues:**
- System reinstalled 3 more times due to SSH lockouts
- `AllowedIPs = 0.0.0.0/0` in AWG client config caused SSH loss on startup
  Fix: changed to `AllowedIPs = 10.77.77.1/32` — only Moldova endpoint

---

## 2026-05-06

### 🛠 Done Today

#### Russian Bridge — Routing attempts (multiple iterations)

**Goal:** Forward client traffic: Android → wg0 → awg1 → Moldova → IPIP → Bulgaria

**Attempts:**
- Policy routing table 200: `ip rule add from 10.99.99.0/24 lookup 200`
  Result: route existed but `ICMP host unreachable` — Moldova not receiving packets
- Added MASQUERADE on `awg1`: traffic counters grew but no internet
- Added FORWARD rules `wg0 → awg1` and `awg1 → wg0`
- `ufw default allow routed` — fixed UFW forward policy
- Added `ip route add 0.0.0.0/1 dev awg1` — SSH lost immediately, system reinstalled again

**Root cause identified:**
- Two separate subnets (`10.99.99.0/24` for WireGuard, `10.77.77.0/30` for AWG)
  cause routing conflicts — default route via AWG kills SSH
- Bulgaria only knows `10.66.66.0/24` — doesn't route `10.99.99.x` or `10.77.77.x`
- Moldova `awg1` receives no packets from Bridge despite correct rules

**Total reinstalls to date: 6**

---

## 2026-05-07

### 🛠 Done Today

#### Russian Bridge — Routing architecture failures and pivot

**Routing attempts (all failed):**
- Policy routing table 200 with `ip rule from 10.99.99.0/24`
- MASQUERADE on awg1 — traffic counters grew but no internet
- `ufw default allow routed` — UFW forward policy fixed but no result
- `ip route add 0.0.0.0/1 dev awg1` — SSH lost immediately

**Root cause (final diagnosis):**
WireGuard (`wg0`) and AmneziaWG (`awg1`) on same server create
irresolvable routing conflicts. Any default route via AWG kills SSH.
Same pattern observed earlier with Moldova→Bulgaria WireGuard attempt.
This is a systemic issue, not a configuration error.

**Total system reinstalls: 7**

**Architecture decision — abandon WireGuard on Bridge:**
- WireGuard + AmneziaWG routing conflicts are not worth solving
- New approach: Outline (Shadowsocks) as client protocol on Bridge
- No kernel-level routing conflicts — works at application layer
- Available on iOS App Store, Google Play, Linux, Windows, Mac
- Single Docker container, minimal CPU overhead (chacha20-ietf-poly1305)
- DNAT forwarding Bridge → Moldova (no tunnel between them)

**New target architecture:**
- Client (Outline app) → Shadowsocks (Bridge:443/TCP)
- Bridge → iptables DNAT → Moldova:443
- Moldova → AWG → IPIP → Bulgaria → Internet

### 📋 Plans for Tomorrow (2026-05-08)

- Deploy Outline server on Bridge (Docker, single command)
- Configure DNAT: Bridge:443 → Moldova:443
- Test end-to-end: Android Outline client → Bridge → Moldova → Bulgaria
- If successful: generate Outline access keys for all clients
- Update Ansible role for Bridge (replace wireguard-bridge + amneziawg-client)
- Commit working configuration to git

---

## 2026-05-08

### 🛠 Done Today

#### Russian Bridge — VLESS/Reality experiment and pivot to dual AWG

**Outline (Shadowsocks) test — failed:**
- Deployed Outline in Docker on port 443
- Android client: connection unstable, only Google search worked
- DPI throttling detected — Shadowsocks signature on port 443 too obvious
- Switched to non-standard port 8388 — same result
- Conclusion: plain Shadowsocks insufficient for current DPI level

**VLESS + Reality preparation — abandoned:**
- Started writing xray-reality Ansible role
- User insight: client app compatibility issues (no AmneziaWG-equivalent on iOS App Store)
- Decision: stick with AmneziaWG protocol on all hops — proven to work reliably

**Final architecture (working):**

- Client (AWG app) → AWG awg0 (Bridge:8443/UDP, custom obfuscation)
- Bridge → AWG awg1 (Moldova:51820/UDP, original obfuscation)
- Moldova → IPIP → Bulgaria → Internet

**Bridge — dual AWG interfaces:**
- `awg0` — server for clients, port 8443, subnet 10.88.88.0/24
- `awg1` — client to Moldova, subnet 10.77.77.0/30
- Both use kernel module `amneziawg` — no protocol conflicts
- Different obfuscation parameters on each interface (DPI sees different patterns)

**Ansible role created: `amneziawg-bridge`**
- Single role for both AWG interfaces
- AWG kernel module via DKMS (built from GitHub source)
- Binaries copied from Moldova (PPA blocked on RU)
- Beget mirror for apt (foreign repos blocked)

**Client connection (Android):**
- Handshake works on first attempt (WiFi + LTE) ✅
- Tunnel Bridge → Moldova: 0% packet loss, 65-70ms latency
- Internet routing: not yet working (debug tomorrow)

**Total system reinstalls: 8** (Outline cleanup + final architecture)

### 📋 Plans for Tomorrow (2026-05-09)

- Debug routing: client traffic reaches Bridge but no internet
- Likely issue: NAT/MASQUERADE rules or table 200 routing
- Make Bridge routing persistent (ip rule + ip route survive reboot)
- Test all clients (Android, iOS, workstation)
- Update PROJECT-JOURNAL with final working architecture
- Commit Ansible roles to git

---

## 2026-05-09

### 🛠 Done Today

#### Russian Bridge — End-to-end tunnel WORKING

**Final architecture (verified):**

- Client (AmneziaWG app) → AWG awg0 (Bridge:8443/UDP, custom obfuscation)
- Bridge → AWG awg1 (Moldova:51820/UDP, original obfuscation)
- Moldova → IPIP → Bulgaria → Internet

**Routing breakthrough — `Table = off` in awg1 config:**
- Problem: `AllowedIPs = 0.0.0.0/0` killed SSH (default route hijack)
- Problem: `AllowedIPs = 10.0.0.0/8` only allowed private subnets — public traffic dropped
- Solution: `AllowedIPs = 0.0.0.0/0` + `Table = off` directive
- `Table = off` prevents wg-quick from auto-adding default route
- Custom routing only via table 200 for client subnet 10.88.88.0/24
- SSH stays on main routing table → no lockout
- Client traffic uses table 200 → goes via awg1

**Moldova-side change:**
- Extended `AllowedIPs` for Bridge peer: `10.77.77.2/32, 10.88.88.0/24`
- Required because client packets arrive with original source IP (no MASQUERADE on Bridge)

**Persistent routing:**
- Created `/etc/systemd/system/rc-local.service`
- Runs after `awg-quick@awg1.service` and `network-online.target`
- Restores `ip rule` and `ip route` for table 200 on every boot

**Test results (Android client):**
- WiFi: handshake on first attempt, internet works
- LTE: handshake on first attempt, internet works ✅
- Speed: 16.45 Mbps download, 205ms ping
- Exit IP confirmed: 185.237.223.94 (Bulgaria)

#### Strategic decisions

- Don't migrate other clients yet — observe Android stability first
- Bot fixes deferred to post-migration phase
- PWA development continues in parallel with bot work
- PWA SRE control panel — separate domain from user-facing PWA
  (security separation: admin tools isolated from client interface)

### 📋 Plans for Tomorrow (2026-05-10)

- Monitor Android client stability overnight
- If stable: implement split tunneling (RU services bypass via Bridge IP)
- ipset-based routing: RU domains → eth0, foreign → awg1
- Sources: antifilter.network IP lists, manual ASN entries for major RU services

---

## 2026-05-10

### 🛠 Done Today

#### Russian Bridge — Full validation across all platforms

**Tested clients:**
- Android (Honor, Chinese market): WiFi + LTE (MTS) ✅
- Workstation (Pop-OS): WiFi, 38.2 Mbps ✅
- iOS (iPhone): WiFi + LTE (Beeline) ✅

**Speed benchmarks:**
- Workstation WiFi: 38.2 Mbps / 6.87 Mbps, 216ms
- iOS WiFi: 35 Mbps
- iOS LTE (Beeline): 12 Mbps
- Android LTE: 16.45 Mbps

**Technical breakthrough:**
`Table = off` in awg1 config — prevents default route hijack,
allows custom policy routing via table 200 without killing SSH.
Client subnet 10.88.88.0/24 → table 200 → awg1 → Moldova.

### 📋 Plans for Tomorrow (2026-05-11)

- Migrate remaining clients to Bridge tunnel
- Implement split tunneling (RU domains via Bridge IP directly)
- Bot: debug Logs button, integrate Loki API
- PWA: SRE admin panel on separate domain

---

## 2026-05-11

### 🛠 Done Today

#### Russian Bridge — Client migration continues

#### PWA — Day 1: FastAPI skeleton

**Stack:** FastAPI + Uvicorn + python-dotenv

**Structure:**
pwa/
├── main.py          — FastAPI app, CORS, router
├── config.py        — env-based config
├── services/
│   └── net_manager.py  — reused from bot (SSH-based)
└── api/
└── status.py    — /api/status, /api/health

**Endpoints implemented:**
- `GET /` — root health check
- `GET /api/status` — AWG peers (19 total, 12 active), handshake times, transfer stats
- `GET /api/health` — Bulgaria + Moldova CPU/RAM/Disk, IPIP tunnel quality

**Data confirmed live:**
- Moldova: 19 peers, 12 active connections
- Bulgaria: 7GB RAM, 75GB disk free
- Moldova: 961MB RAM, 14GB disk free
- Bridge peer visible: vpZ1KPFsYd4p, 740MB RX / 14GB TX

**Committed to git:** feat(pwa): FastAPI skeleton

### 📋 Plans for Tomorrow (2026-05-12)

- PWA Day 2: `/api/clients` endpoint (peer list with names, not just keys)
- PWA Day 3: `/api/logs` endpoint (AWG + system logs via SSH from Moldova)
- Continue client migration to Bridge tunnel (1-2 per day)
- Monitor Bridge stability under growing load

---

## 2026-05-12

### 🛠 Done Today

#### Client migration — 11 new configs generated for Bridge tunnel

Generated and distributed AWG configs for 11 clients.

#### PWA Day 2 — /api/clients and /api/logs

**New endpoints:**
- `GET /api/clients` — peer list from Bridge awg0.conf, dynamic name resolution
- `GET /api/clients/{name}` — single client lookup
- `GET /api/logs` — AWG + sshd + fail2ban logs from Moldova as line arrays
- `GET /api/logs/{service}` — single service logs, up to 200 lines

**Architecture:**
- `_ssh_bridge()` helper added to net_manager — separate SSH connection to Bridge
- Client names parsed from `### Name` comments in awg0.conf
- Logs returned as `string[]` not raw string
- Removed `--since 24h` filter — AWG logs are sparse (service rarely restarts)

**Version:** 0.3.0

**Committed and pushed to GitHub.**

### 📋 Plans for Tomorrow (2026-05-13)

- PWA Day 3: JWT authentication — `/api/auth/token` endpoint
- No write operations until auth is in place
- Continue monitoring Bridge client connections

---

## 2026-05-13

### 🛠 Done Today

#### PWA Day 3 — JWT Authentication

**New endpoints:**
- `POST /api/auth/token` — login with username/password, returns Bearer token (24h TTL)
- `GET /api/auth/verify` — token validation

**All endpoints now protected:**
- `/api/status`, `/api/health`, `/api/clients`, `/api/logs` — require Bearer token
- Unauthenticated requests return `401 Unauthorized`

**Implementation:**
- `auth/jwt.py` — token creation, validation, `require_auth` dependency
- `api/auth.py` — login endpoint, single admin user from env
- Password hashing: argon2 (bcrypt 5.0 incompatible with passlib 1.7.4)
- JWT: python-jose, HS256, 24h expiry

**Version:** 0.4.0
**Committed and pushed.**

### 📋 Plans for Tomorrow (2026-05-14)

- PWA Day 4: `/api/analyze` — AI analysis endpoint (reuse from bot)
- PWA Day 5: minimal HTML frontend
- Deploy PWA to Bulgaria via Docker

---

## 2026-05-14

### 🛠 Done Today

#### PWA Day 4 — /api/analyze

- `POST /api/analyze` — collects metrics from Bulgaria + Moldova + IPIP tunnel quality, fetches AWG logs, sends to Gemini via OpenRouter
- Protected by JWT
- Reuses AsyncOpenAI pattern from bot
- Response: structured plain text (STATS / ISSUES / FIX)
- version 0.5.0, pushed to GitHub

#### Current PWA API state
✅ GET  /                    — health check
✅ POST /api/auth/token      — JWT login
✅ GET  /api/auth/verify     — token validation
✅ GET  /api/status          — AWG peers from Moldova
✅ GET  /api/health          — Bulgaria + Moldova metrics
✅ GET  /api/clients         — Bridge clients with names
✅ GET  /api/clients/{name}  — single client
✅ GET  /api/logs            — AWG + sshd + fail2ban logs
✅ GET  /api/logs/{service}  — single service logs
✅ POST /api/analyze         — AI analysis via Gemini

### 📋 Plans for Tomorrow (2026-05-15)

- HTML frontend — minimal SRE dashboard
- Docker deploy на Bulgaria
- Nginx + domain

---

## 2026-05-15

### 🛠 Done Today

#### PWA Day 5 — Minimal HTML Frontend

Single-page SRE dashboard — one HTML file, no frameworks.

**Features:**
- Login form → JWT token → localStorage
- Auto-logout on 401
- Auto-refresh every 30 seconds
- Infrastructure card: Bulgaria + Moldova CPU/RAM/Disk, IPIP loss
- AWG Status card: total/active/inactive peers
- Clients list: name + active/idle/inactive badge
- AI Analysis: button → Gemini response inline
- Dark terminal theme (#0d1117)

**Technical:**
- FastAPI serves static files via `StaticFiles`
- `GET /` returns `index.html`
- version 0.6.0, pushed to GitHub

#### PWA API — complete for MVP
✅ POST /api/auth/token
✅ GET  /api/auth/verify
✅ GET  /api/status
✅ GET  /api/health
✅ GET  /api/clients
✅ GET  /api/clients/{name}
✅ GET  /api/logs
✅ GET  /api/logs/{service}
✅ POST /api/analyze
✅ GET  /→ index.html

### 📋 Plans for Tomorrow (2026-05-16)

- Deploy PWA to Bulgaria via Docker
- Nginx reverse proxy + domain
- Bot: fix Logs button (journalctl returns no entries)

---

## 2026-05-16

### 🛠 Done Today

#### Bridge — routing persistence verified

- `rc-local.service` active since 2026-05-09, never failed
- `/etc/rc.local` contains correct `ip rule` and `ip route` commands
- Service starts after `awg-quick@awg1.service` — correct dependency order
- Live test skipped — 20 active clients, no downtime acceptable
- Real persistence test deferred to planned maintenance window

### 📋 📋 Plans for Tomorrow (2026-05-17)

- Deploy PWA to Bulgaria (Docker + Nginx)
- Bot: fix Logs button
- Bridge: test rc.local on reboot during low-traffic window

---

## 2026-05-17

### 🛠 Done Today

#### PostgreSQL — deployed on Bulgaria

- Docker container `pwa-postgres` running on Bulgaria
- Image: postgres:16-alpine
- Database: `vpn_sre`, user: `sre_user`
- Port: 127.0.0.1:5432 (not exposed externally)
- Healthcheck: pg_isready, status: healthy
- Separate docker-compose at `/opt/pwa/docker-compose.yml`
- Isolated network `pwa` — separate from monitoring stack

### 📋 Next Steps

- SQLAlchemy + Alembic setup in pwa/
- User model: id, username, email, password_hash, created_at
- First migration
- Registration endpoint: POST /api/client/register

---

## 2026-05-18

### 🛠 Done Today

#### PWA — PostgreSQL + SQLAlchemy + Alembic

**Setup:**
- SQLAlchemy 2.0 async + asyncpg driver
- Alembic migrations configured for async PostgreSQL
- SSH tunnel to Bulgaria for local migration runs

**Models:**
- `User`: id (UUID), username, email, password_hash, is_active, created_at

**Migration:**
- First migration: `create users table` applied to Bulgaria PostgreSQL
- Table verified: `users` + `alembic_version` in `vpn_sre` database

**Security fix:**
- Removed hardcoded credentials from `db/base.py` and `alembic.ini`
- DATABASE_URL moved to `.env` (gitignored)

### 📋 Plans for Tomorrow

- Registration endpoint: `POST /api/client/register`
- Login endpoint: `POST /api/client/token`
- Separate auth for clients vs SRE admin

---

## 2026-05-19

### 🛠 Done Today

#### Critical Incident — Bulgaria exit node broken

**Root cause:**
Provider blocking raw IPIP and GRE protocols on Bulgaria exit node.
FOU decapsulation stopped working, clean IPIP and GRE both blocked.

**Diagnostic chain:**
- Bridge awg0/awg1: handshake OK, client traffic arriving ✅
- Moldova awg1: receiving traffic from Bridge ✅
- Moldova → Bulgaria IPIP: traffic not forwarding ❌
- Bulgaria: IPIP decapsulation broken ❌
- All clients affected including Moldova-direct ones ❌

**Temporary fix — bypass Bulgaria:**
Client (AWG) → Bridge → Moldova → ens3 NAT → Internet

Changes on Moldova:
- Default route in table 100 changed to direct ISP gateway
- MASQUERADE on ens3 for client subnets
- Forward rules between VPN interfaces and ens3

**Result:** All clients working via Moldova direct exit ✅

#### Client configs — mass generation

- Generated keys for new clients
- Mass generation script: auto-creates .conf files with PSK
- Fixed `awg set` fopen error — added peers manually to awg0.conf + restart
- All client .conf files ready for distribution

**Current architecture:**
Client (AmneziaWG) → Bridge (AWG server)
Bridge → Moldova (AWG client)
Moldova → ISP (NAT) → Internet
Bulgaria: temporarily excluded

---

## 2026-05-20

### 🛠 Done Today

#### Critical incident — Bulgaria IPIP broken, full infrastructure recovery

**Root cause:** Cloud4Box Bulgaria blocks outgoing UDP — asymmetric filtering.
Moldova → Bulgaria UDP worked, Bulgaria → Moldova UDP blocked by provider.
Same issue confirmed with multiple ports (5555, 4789) and protocols (GRE, IPIP).

**Attempts that failed:**
- FOU+IPIP restoration — decapsulation worked but responses lost
- SSH reverse tunnel + socat UDP→TCP proxy
- AWG server on Bulgaria (handshake established, no data flow)
- AWG client Moldova → Bulgaria AWG (same asymmetric issue)

**Solution — new exit node:**
- Cancelled Cloud4Box Bulgaria (4-5 days remaining, not renewed)
- Provisioned AEZA Stockholm: 2C/4GB, 1Gbit, ~900 RUB/month
- Ping SPb → Stockholm: ~62ms

**Stockholm setup:**
- AmneziaWG installed (binaries + DKMS module from Moldova)
- AWG server on port 9999, subnet 10.100.0.0/30
- Moldova → Stockholm AWG tunnel: handshake instant, 0% packet loss
- Root cause of previous failure: AEZA uses 10.0.0.1 as ISP gateway —
  conflicted with our tunnel subnet 10.0.0.0/30
  Fixed by switching to 10.100.0.0/30

**Temporary architecture (end of day):**
Client (AWG) → Bridge:8443 → Moldova → ens3 NAT → Internet

Stockholm connected but not yet in routing chain.

**Client configs:**
- Mass generation for 14 clients on Bridge
- AWG conf lost after Bridge reboot — regenerated

---

## 2026-05-21

### 🛠 Done Today

#### IPIP FOU tunnel Moldova → Stockholm

**Setup:**
- FOU+IPIP tunnel between Moldova and Stockholm (port 5555)
- Key issue: AEZA gateway 10.0.0.1 conflicted with IPIP subnet
  Fixed: removed `10.0.0.1 dev enp0s3` static route on Stockholm
- rp_filter disabled on Stockholm (was dropping asymmetric traffic)
- NAT configured on Stockholm: MASQUERADE on enp0s3

**Routing on Moldova:**
- Table 101: `default dev ipip0`
- `ip rule from 10.77.77.2 lookup 101 priority 85`
- All Bridge clients exit via Stockholm

**Test results:**
- Ping Moldova → Stockholm: 63ms, 0% packet loss
- Speed: 15-20 Mbps (Moldova 1C/1GB bottleneck on double tunneling)

**Observation:**
When AWG Moldova→Stockholm was used instead of IPIP:
Moldova CPU saturated → speed dropped → mobile handshake failed.
IPIP is kernel-space — near-zero CPU overhead on Moldova.

**Current architecture:**
Client (AWG) → Bridge:8443/UDP
Bridge → Moldova awg1:51820/UDP
Moldova → IPIP/FOU → Stockholm → Internet

### 📋 Plans

- Investigate Bulgaria tunnel options: WireGuard site-to-site or SSH tunnel
- Restore Bulgaria as exit node when stable solution found
- Monitor Moldova load — now handling all exit traffic
- Continue PWA: registration endpoint

---

## 2026-05-22

### 🛠 Done Today

#### Client configs — 12 new configs generated

Generated and distributed AWG configs for:
Vika, Dasha, Danil, Danil-Mac, Kris-Vanya, Vanya-iPhone, Vanya-iPad,
My-Mac, Artem, Yana, Mama, Father — all on Bridge:8443, subnet 10.88.88.20-31

Total peers on Bridge: 16 (4 test + 12 clients)

### 📋 Plans

- Make IPIP persistent on Moldova and Stockholm (rc.local / systemd)
- Monitor client connections stability
- Ubuntu Server on old laptop — specs pending
- PWA: continue deployment to Bulgaria/Stockholm

---

## 2026-05-23

### 🛠 Done Today

#### Client configs — regenerated with correct obfuscation params

All 12 client configs regenerated with Bridge awg0 parameters:
Jc=3, Jmin=50, Jmax=1000, S1=72, S2=146, H1-H4 matching Bridge.
Previous script used wrong obfuscation values — fixed.

#### IPIP persistence — systemd services on both nodes

Moldova `/etc/systemd/system/ipip-tunnel.service`:
- Loads fou + ipip modules
- Creates FOU socket port 5555
- Brings up ipip0 tunnel to Stockholm
- Adds default route to table 101
- Adds ip rule from 10.77.77.2 lookup 101 priority 85
- Enabled, active

Stockholm `/etc/systemd/system/ipip-tunnel.service`:
- Mirror config, reverse direction
- NAT MASQUERADE on enp0s3
- Routes for client subnets via ipip0
- rp_filter disabled
- Enabled, active

Tunnel verified: ping Moldova → Stockholm 63ms, 0% packet loss.

#### PWA Day 6 — /api/client/register

- `POST /api/client/register` — creates client in PostgreSQL
- `GET /api/client/list` — lists all registered clients
- Fields: username, email, password (argon2), is_active, created_at
- Duplicate username/email returns 409
- JWT protected (admin only)
- Local PostgreSQL via Docker for development
- version 0.7.0, pushed to GitHub

#### Hardware — old laptop specs for first residential node

CPU: AMD E2-1800 APU, 1.70 GHz (2 cores)
RAM: 4 GB
Arch: x64
OS: Windows 10 Pro (to be replaced with Ubuntu Server 24.04)

### 📋 Plans for Tomorrow (2026-05-24)

- Install Ubuntu Server 24.04 on old laptop
- Basic hardening: SSH key, UFW, fail2ban
- AWG install (DKMS build)
- Connect as first residential node to Moldova

---

## 2026-05-24

### 🛠 Done Today

#### PWA — Full SPA Dashboard v2

Complete rewrite of `static/index.html`. Single-page app with hash routing, no framework.

**Views:**

Landing — grid background, animated badge, system status indicator, Sign In / Admin buttons.

Login — unified screen, routes to client portal or admin panel based on username.

Client Portal:
- Overview — connection status, active peers, infrastructure health card
- My Config — config block with copy button, QR placeholder, download button, setup instructions
- Payment — current plan info + "503 / in development" placeholder for crypto billing

Admin SRE Panel:
- Dashboard — active/total peers, exit node info, IPIP tunnel health, Bridge + Moldova metrics, active clients list. Auto-refresh every 30s.
- Clients — full AWG peers table with status badges
- Logs — AWG / SSH / fail2ban tabs, Moldova journalctl
- AI Analyze — Gemini analysis button + output block

**Design:**
- Brand: Sovereign
- Dark terminal aesthetic (#080c0f base)
- Fonts: JetBrains Mono + Unbounded
- Noise texture + scanline overlay
- CSS variables throughout
- Mobile responsive (sidebar hidden on small screens)

**Version:** 0.7.0 (index.html only, API unchanged)

### 📋 Plans

- Connect old laptop (Ubuntu Server) to router via ethernet — first residential node
- Deploy PWA to Bridge (Beget) — Russian IP, accessible without VPN
- Docker + Nginx setup on Bridge
- Sovereign domain purchase (Cloudflare Registrar)

---

## 2026-05-25

### 🛠 Done Today

#### PWA — Production Deploy on Bridge

**Docker setup:**
- Dockerfile: python:3.12-slim + openssh-client
- docker-compose: sovereign-pwa + sovereign-postgres
- SSH keys mounted read-only for Moldova/Stockholm access
- Secrets: JWT_SECRET and POSTGRES_PASSWORD generated via openssl

**Deploy:**
- Rsync code to Bridge /opt/pwa/
- docker compose build + up -d
- Alembic migration applied in container
- API verified: POST /api/auth/token returns JWT token

**Nginx:**
- Reverse proxy on port 80
- Proxies to uvicorn on 127.0.0.1:8000
- Default site disabled
- Site accessible via browser ✅

**Current stack on Bridge:**
Nginx :80 → uvicorn :8000 (sovereign-pwa)
↓
PostgreSQL :5432 (sovereign-postgres)

#### PWA — Sovereign SPA Dashboard v2

Complete frontend rewrite — full SPA with hash routing.
Landing, Login, Client Portal (Overview / Config / Payment), Admin SRE Panel.
Brand name: Sovereign. Dark terminal aesthetic.
Deployed to production as static/index.html.

### 📋 Plans for Tomorrow

- Buy domain on Cloudflare Registrar
- Configure DNS → Bridge IP
- SSL via Let's Encrypt (certbot + nginx)
- Residential node (old laptop): WiFi setup + basic hardening

---

## 2026-05-26

### 🛠 Done Today

#### PWA — Client Registration System

**New API endpoints:**
- `POST /api/client/register` — public, no auth required. Creates account in DB.
- `GET /api/client/me` — returns subscription status, peer_ip, subscribed_until
- `POST /api/admin/assign-peer` — admin manually assigns peer_ip to user, sets is_subscribed=true
- `POST /api/auth/token` — now works for both admin (env) and DB clients

**DB migration:**
- Added fields to `users` table: `is_subscribed`, `peer_ip`, `subscribed_until`

**Business logic:**
- Registration creates account only — no AWG peer generated
- AWG peer assigned manually by admin after payment (future: auto after billing)
- Existing clients added manually via assign-peer endpoint

#### PWA — Frontend Updates

**Landing:**
- Added "Create Account" button
- Tagline: "Path always exists." with hover → "Путь всегда существует."

**Register page:**
- Username, email, password, confirm password
- Validation: duplicate check, password match, min length
- Success → auto-redirect to login

**Mobile adaptation:**
- Hamburger menu (☰) for sidebar navigation on mobile
- Sidebar slides in from left with overlay
- Grid adapts to single column on small screens

#### Deploy — Production on Bridge

**Fixed persistent deploy workflow:**
- Never use `docker compose down -v` — loses DB volume
- Correct deploy: `docker compose build pwa && docker compose up -d --force-recreate pwa`
- Migrations run automatically via `entrypoint.sh` on container start
- `.env` on server managed separately, not overwritten by rsync

**Current stack:**
Nginx :80 → uvicorn :8000 (sovereign-pwa)
sovereign-pwa → sovereign-postgres (persistent volume)
Migrations: auto on startup via alembic upgrade head

### 📋 Plans

- Buy domain on Cloudflare
- SSL via Let's Encrypt
- Update client portal to show real config from DB
- Residential node (laptop): connect via ethernet, complete setup

---

## 2026-05-27

### 🚨 Critical Incident — ТСПУ update broke all clients

**Timeline:**
Telegram died first → YouTube → Google. All clients lost internet progressively.
AWG tunnel to Moldova (awg1) was active but traffic wasn't passing.

**Root cause chain:**

**1. MTU mismatch on Bridge awg0**
ICMP "frag needed" messages visible in tcpdump on awg0.
awg0 MTU was 1220 — too small, causing fragmentation and packet drops.

Fix:
- `sudo ip link set dev awg0 mtu 1300`
- `iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu`

**2. Client MTU mismatch**
Server awg0 MTU: 1300. Client awg0 MTU: 1420 (default).
Packets returned oversized.

Fix: client MTU forced to 1300. Added `MTU = 1300` recommendation for all client configs.

**3. YouTube + Telegram still broken (UDP issue)**
TCP sites worked. Video and messengers didn't.
YouTube uses QUIC (UDP/443), Telegram is UDP-heavy.
Large UDP packets dropped due to cumulative encapsulation overhead: AWG → AWG → IPIP/FOU.

**4. Root cause: IPIP tunnel Moldova → Stockholm**
Test: bypassed IPIP, used Moldova direct exit → YouTube and Telegram worked instantly.
IPIP+FOU adds extra headers (IPIP + UDP), inflating packet size.
Under DPI filtering, large UDP packets exceed MTU and get dropped.
This is the second time IPIP failed after provider DPI update.

---

### 🏗 Architectural Decision — Retire IPIP

**New architecture: split traffic at Bridge level**
Free clients  (10.88.88.0/24) → awg1 → Moldova → Internet
Paid clients  (10.99.99.0/24) → awg2 → Stockholm (direct AWG) → Internet

**Why AWG instead of IPIP:**
- AWG is obfuscated by design, more resilient to DPI than IPIP+FOU
- No extra encapsulation overhead
- Two independent paths, simpler to debug
- Policy routing on Bridge: table 200 (Moldova), table 201 (Stockholm)

**Current status:**
- All clients routing through Moldova direct ✅
- YouTube, Telegram, UDP services working ✅
- Stockholm exit node waiting for new AWG server role

### 📋 Next Steps

- Stockholm: configure AWG server for direct Bridge → Stockholm tunnel
- Bridge: create awg2 with `Table = off`, route table 201
- Policy routing: `from 10.99.99.0/24 lookup 201`
- Test on one paid client → migrate others
- Update client configs: add `MTU = 1300`

---

## 2026-05-28

### 🛠 Done Today

#### PWA — Plans Page

Pricing page added to client portal:

- Basic — 350 ₽/mo, first month 250 ₽, 1 device
- Extended — 750 ₽/mo, 2 devices + allowlist bypass (infrastructure in dev, button disabled)
- Family — 600 ₽/mo, 3 devices
- Footer banner "crypto billing coming soon"
- "Get Started" buttons — placeholder for Heleket API

#### PWA — UI Updates

- Light theme: warm background #f5f0eb, accent color terracotta #c45000 (opposite spectrum from blue)
- Theme toggle button ◐/◑ — fixed position, persists in localStorage
- Language toggle EN/RU — default RU, persists in localStorage
- Tagline "Path always exists." intentionally untranslated
- Admin button removed from landing — replaced with subtle hidden link in bottom-right corner

#### DB — configs and payments tables

- `configs`: user_id, name, peer_ip, private_key, public_key, preshared_key, is_active
- `payments`: user_id, plan, amount, currency, status, heleket_invoice_id, paid_at
- `users`: added plan field
- Migration applied on Bridge

#### Deploy — stable workflow

Created `deploy.sh` — excludes `.env` from rsync, recreates only pwa container without touching DB volume.

### 📋 Plans

- Bridge → Stockholm AWG tunnel (awg2, subnet 10.99.99.0/24)
- Heleket API integration
- Auto-provisioning configs after payment
- Residential node (laptop): connect via ethernet, complete setup

---

## 2026-05-29

### 🛠 Done Today

#### PWA — i18n across the whole portal

- Language (RU/EN) and theme toggles moved to top-level — now work on every screen (landing, client portal, admin), not just the landing page
- Default language: RU
- Entire client portal and admin interface now translatable (nav, pages, plans, features, statuses)
- Tagline "Path always exists." remains untranslated by design
- Font size increased +3px site-wide for readability

#### PWA — Overview redesign

- SVG route map embedded inline (self-contained, no external dependency — resilient under allowlist/blocking)
- Entry node St. Petersburg → two vectors: Stockholm (primary, solid line, animated packets, pulsing node) and Chisinau (fallback, dashed, slower packet)
- Cities placed by real relative geographic position
- Animation via SMIL — works without JS or internet
- Exit Node block: Primary Stockholm / Fallback Chisinau
- Status block: per-node status scaffold (Stockholm / Chisinau)
- Speed block: real latency measurement (median of 4 samples), throughput scaffolded
- Network block removed (not needed by clients)

#### PWA — Payment section rework

- "Plans" removed from sidebar — integrated into Payment
- Sub-tabs: Subscription / Order History / Support
- Subscription tab: Current Plan (real data from /api/client/me) + plan selection
- Order History and Support: "in development" placeholders
- Telegram removed entirely (unreachable in RF without VPN — all flows stay on-site)

#### Backend — Cryptobilling in development

- `services/heleket.py` — signature (md5(base64(body)+key)), invoice creation, webhook verification. Slash-escaping gotcha handled.
- `api/payment.py` — POST /api/payment/create (server-side price table, never trusts client amounts), POST /api/payment/webhook (signature verify, idempotent, activates subscription on paid)
- Auto-provisioning of AWG peer after payment marked as TODO (next step)
- Endpoints dormant until registered in main.py
- Frontend selectPlan() wired to create invoice and redirect

### 📋 Pending for billing launch

- Register payment router in main.py
- Domain + HTTPS for webhook url_callback
- Heleket credentials in .env
- Payment currency selection
- Auto-provisioning service (generate AWG peer on Bridge, save Config, expose in portal)

### 📋 Other Pending

- Bridge → Stockholm awg2 tunnel (subnet 10.99.99.0/24, table 201)
- Residential node: ethernet connect + hardening + AWG
- Multi-config support for clients with multiple devices

---

## 2026-05-30

### 🛠 Done Today

#### PWA — Overview map replaced with real region map

- Dropped the hand-drawn SVG blobs (rendered incorrectly — SVG text used CSS vars and dropped out)
- New map rendered from real Natural Earth border data: recognizable Baltic / Scandinavia region
- Cities at real relative positions: St. Petersburg (entry), Stockholm (primary), Chisinau (fallback)
- Two versions (dark / light) embedded as base64 — fully self-contained, no external load
- City labels overlaid in HTML — localizable RU/EN, theme-colored
- Primary node pulse + animated packet along the St. Petersburg → Stockholm route
- Page size grew to ~248 KB (cost of embedded maps — acceptable for offline resilience)

### 📋 Tomorrow

- Remove leftover static labels that don't change
- Check map rendering on mobile (most users are on phones)

---

## 2026-05-31

### 🛠 Done Today

#### PWA — Map labels fixed

- Found the duplicate-labels bug: the embedded map PNG still had baked-in Russian city names (from an earlier render), with HTML overlay labels stacked on top — hence duplicates in a different font that didn't translate
- Re-rendered both maps (dark + light) completely label-free — only nodes and routes baked in
- City labels are now HTML overlay only: localized RU/EN and theme-colored

#### PWA — Order History (real data)

- New endpoint `GET /api/client/payments` — returns the current user's payments (plan, amount, currency, status, dates), newest first
- Order History sub-tab no longer a placeholder: loads on open, renders a table (date / plan / amount / status)
- Statuses localized and color-coded: paid green, pending yellow, error red; empty state "No orders yet"

### 📋 Pending

- Domain (sovrn.nexus chosen) — deferred
- Register payment router in main.py + Heleket credentials (waiting on domain + currency decision)
- Auto-provisioning AWG peer after payment
- Multi-config support in "My Config" (clients with several devices)
- Bridge → Stockholm awg2 tunnel
- Residential node: ethernet + hardening + AWG

---

## 2026-06-01

### 🛠 Done Today

#### Residential Node — AWG tunnel to Stockholm

**Goal:** residential laptop (home RF IP) → AWG → Stockholm → Internet

**Steps completed:**

- SSH access to residential node established over WiFi
- amneziawg PPA added, DKMS module built and loaded (weak CPU, ~5 min compile time — expected)
- AWG keypair generated for residential node
- Peer added to Stockholm AWG server, dedicated subnet for residential nodes
- Client config created on residential node matching Stockholm obfuscation params
- Stockholm: ip_forward enabled, MASQUERADE configured, route to residential subnet added via PostUp in AWG config
- iptables rules saved persistently
- Autostart enabled on both nodes (awg-quick@awg0 systemd service)
- Verified after reboot: tunnel comes up automatically, exit IP confirmed as Stockholm ✅

**Current chain:**
Residential node (home RF IP) → AWG → Stockholm → Internet

### 📋 Tomorrow

- AWG server on residential node (phones connect to it as first hop)
- First test client config via residential → Stockholm chain
- Final target: Phone → Residential (RF IP) → Stockholm → Internet

---

## 2026-06-02

### 🛠 Done Today

#### Residential Node — AWG server setup (partial)

- AWG server (awg1) brought up on residential node, port 7443, custom obfuscation params
- Port forwarding configured on home router (UDP 7443 → residential node)
- Test client peer added, handshake established between phone and residential node
- Routing phone→residential→Stockholm not completed — requires clean approach
- ip_forward enabled and persisted on residential node

#### Moldova — Emergency maintenance

- Disk was at 100% — syslog/kern.log consumed 10+ GB
- Freed 16 GB via log truncation and journald vacuum
- Disk now at 37%, RAM usage normal
- Log rotation configured: journald max 200 MB / 7 days, logrotate max 100 MB / 3 rotations

#### Infrastructure — 5 new client configs

- Generated 5 new AWG keypairs (client7–client11)
- Peers added to Bridge awg0 (subnet .37–.41)
- Client configs created with correct obfuscation params and MTU 1300
- client7 and client8 distributed as promo configs

#### Auto-provisioning — Architecture designed + provisioner.py written

- Full billing→provisioning cycle designed for Basic plan
- `services/provisioner.py` written and syntax-verified:
  - Generates AWG keypair + PSK locally
  - Finds free IP from pool
  - Adds peer to Bridge via SSH (awg set + appends to config file)
  - Saves encrypted Config to DB (Fernet symmetric encryption)
  - Activates user subscription (30 days)
  - Returns decrypted .conf for client portal

### 📋 Plan — next 2 days (auto-provisioning completion)

1. Copy `provisioner.py` to `services/` in project
2. Generate `FERNET_KEY`, add to `.env` on server and locally
3. Add `cryptography` to `requirements.txt`
4. Wire `provision_basic()` into `api/payment.py` webhook (on `paid` status)
5. Create `api/config.py` — `GET /api/client/config` endpoint
6. Update `index.html` — "My Config" page shows real config data from DB
7. Register payment + config routers in `main.py`

---

## 2026-06-03

### 🛠 Done Today — Auto-provisioning deployed (v0.8.0)

#### Backend wiring
- `services/provisioner.py` deployed: generates AWG keys, finds free IP from pool, adds peer to Bridge via SSH, saves encrypted Config to DB, activates subscription
- `api/payment.py`: `provision_basic()` wired into webhook on paid status; Basic plan price set to 200 RUB/mo
- `api/config.py`: `GET /api/client/config` + `/raw` download endpoint
- `main.py`: payment + config routers registered, version bumped to 0.8.0
- `.env`: added FERNET_KEY, BRIDGE_PUBLIC_KEY, BRIDGE_ENDPOINT (local + server)
- Migrations applied on server

#### Manual config seeding (test data)
- 3 existing users granted Basic plan manually (simulating paid subscription)
- Inserted Config rows with real AWG keys (private key + PSK Fernet-encrypted)
- Verified: config displays in portal, downloads correctly as .conf

#### Frontend — major portal cleanup
- Removed Overview page (deferred for later, more detailed rework)
- "My Config" is now the default landing page after login
- Setup instructions rebuilt as tabbed (iOS / Android / Windows), iOS default
- Contrast improved in both light and dark themes
- Landing tagline font reduced (was competing with site name on mobile)
- Config page now shows real config from API, or "no subscription" / "config being prepared" states

#### Payment section rework
- Fixed critical bug: payment page rendered empty — root cause was an unbalanced `</div>` causing the payment page to nest inside the config page
- `showPayTab` rewritten to use direct style.display manipulation instead of CSS class toggling
- Support moved out of payment sub-tabs into its own sidebar section
- Plans reworked: Basic = "Popular" at 200 RUB/mo; Extended = "in development" only (details removed); Family removed entirely

### 📋 Plan — next session

1. **Moldova — disk + reboot prep**
   - Investigate disk consumption (verify log rotation took effect)
   - Audit auto-start after reboot: IPIP tunnel, AWG (awg0 + awg1), routing tables, PostUp persistence
   - Confirm everything survives reboot before rebooting; schedule reboot at night

2. **"Forgot password" on login**
   - Design reset flow — depends on email availability (linked to #4)
   - Options: email-based reset (needs SMTP) or manual admin reset initially

3. **Order History tab — not switching**
   - Likely same class of bug as payment page after support subtab removal — check showPayTab logic

4. **Support localization**
   - Telegram rejected (users can't reach it during config/infra problems)
   - Phase 1: feedback form → tickets to support email
   - Phase 2: on-site AI consultant for setup/support, with escalation to human operator
   - Start with form + email first

---

## 2026-06-04

### 🛠 Done — Moldova disk growth diagnosed and fixed

- Disk was filling ~3 GB per 16 hours despite log rotation being configured
- Root cause: two leftover debug iptables LOG rules logging every packet from a tunnel source IP
  - one in `mangle PREROUTING`, one in `nat PREROUTING`
  - they flooded kern.log/syslog faster than rotation could trim
- Removed both rules, truncated the bloated logs
- Disk back to 37%, growth stopped
- Confirmed no LOG rules remain in any table

## 2026-06-05

### 🔍 Analysis — Moldova reboot-readiness audit

Goal: confirm what survives a reboot before scheduling one (uptime was 69 days).

Findings:
- AWG autostart: `awg-quick@awg0` and `awg-quick@awg1` both enabled ✓
- `ip_forward` persistent via sysctl.d ✓
- **NAT/forwarding restored via AWG PostUp hooks** (MASQUERADE out main iface + FORWARD rules live in awg0/awg1 configs) — this is why the box survives reboots without netfilter-persistent
- Debug LOG rules (the disk-fillers) are not in any PostUp → won't return after reboot ✓
- IPIP tunnel confirmed dead (0 bytes over 5s sample; 109 GB counter was historical)
- Policy routing via custom table was redundant — it pointed to the same gateway as the main table since IPIP was retired

Actions:
- Disabled and stopped `ipip-tunnel.service` so it no longer recreates the dead tunnel or hijacks the custom routing table on boot
- Verified after changes: free clients still exit via Moldova, AWG peers intact (18 on awg0)

Conclusion: **Moldova is reboot-safe.** Everything critical auto-restores. Reboot can be done at night.

### 📋 Tomorrow evening

- Clear zombie processes on Moldova (reboot will handle them, or kill parent)
- Run the same reboot-readiness + disk/process analysis on Bridge (production entry node)

---

## 2026-06-06

### 🔍 Bridge — new clients 37/38 not working

- Symptom: the two newest peers had an endpoint and tiny transfer but NO completed handshake (no "latest handshake" line)
- Root cause: when peers 7–11 were added in an earlier session, the preshared-key step failed silently (process substitution doesn't work over SSH), so the peers were registered WITHOUT a PSK while the client configs HAD one → PSK mismatch → handshake never completes
- Fix: set preshared-key for all five peers (37–41) via temp-file method
- Pending: verify handshake after client reconnect
- TODO: persist PSKs to awg0.conf so they survive reboot

### 📋 Tomorrow

- Verify client 37 handshake after reconnect
- Persist PSKs into awg0.conf
- Clear zombie processes on Moldova
- Run reboot-readiness + disk/process analysis on Bridge

---

## 2026-06-08

### 🛠 Done Today

#### Documentation — README fully rewritten

- README updated to reflect current state (was dated April 2026 with wrong architecture)
- Removed: France exit node, Xray, IPIP tunnel, Yandex Cloud, Prometheus/Grafana/Alertmanager
- Added: actual 4-node topology, PWA section, auto-provisioning section
- Badges trimmed from 13 to 6 (only what's actually in use)
- Troubleshooting section rewritten with real production lessons
- Tech stack table reflects actual deployed components

#### Repository audit

- Full tree audit: identified outdated components, security concerns, and noise
- Proposed clean structure for employer-facing portfolio
- Key finding: venv dirs committed (thousands of files), retired stacks still present (Xray, IPIP, Yandex)

---

## 2026-06-09

### 🛠 Done Today

#### 🛠 Repository cleanup and restructuring

Restructuring repo to reflect current project state and clean up for portfolio use:

**Remove:**
- `configs/3x-ui/`, `configs/xray/`, `configs/monitoring/` — retired stacks
- `infrastructure/ansible/roles/xray-relay/`, `fou-backbone/`, `outline/` — retired
- `infrastructure/terraform/yandex/`, `yc-backend-setup/` — Yandex Cloud not used
- `scripts/providers/fourvps/` — retired provider
- `monitoring/ai-bot-monitoring/*.tar.gz` — binary artifacts
- `monitoring/dashboards/` — empty directory

**Add:**
- `docs/runbook.md` — incident response procedures (what to do when X)
- `tests/test_api.py` — basic pytest for /api/health

**Update:**
- `docs/architecture.md` — current 4-node topology
- `docs/troubleshooting.md` — updated with production lessons
- `scripts/README.md` — mark which scripts are production-active

---

## 2026-06-21

### 🛠 Done Today

#### Infrastructure
- Full health check after 2-week pause: all nodes operational
- Bridge: 31 peers, disk 17%, portal v0.8.0 responding
- Moldova: disk stable at 37% (no growth since June 5 — LOG rule fix held)
- Moldova reboot deferred to next session

#### Repository
- Committed `docs/runbook.md` — full incident response procedures
- Added `docs/architecture.md` — current 4-node topology, IP addressing, provisioning flow
- Added `tests/test_api.py` — basic pytest coverage for auth, config, payment endpoints
- Updated `scripts/README.md` — production-active vs reference status for all scripts

#### Portal — typography overhaul
- Added `--font-body: system-ui` variable to CSS root
- Body text switched from JetBrains Mono → system-ui across the entire portal
- JetBrains Mono retained only for technical elements: config blocks, labels, status codes
- Slogan font switched to system-ui with letter-spacing 4px, weight 500
- Deployed to production

### 📋 Tomorrow

- Fix payment tab switching: "Subscription" / "Order History" tabs not toggling
- Mobile layout improvements: vertical spacing, instruction blocks
- Navigation: review icon + label clarity
- Moldova reboot (audit was completed on 2026-06-05, confirmed safe)

---

## 2026-06-22

### 🛠 Done Today

#### Portal — typography (carried over, deployed)
- Body text switched from JetBrains Mono to system-ui across the portal
- Monospace retained only for technical elements (config blocks, labels, status codes)
- Slogan restyled with system-ui, increased letter-spacing

#### Portal — payment tab fix
- "Order History" tab returned 500 — root cause: `Payment` not imported in `api/register.py`
- Fixed import, rebuilt PWA container (image-baked code, not bind-mounted)
- `showPayTab` rewritten to use direct `style.display` instead of CSS class toggling — tab switching now reliable

#### Portal — support section rebuilt
- Replaced static contact info with a structured feedback form
- Issue categories with conditional sub-fields:
  - VPN won't connect → OS selector (iOS/Android/Windows/macOS)
  - App/resource slow → service selector (YouTube/Telegram/WhatsApp/TikTok/Instagram/custom)
  - Can't import .conf → OS selector
  - Other → free-text field
- Email field + submit, success confirmation screen with boutique-style copy
- Direct contact line (sovrn.support@gmail.com) below the form

#### Portal — layout bug (extended debugging)
- Support page content was rendering at the bottom of the page, outside the app shell
- Root cause: a single missing `</div>` in the support page — HTML parsers silently auto-corrected it, but the browser rendered the broken structure, pushing the page out of `<main>`
- Pulled the live server file as source of truth, validated full div balance with a parser, fixed the one missing tag
- Verified: body div depth balanced (0), all three client pages are correct siblings inside dashboard main
- Deployed, confirmed working

### 📋 Next session — email functionality (SMTP)

Build three features on a shared SMTP layer (`services/mailer.py`, Gmail SMTP):

1. **Support form → email** — `POST /api/support/ticket` sends formatted ticket to support inbox; wire real fetch into existing form
2. **Forgot password** — `POST /api/auth/forgot` (token + reset link) and `POST /api/auth/reset` (token + new password); Alembic migration for `reset_token` + `reset_expires`; login-page button + reset page on frontend
3. **Registration email** — welcome email on signup (later: subscription confirmation emails to same address)

Email language follows user's interface language (RU/EN).

**Prep needed:**
- `sovrn.support@gmail.com` registered (personal account, no domain/Workspace needed)
- App-password generated (requires 2FA enabled)
- `.env`: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

**Note:** password-reset links will point to bare IP until domain is purchased — Gmail may flag; acceptable for testing.

---

## 2026-06-25

### 🛠 Bridge — recovery after payment block and reboot

**Incident:**
- Service payment was late; Bridge was blocked at 10:00 MSK, paid at 11:00
- After restoration there was no SSH access — awg1 was intercepting part of the traffic, including inbound SSH
- Recovered access via VNC, added `Table = off` to awg1.conf so it no longer hijacks the routing table or inbound SSH

**Peers 12-16 lost after reboot:**
- Clients 12-16 (10.88.88.42-46) had been added at runtime only (`awg set`), never written to awg0.conf
- Their configs worked until the reboot, then the runtime state was lost — peers gone from the server, clients still holding valid configs
- Recovery: derived public keys from the client private keys (`wg pubkey`), re-added all five peers both to runtime (`awg set`, temp-file PSK method) AND to awg0.conf
- Verified: 31 peers in both runtime and file — now reboot-safe

**Lesson reinforced:** always write peers into awg0.conf immediately after `awg set` — runtime-only peers silently vanish on reboot.

---

## 2026-06-26

### 🛠 awg1 relay migration — Moldova → Germany (full cutover)

**Cause:** the Moldova relay went down. Needed to restore client internet access urgently, without changing any client configs.

**New relay (Germany, Ubuntu 26.04):**
- AmneziaWG built from source (PPA doesn't support 26.04 yet)
- awg0 configured as the tunnel server side:
  - subnet 10.77.77.0/30, address 10.77.77.1/30, port 51820, MTU 1300
  - obfuscation params copied from Bridge
  - PSK + AllowedIPs 10.77.77.2/32 for the Bridge peer
- ip_forward enabled and persistent

**Bridge changes (awg1):**
- Peer PublicKey swapped to the German server's key, Endpoint updated to the German node
- awg1 already carried `Table = off` + a route into table 200 (policy routing for client traffic)

**Finalization:**
- Set up SSH key auth from workstation to the German server (was password-only)
- Germany awg0.conf: replaced the narrow PostUp (only covered 10.88.88.0/24) with the full working rule set —
  - MASQUERADE out the main interface
  - FORWARD awg0 ↔ main interface (both directions)
  - matching PostDown for all three
- Bridge awg1.conf: added the missing `MASQUERADE -o awg1` to PostUp/PostDown (it had been added by hand at runtime and would not have survived a reboot)
- Verified both nodes reboot-safe: AWG autostart enabled, configs parse clean, ip_forward persistent

**Status:**
- Clients exit through Germany. Bridge ↔ Germany handshake healthy, traffic flowing.
- All previously-manual iptables rules now persisted in the configs — survives reboot.

### 🗺 Infrastructure change — Moldova decommissioned

- **Moldova is now fully removed from the infrastructure.**
- The standard-tier relay/exit role has moved to the German node.
- Architecture going forward:
  - Client device → Bridge (RF entry, awg0) → awg1 → Germany → Internet
  - Residential tier unchanged: Residential node → Stockholm → Internet
- TODO: update README and docs/architecture.md to drop Moldova and reflect the German relay.

**Lesson reinforced (third time):** runtime-only state — iptables rules and AWG peers alike — must be written into configs immediately. All three recent incidents (missing PSKs, lost peers 12-16, hand-added MASQUERADE) trace to the same root cause. Persisting on creation is now a hard rule.

---

## 2026-06-29

### 🛠 Germany node — security hardening (part 1)

Began hardening the German relay (was running as root with password auth).

**Done:**
- Created `sovadmin` user with sudo + passwordless sudo (avoids the SSH-password trap previously hit on Moldova)
- Copied SSH key from root to sovadmin, verified key login + sudo both work
- SSH hardening via drop-in `/etc/ssh/sshd_config.d/99-hardening.conf`:
  - PermitRootLogin no
  - PasswordAuthentication no
  - PubkeyAuthentication yes
- Validated with `sshd -t` before restart
- Verified after restart: sovadmin login works, root login refused (Permission denied)

**Deferred (needs full battery — UFW can cut access if done wrong):**
- UFW firewall — must set DEFAULT_FORWARD_POLICY=ACCEPT before enabling, or it breaks client tunnel traffic; allow 22/tcp + 51820/udp
- Fail2ban on SSH
- Basic monitoring: disk guard (the Moldova lesson), uptime check, AWG handshake watcher
- unattended-upgrades for security patches

---

## 2026-06-30

### 🛠 Germany node — kernel update broke the tunnel (root cause fixed)

**Incident:** German relay rebooted into a new kernel (7.0.0-27-generic). The AmneziaWG module wasn't built for it, so awg0 failed to come up and clients lost internet. iptables (NAT + FORWARD) also reset on reboot.

**Immediate recovery (done before this session):**
- /tmp module sources were gone (tmp is cleared on reboot), so re-cloned amneziawg-linux-kernel-module
- Installed current kernel headers, rebuilt + installed module, modprobe, brought awg0 up
- Manually restored iptables NAT/FORWARD rules
- Created /etc/modules-load.d/amneziawg.conf for module autoload
- Added PostUp/PostDown to awg0.conf; on Bridge restarted awg1 and added PostUp/PostDown to awg1.conf

**Root-cause fix (this session) — module moved to DKMS:**
- Diagnosed: module had been installed via plain `make install`, NOT registered in DKMS → every kernel update would break it again (this was the 4th reboot-related incident in a row)
- Moved sources from /tmp to /usr/src/amneziawg-1.0.0 (permanent — tmp is wiped on reboot, the reason re-cloning was needed today)
- Registered with DKMS: `dkms add` / `build` / `install` — module's own dkms.conf has AUTOINSTALL=yes
- Now: amneziawg/1.0.0 installed under DKMS → automatically rebuilds for any future kernel
- Cleaned up: removed duplicate MASQUERADE rule (manual rule stacked on top of PostUp), confirmed only the DKMS module remains

**Reboot-readiness checklist (all green):**
1. DKMS rebuilds module on new kernel ✓
2. Module autoloads (modules-load.d) ✓
3. awg0 autostart enabled ✓
4. ip_forward persistent ✓
5. iptables in PostUp (3 rules) ✓
6. Config parses clean ✓
7. Bridge↔Germany handshake alive ✓

**Status:** Clients exit via Germany. The kernel-update failure mode is now permanently closed — DKMS handles module rebuilds, all rules persist in configs.

**Root cause across 4 incidents:** runtime-only state that didn't survive reboot — missing PSKs, lost peers 12-16, hand-added MASQUERADE, and now a non-DKMS module. Each is now persisted at the source. The pattern is the lesson: nothing is "done" until it survives a reboot.

---

## 2026-07-01

### 🛠 Germany node — security hardening (completed)

Finished hardening the German relay (had been running as root with password auth until the user/SSH work began).

**Firewall (UFW):**
- Staged all rules before enabling to avoid lockout
- allow 22/tcp (SSH) + 51820/udp (AmneziaWG)
- default deny incoming / allow outgoing
- CRITICAL: set DEFAULT_FORWARD_POLICY="ACCEPT" before enabling — otherwise UFW breaks client tunnel forwarding
- Verified after enable: SSH intact, handshake alive, traffic flowing

**fail2ban:**
- jail.local on sshd (bantime 1h, maxretry 5, systemd backend)
- Immediately banned 4 brute-force IPs on startup — confirms the node was under active attack

**Monitoring (local, no Telegram yet):**
- /usr/local/bin/sov-healthcheck.sh, cron every 5 min: disk >80%, awg0 handshake staleness, module-loaded check
- logrotate on the health log (the Moldova disk lesson)
- Currently clean

**Auto-updates:**
- unattended-upgrades enabled for security patches
- Automatic-Reboot explicitly disabled — kernel transitions only on manual reboot, under supervision (DKMS guarantees the module is ready, so a controlled reboot is safe)
- Decision: "golden middle" — patches install automatically, reboot stays manual

### 🛠 Bridge (Russia) — security audit & hardening

Audited the production entry node for the first time since initial setup — hosts the PWA, holds all client peers, sits on a Russian public IP under constant scanning.

**Audit findings:**
- Good already: fail2ban active, unattended-upgrades enabled, PermitRootLogin no, 0 security updates pending, disk 19%
- **Critical hole found:** SSH password authentication was effectively ON. Cloud-init's `50-cloud-init.conf` set `PasswordAuthentication yes`; since the `Include` sits at line 12 and SSH honors the FIRST value seen, it silently overrode the `no` in the main config. A higher-numbered drop-in could not win. Brute-force had been possible since the image was provisioned.
- Public ports were actually fine: 8000/41225/53 only listen on localhost; only 22, 80 and AWG udp are truly exposed

**Fixes:**
- Disabled password auth at the source (edited 50-cloud-init.conf directly, removed the useless 99- drop-in). Verified effective `passwordauthentication no` via `sshd -T`, key access intact.
- UFW enabled: allow 22/tcp, 80/tcp (PWA nginx), 8443/udp (awg0 clients), 51821/udp (awg1→Germany); DEFAULT_FORWARD_POLICY=ACCEPT (all client traffic forwards through here)
- Post-enable verification (4 checks): SSH ok, PWA ok (v0.8.0), awg1→Germany handshake alive, 30 client peers intact
- Added the same healthcheck cron (disk / awg1 handshake / PWA liveness / awg0 peer count) + logrotate

**Lesson:** cloud images ship their own sshd drop-ins. Always check the EFFECTIVE config with `sshd -T` — the main config can say `no` while a cloud-init file quietly says `yes`. The audit habit found a hole that had been open for the life of the server.

**Status:** Germany and Bridge are now at parity — firewall + fail2ban + auto-patching + health monitoring on both.

### 🛠 SMTP email — foundation working

Began the email subsystem (Gmail SMTP, personal account, no domain needed).

**Done:**
- `services/mailer.py` — best-effort SMTP wrapper (never raises into the request path), reads SMTP_* from env; dark-themed RU/EN templates for welcome / password-reset / support-ticket
- `api/register.py` — welcome email wired into registration (best-effort try/except); added `lang` field to follow the user's interface language; preserved the `Payment` import fix
- `.env` on Bridge: SMTP_HOST/PORT/USER/PASS/FROM (Gmail app-password)
- Deployed (rebuilt PWA image — code is baked in)
- Verified end-to-end: test registration → SMTP full handshake (AUTH 235 Accepted → 250 OK) → welcome email delivered to inbox
- Cleaned up the test user from the DB

**Known minor issue:** mailer's `logger.info/error` aren't surfaced in container stdout (swallowed by uvicorn's log level) — diagnosis harder until fixed, one-line change later.

### 📋 Next session — remaining email features

1. **Support form → email** — `POST /api/support/ticket` + wire fetch into the existing form (template `support_ticket_email` already written)
2. **Forgot password** — `POST /api/auth/forgot` + `/api/auth/reset`; Alembic migration for reset_token + reset_expires; reset page on frontend; links point to bare IP until domain (Gmail may flag) — do this one fresh, not tired (touches the DB)
3. Healthcheck delivery — wire the cron scripts to email on CRIT once the channel is proven
4. UptimeRobot external monitoring (deferred by user)
5. Update README + docs/architecture.md: Moldova → Germany relay

---

## 2026-07-02

### 🛠 Password reset flow (complete)

Built the full forgot/reset chain on the SMTP foundation.

- Alembic migration `a1b2c3d4e5f6`: `reset_token` + `reset_expires` on users. Chained from the actual DB head `ebdcec96d747` — not the latest-by-date migration (the head had diverged from the newest file).
- `POST /api/auth/forgot`: `secrets.token_urlsafe` token, 1h expiry, emails the reset link. Enumeration-safe — identical response whether or not the email exists.
- `POST /api/auth/reset`: validates token + expiry, re-hashes with argon2, invalidates token (single-use).
- Frontend: "Forgot password?" link, dedicated reset view, `?token=` handling on the `/reset` route.
- Verified end-to-end: request → email → reset page → new password → login. Confirmed token is cleared after use (single-use works). Also surfaced a data issue — a user's email had a typo from registration; fixed directly in DB.

### 🛠 Support form → email (complete)

- `POST /api/support/ticket`: structured ticket (category, OS/service, details, email) → support inbox via the `support_ticket_email` template.
- Frontend: `submitSupportForm` wired to the backend (optimistic UI — success screen shows immediately, delivery is best-effort server-side).
- Verified: ticket arrived at the support inbox with all fields, dark-themed template.

This completes the email subsystem: welcome, password reset, support ticket.

### 🛠 PWA icons + manifest (home-screen install)

- Chose a node-graph icon (multi-hop metaphor) in brand cyan on dark.
- Full icon set generated: iOS (apple-touch, 120/152/167), Android (192/512 + maskable variants), favicons.
- `manifest.json`: standalone display, brand colors.
- PWA meta tags in `<head>`: apple-touch-icon, theme-color, manifest link.
- Verified: icons + manifest serve correctly (200 image/png); installed on iPhone home screen — shows the icon instead of the bare "S". Android full install pending SSL.

### 🛠 Split-tunnel — RU traffic exits locally (server-side, complete)

Goal: Russian services (banks, Ozon, Gosuslugi) reachable without turning the VPN off. Client configs unchanged — all logic on Bridge.

**Mechanism:**
- ipset `ru_nets` (hash:net) holds RU prefixes; mangle rule marks client traffic destined to those IPs; `ip rule` priority 99 (before rule 100 → Germany) routes marked traffic via the main table = local RF exit.
- Source: RIPE country-resource-list (~11.4k prefixes) + manual ranges for Yandex/VK/Gosuslugi (services sometimes hosted outside RU registration).

**Rollout (staged, safety-first):**
- Started scoped to one test client (`10.88.88.44/32`), verified: Ozon + Ozon Bank + Gosuslugi work with VPN on. (`2ip.ru` still showed Germany — correctly: it's hosted on Hetzner/DE, so it's not in the RU set. The mechanism routes by real IP location, not by domain name — working as intended.)
- Built persistence: `sov-split.service` (systemd oneshot) restores ipset + rules on boot from `/etc/sovereign/ru_nets.ipset`.
- **Reboot-simulation caught a silent bug:** the first restore script did manual `ipset create` + `flush` before `ipset restore`, which aborted on the pre-existing set — service reported `SUCCESS` but restored nothing. Fixed: `ipset destroy` then `ipset restore` (the dump carries its own `create`). Re-verified via `systemctl restart` (not manual run) — full restore confirmed.
- Expanded to all clients (`10.88.88.0/24`) once persistence was proven; re-verified restore path.

**Lesson reinforced:** "SUCCESS" exit status isn't proof — the restore ran, exited 0, and restored nothing. Only the reboot simulation exposed it. Test the real path, not the assumed one.

### 🛠 RIPE list auto-update (complete)

- `sov-update-ru-list.sh`, weekly cron (Sun 04:00): refreshes `ru_nets` from RIPE.
- Safe by design: builds a temp set, sanity floor (refuse if < 8000 prefixes — guards against RIPE outage / garbage), then **atomic `ipset swap`** so the tunnel is never without a list mid-update. Re-adds manual service ranges, re-saves the dump for reboot persistence.
- Tested: refreshed to 11393 entries, logged `[OK]`.

### 🛠 Email alerts from healthcheck (complete)

Closed the loop on monitoring — the health cron wrote to a log but never notified.

- `/etc/sovereign/smtp.env` (600, root) on both nodes with SMTP creds + `ALERT_TO`. On Bridge, copied from the PWA `.env`; on Germany, added fresh.
- `sov-alert.sh` (sender) + `sov-alert-check.sh` (reads health log, rate-limits to once per 6h per problem, sends a RECOVERED notice when clear). Hooked into the existing 5-min health cron on both nodes.
- Alerts go to the personal inbox.
- **Two parsing/behavior bugs found and fixed:**
  - `smtp.env` values needed quoting — the app-password has spaces and `SMTP_FROM` has `<>`, which broke `source` (bash tried to execute parts of them).
  - `sov-alert.sh` read the recipient from `ALERT_TO`, only set by the caller — a direct test run had `TO=` empty and silently `exit 0`. Fixed by putting `ALERT_TO` in `smtp.env` so the sender is self-sufficient.
- Verified the full chain on both nodes: injected a test `[CRIT]` → alert email arrived (correct node label, issue, rate-limit note) → cleared the log → RECOVERED email + state reset.

**Lesson:** a direct test of one component (the sender) was misleading — it only works when the caller sets a variable. The real failure mode only showed when tracing who calls what. Test the integrated path.

### 📋 Still open
- Domain + SSL (unblocks Heleket real payments, fixes bare-IP reset links, enables Android PWA install) — needs domain purchase
- UptimeRobot external monitoring (catches whole-node-down, which the local healthcheck can't)
- README + docs/architecture.md still reference Moldova — update to Germany relay
- mailer logs not surfaced in container stdout (one-line fix)

---

## 2026-07-04

### 🛠 Logging fix — surface app-module logs in container stdout

Closed the diagnostic gap noted on 2026-07-01: `mailer` (and other module) logs were being swallowed — only uvicorn's own logs appeared in `docker logs`, so debugging SMTP meant execing into the container and running Python by hand.

**Fix:**
- Added `logging.basicConfig` at the top of `main.py` (before router imports, so the root logger is configured before any module logs): level INFO, stream to stdout, format includes timestamp / level / module name.

**Verified:**
- Health check after the 2-day pause: all green — 30 peers, both tunnels fresh, PWA up, split-tunnel active (11393 entries, service active), UFW active on Germany.
- Test registration now shows the mailer line directly in `docker logs`:
  `INFO [services.mailer] Email sent to ... : Добро пожаловать в Sovereign`
- Confirmed the email-uniqueness constraint works as a side note — a duplicate email returns 409, no user created, no mail attempted.
- Cleaned up the test user.

**Status:** SMTP / registration / reset / support flows are now observable from `docker logs` without entering the container.

### 📋 Still open
- Domain + SSL (unblocks Heleket real payments, fixes bare-IP reset links, enables Android PWA install) — needs domain purchase
- UptimeRobot external monitoring (catches whole-node-down)
- README + docs/architecture.md still reference Moldova — update to Germany relay

---

## 2026-07-05

### 🛠 Major incident — inter-provider connectivity loss (Beget ↔ Cloud4Box)

**Symptom:** Clients lost internet. Bridge (Beget) awg1 and Germany (Cloud4Box) awg0 both showed live handshakes, but no traffic passed.

**Root cause (diagnosed by layer):** IP-level connectivity between Beget and Cloud4Box disappeared — the two servers stopped being able to reach each other, while both remained reachable from the home workstation. Confirmed it wasn't AWG config: tried port changes, key regen, udp2raw — none helped because packets physically weren't crossing between the networks. The problem was below the tunnel layer.

**Emergency fix (creative, under pressure):** the workstation was the only point with connectivity to both servers. Built a three-hop relay chain through the home laptop (Pop!_OS): Client → Bridge → laptop (awg-ru ↔ awg-de, NAT + forwarding + policy routing) → Germany → Internet. Service restored around 3am.

**Honest assessment of that state:** the home laptop became a critical part of production — fragile (sleep, IP change, reboot all break it), non-persistent, and exposes the home IP as a transit node. Correct as a "keep it alive now" patch, unacceptable as architecture. Recognized this myself and planned a proper relay VPS.

**Stopped at the right point** — as soon as it worked, not when it was "perfect." Masked suspend targets so the laptop wouldn't sleep with the lid closed, verified the chain was live, and slept a few hours instead of pushing to exhaustion.

### 🗺 Decision — move off Cloud4Box

Cloud4Box has now caused three incidents (disk-fill, kernel/DKMS, connectivity). Decided to drop it. Also noticed Gemini stopped working from Cloud4Box IPs (Moldova + Germany) — datacenter IP reputation likely flagged by Google.

### 🛠 New relay — Aeza Vienna (45.86.245.86)

- Chose Vienna over US (Charlotte) — better ping (99 vs 129ms), European connectivity to Beget likely more reliable, and for AI/YouTube/Telegram an Austrian IP is statistically no worse than US.
- Rented, provisioned Ubuntu 26.04.
- **Verified the important things before building:** server reaches the internet cleanly; Telegram (302), YouTube (200), Anthropic API (404 = reachable) all work from it — IP is clean, the Cloud4Box/Gemini problem is solved here.
- **But hit an SSH access problem:** can't SSH to Vienna directly from home — connects only via ProxyJump through Germany. TCP to the port succeeds, but the SSH session times out "during banner exchange."

## 2026-07-06

### 🔍 Diagnosing the Vienna SSH access problem (unresolved, narrowed)

Spent the session isolating why direct SSH home → Vienna fails while home → Germany works.

**Ruled out, systematically:**
- **Not IP blocking** — `nc` to ports 22 / 443 / 2222 all return `succeeded` (TCP handshake completes on every port).
- **Not port blocking** — same, all ports open at TCP level.
- **Not a total SSH/DPI filter at the home ISP (SkyNet)** — SSH to Germany (Cloud4Box) works fine directly. So the ISP isn't blocking "SSH" or "foreign datacenters" wholesale.
- **Not the home-side MTU** — lowering wlan0 MTU to 1400 didn't help; direct SSH still timed out.
- **Not the server** — healthy, sshd listening (disabled ssh.socket to get it listening on 22/443/2222; socket activation had been ignoring the `Port` directive in sshd_config, which explained the earlier "connection refused" on 2222/443).

**Found (partial):** a PMTU anomaly on the SkyNet → Aeza-Vienna path. `ping -M do -s 1472` (full 1500 MTU) → 100% loss to Vienna, but the same size passes to Germany. So the path to Vienna has an MTU below 1500 while the path to Germany doesn't. This fits the "TCP handshake works, data transfer stalls" signature — small packets (SYN, ping, nc) pass; large packets (SSH banner/keyexchange) get black-holed.

**But:** clamp-MSS on the server's OUTPUT (`--set-mss 1350`) did NOT fix it, and lowering the home MTU didn't either. So it's likely an asymmetric PMTU black hole (return path server→client) or something on the transit — needs a simultaneous tcpdump on both ends to pin down. Left for a rested session.

**Working state / what's not on fire:**
- Clients are online — service via Beget direct exit serves YouTube (200), Telegram (302), X (200).
- What Beget direct does NOT reach: Instagram (000), ChatGPT (403), Gemini (blocked) — so a working outbound tunnel is still needed, specifically for AI + Instagram, not for everything.
- Vienna server is healthy and manageable via ProxyJump: `ssh -J sovadmin@45.134.217.122 root@45.86.245.86`.
- Reconfirmed: with the client `awg0` tunnel up, SSH to infra servers breaks (`No route to host`) — the client config routes everything into the tunnel with no exclusions for infra IPs. For infra work, bring the client tunnel down.

### 💡 Strategic thread (to revisit rested)
- Idea: run BOTH the RU-entry and the foreign-exit on Aeza (one provider) to avoid the inter-provider connectivity failure that started this. Strong idea — connectivity within one provider's backbone is near-guaranteed. Caveats: cost of two Aeza servers, RU Aeza node still under RF jurisdiction, and need to verify Aeza-SPb ↔ Aeza-Vienna actually routes before committing.
- The same MTU/large-packet issue on the path to Vienna may also explain why the Bridge→Vienna tunnel handshake wouldn't establish — worth testing with a lowered tunnel MTU once the access path is sorted.

### 📋 Open (carried)
- Resolve Vienna direct-SSH (paired tcpdump both ends; test asymmetric PMTU; consider MSS clamp on INPUT/forward or lower tunnel MTU)
- Decide RU-entry provider (stay Beget vs move to Aeza) — after connectivity test
- Remove home laptop from any production path (still the emergency relay)
- Earlier backlog still open: domain + SSL, UptimeRobot, README/architecture Moldova→Germany→(Vienna?) update

---

## 2026-07-07

### 🔍 Vienna SSH problem — ROOT CAUSE FOUND (packet-level proof)

Finally pinned the three-day Vienna access problem with a paired tcpdump. The cause is **not** DPI, not IP/port blocking, not Aeza's fault, not the cross-border route as such — it's a **PMTU black hole on the path Vienna → RU networks**.

**Decisive test — bought a RU node on Aeza (45.151.101.104) to test connectivity WITHIN one provider**, removing the cross-border/inter-provider variable entirely:
- RU-Aeza → Vienna-Aeza: small packets fine (ping 0% loss), TCP handshake completes, `nc` to :22 succeeds.
- But SSH still failed with the same "timeout during banner exchange" — reproducing the problem *inside* Aeza. This proved the issue is specific to the path to the Vienna node, not the ISP (SkyNet/Tele2 both showed it too) and not cross-border transit generically.

**Paired tcpdump (RU node initiating, tcpdump on Vienna) — the smoking gun:**
- Vienna receives the client SYN, replies SYN-ACK, gets ACK — TCP established.
- Small packets (42 bytes, the SSH version banner) pass both ways and are ACKed.
- Vienna then sends its key-exchange packets at **length 1082** — and the RU node **never ACKs them**. Vienna retransmits the same 1082-byte packet repeatedly (growing backoff) until the RU node gives up and sends FIN.
- So: packets ≥ ~1000 bytes from Vienna → RU are silently dropped; small packets pass. Classic PMTU black hole, and the ICMP fragmentation-needed isn't getting back so PMTU discovery can't self-correct.

**MSS clamp does NOT fix it** — tried `TCPMSS --set-mss 1200` then `900` on Vienna's OUTPUT. tcpdump confirmed the SYN-ACK carried the reduced MSS, but the SSH key-exchange packets still went out at 1082 bytes (they bypass the MSS clamp) and still black-holed. This confirms the problem is at the link/route layer, not TCP config — it can't be papered over from the server side with MSS.

**Comparison that localizes it:** to Cloud4Box-Germany, full 1472-byte packets pass fine. To Aeza-Vienna, they don't. Same RU sources. So it's the specific Vienna path that's bad.

### 🗺 Decision — request server relocation instead of fighting MTU

Rather than force a low MTU on the interface (which would then have to be re-solved for the AWG tunnel, with its own encapsulation MTU, and would remain fragile) — decided to **ask Aeza support to move the server to a different location** where the path to RU is clean. Reasoning: building a tunnel on top of a link with a PMTU black hole is a house on a swamp — it'll resurface in AWG, in real client traffic, at the worst time. Fix the foundation first.

Wrote a support ticket with the full reproducible diagnosis (ping size thresholds, tcpdump showing 1082-byte retransmits unacked, MSS-clamp not helping) and a request to relocate to Frankfurt/Amsterdam/Helsinki or similar.

### 📊 Current state (nothing on fire)
- Clients online via Beget direct exit (YouTube/Telegram/X work; Instagram/ChatGPT/Gemini need the tunnel — still pending).
- RU-Aeza node (45.151.101.104) healthy and paid — half of the planned single-provider architecture is in place.
- Vienna node paid but awaiting relocation.
- Lease clock: **Beget 7 days** (holds prod — real deadline), Cloud4Box 3 weeks, Aeza-Vienna ~1 month.

### 📋 Next (rested)
- Send Aeza ticket, get Vienna relocated (or new location), re-test path RU→new-node with large packets BEFORE building anything.
- Once path is clean: build AWG tunnel RU-Aeza ↔ exit node, MTU sized for the real path, 5 test peers, 2–3 day soak.
- If stable: migrate clients + site + DB off Beget before its 7-day lease ends. Client configs point at Beget IP — all peers need reissue/endpoint change; plan delivery channel.
- Remove home laptop from any production path (still the emergency relay).

---

## 2026-07-08

### 🗺 Vienna resolved — refunded, replaced with Aeza Frankfurt

Support ticket to Aeza (packet-level PMTU black-hole diagnosis from 2026-07-07) succeeded — refunded the Vienna server, rented **Aeza Frankfurt (178.20.209.224)** instead, same price.

**Verified connectivity BEFORE building anything** (lesson from Vienna applied): ran the same large-packet test suite from both the home workstation and the RU-Aeza node (45.151.101.104) to Frankfurt — `ping -M do -s 1400` passes cleanly (0% loss) from both sources; only the 1500-MTU edge (`-s 1472`) fails, which is normal/expected, not a black hole. Confirmed real SSH connects (not just `nc`/ping) — the actual test that mattered with Vienna.

**Hit and fixed the same `ssh.socket` activation issue as Vienna** on the fresh Frankfurt image (sshd inactive, systemd holding port 22, real SSH timing out while `nc` "succeeded"). Fixed via VNC console: `systemctl disable --now ssh.socket && systemctl enable --now ssh`.

### 🛠 AmneziaWG installed on both Aeza nodes (RU + Frankfurt)

Ubuntu 26.04 ("resolute") has no Amnezia PPA build yet. Fixed by pinning the PPA to `noble` (24.04) instead — installs and DKMS-builds cleanly on the 26.04 kernel. Also had to drop `apt-key` (deprecated, breaks under `set -e` on 26.04) in favor of importing the key via `gpg --dearmor` into a keyring referenced by `Signed-By`.

Verified on both nodes: `awg`/`awg-quick` present, kernel module loads, and — importantly — **DKMS built the module for both the running kernel and the next one already staged** (`7.0.0-15` and `7.0.0-27`), which prevents the Cloud4Box-style "new kernel boots without the module" incident from recurring.

### 🗺 Decision — stop configuring by hand, actualize Ansible

After the third round of manual SSH/AWG setup in three days, decided (rightly) that repeated groundwork like this should be codified, not repeated. The project already had a mature-but-stale Ansible structure (roles: common, amneziawg, amneziawg-bridge, monitoring; playbooks for now-decommissioned Moldova/Bulgaria/shadowsocks topologies).

**Actualized for Ubuntu 26.04 + the new Aeza topology:**
- `roles/amneziawg/tasks/install.yml` — rewritten to pin the PPA to `noble`, import the key via gpg (no apt-key), and added a post-install check that DKMS actually built the module for the running kernel (`failed_when` instead of silent failure).
- `roles/common/tasks/main.yml` — added the `ssh.socket` → `ssh.service` fix. Made SSH hardening (disable root login / password auth) **opt-in** via `ssh_hardening: true` flag instead of unconditional — deferred until everything works and clients are migrated, so root access isn't lost mid-setup.
- `roles/amneziawg/templates/awg0.conf.j2` — made the obfuscation block (`Jc/Jmin/Jmax/S1/S2/H1-4`) conditional on `awg_obfuscation` (default false), added `MTU` (default 1300) and an optional `Endpoint` for peers. Reasoning: build the inter-node tunnel in layers — plain AmneziaWG first, obfuscation added afterward — to isolate failures instead of debugging everything at once.
- `inventory/hosts.ini` — replaced the dead Moldova/Bulgaria/Beget-bridge entries with the current topology: `ru-aeza` (45.151.101.104, entry) and `fra-aeza` (178.20.209.224, exit), both on Aeza's backbone.
- Decision: a separate `amneziawg-backbone` role for the inter-node tunnel (awg1), kept cleanly apart from the client-facing `awg0` role — avoids parameterizing one role for two different jobs.

### 🔁 Both Aeza nodes got reinstalled (clean state)

Both RU-Aeza and Frankfurt were reinstalled during the session (fresh OS, new host keys, no AWG). Re-added SSH keys to both after clearing stale `known_hosts` entries. Ended up being a good thing — a clean pair of nodes is the ideal starting point to test the actualized playbook end-to-end rather than layering automation on top of manually-patched state.

### 🐛 First playbook dry-run — found one real issue

Ran `ansible-playbook --check --diff` against `deploy-awg.yml` (entry group / RU-Aeza) as the first real test of the actualized roles.

**Result:** apt cache update succeeded; failed on `Install base packages` — **`net-tools` is not available on Ubuntu 26.04** (functionality folded into `iproute2`, which is present by default; the package was removed from the archive). Straightforward fix: drop `net-tools` from the package list.

**Stopped here** — ran out of usage limits mid-fix, right after identifying the `net-tools` issue and before applying the correction.

### 📋 Next (pick up here)
- Remove `net-tools` from `roles/common/tasks/main.yml` package list, re-run `--check --diff` on RU-Aeza.
- Continue dry-run iteration until `common` + `amneziawg` apply cleanly on RU-Aeza (entry group).
- Frankfurt (exit) needs its own path: `common` only at this layer (client-facing `awg0` role doesn't apply to it) — confirm/adjust playbook targeting.
- Write the `amneziawg-backbone` role (awg1, RU↔Frankfurt): Frankfurt listens (static endpoint), RU-Aeza initiates (Endpoint + PersistentKeepalive), MTU 1300, no obfuscation on this layer, subnet 10.99.99.0/30.
- Generate backbone keys/PSK (RU-Aeza has no `awg` binary right now post-reinstall — install via the playbook, not by hand, then generate).
- After backbone tunnel is up: verify handshake + large-packet test *through* the tunnel (repeat the MTU methodology from 07-07, this time end-to-end).
- Once stable: build 5 test client configs, soak 2–3 days, then migrate clients/site/DB off Beget before its lease ends.
- Secrets handling: currently plaintext in gitignored `entry.yml`/`exit.yml`; `ansible-vault` flagged as a later improvement, not blocking current work.
- Carried backlog: domain + SSL, UptimeRobot, README/architecture update (Moldova→Germany→Aeza).

---

## 2026-07-09 — Backbone role hardening: three routing bugs found and fixed

Built out the dedicated backbone interface (awg1) for the entry↔exit server-to-server
transport, kept fully separate from the client-facing interface (awg0). Three serious
bugs surfaced during a live bring-up and were fixed in the role:

1. **Self-lockout from a wide AllowedIPs on the initiator.** With `AllowedIPs = 0.0.0.0/0`
   on the initiator side, wg-quick's automatic policy routing captured *all* host traffic —
   including the SSH session — the instant the interface came up, before any handshake.
   Fix: `Table = off` on the initiator plus manual scoped routing via PostUp/PostDown
   (a dedicated routing table + an `ip rule` matching only the client subnet as source).
   The host's own traffic keeps its normal default route; only client-subnet-sourced
   traffic uses the tunnel.

2. **Fwmark collision.** The client interface and the backbone interface had been reusing
   the same fwmark, colliding in the policy-routing layer and black-holing host SSH. Fix:
   a unique, explicit fwmark per interface.

3. **Stale-config no-op on restart.** A `state: started` against an already-active oneshot
   unit is a no-op even when the config changed, so a stale tunnel could pass the safety
   check. Fix: register the template result and force `state: restarted` when the config
   actually changed, before the safety check runs.

The role now ends with explicit safety-net checks after any tunnel restart: verify the host
still reaches the internet, and (initiator only) verify the tunnel peer is reachable — both
fail loudly. Backbone verified end to end: handshake, ping through the tunnel, host survives,
re-runs idempotent.

**Rule reinforced:** unique fwmark per interface; never let a backbone initiator take the
default route without `Table = off` + manually scoped routing.

---

## 2026-07-10 — Client layer as code; the "generations of keys" trap

Codified the client-facing awg0 layer through the playbook: client subnet, gateway, port,
MTU, five test peers, and PostUp/PostDown that forward awg0↔awg1 (into the backbone) rather
than NAT'ing locally — egress/NAT belongs on the exit node, not the entry node. Fixed a
lingering wrong interface name in the forward rules (an old placeholder that never matched
the real NIC).

Lost a good chunk of the day to a self-inflicted problem: over several rounds of debugging,
client keypairs had been regenerated multiple times, and the private key that ended up in a
client config no longer matched the public key registered as that peer on the server. The
server silently drops a handshake it can't match to a known peer, so the symptom was pure
silence — packets arriving, nothing coming back. The lesson isn't subtle but it's easy to
violate under fatigue: **a client config and its server peer are one keypair; verify
priv→pub on the server (`awg pubkey`) rather than trusting which "generation" a key came
from.**

---

## 2026-07-11 — Full clean rebuild; the root cause of the intermittent behaviour


Days of accumulated manual patches on top of the playbook had made the servers' actual state
unreadable — every new hand-run command added a variable, and it stopped being diagnosis and
became guessing. Decided to stop patching and return to a reproducible state: reinstalled both
nodes and rebuilt everything through the playbook, touching the servers by hand as little as
possible.

Two root causes of the on-again/off-again behaviour across sessions were finally pinned down:

- **Non-persistent IP forwarding on the exit node.** `net.ipv4.ip_forward` was only ever set
  at runtime, so it reset to 0 on every reboot — and the nodes had rebooted repeatedly. That
  single fact explained the intermittency: it worked whenever forwarding happened to have been
  re-enabled after the last reboot, and failed otherwise. Fixed by writing it to a dedicated
  file under `/etc/sysctl.d/` from the `common` role so it survives reboot.

- **A leftover container runtime on the exit node** had set the kernel FORWARD policy to DROP
  and inserted its own chains, quietly cutting forwarded client traffic. It served nothing on
  this node; removing it (via the reinstall) returned FORWARD policy to ACCEPT.

The clean rebuild ran cleanly across all stages: entry (base + client interface), exit (base),
and backbone (both sides). End-to-end reachability from the client subnet out through the exit
node measured 0% loss.

**Rule reinforced (again, and this time it stuck):** nothing critical lives only at runtime —
kernel modules go to DKMS, iptables to PostUp/PostDown or a persistent store, peers to config
files immediately, and sysctl values to `/etc/sysctl.d/`. Forwarding on an exit node is exactly
that kind of critical, must-survive-reboot value.

---

## 2026-07-12 — The DPI wall, and the win

With a clean, code-defined stack, one symptom remained and it was stubborn: the test client
completed its handshake and resolved DNS perfectly, but no real traffic flowed — TCP handshakes
never completed, and pings from the server to the client dropped at every packet size, even the
smallest. That "even the smallest fails" ruled out a plain MTU problem.

Two things cracked it:

1. **Obfuscation.** The working production config for the older exit uses AmneziaWG obfuscation
   (the Jc/Jmin/Jmax/S/H parameters); the new chain had none. Under heavy DPI, plain
   WireGuard-shaped traffic gets fingerprinted and throttled — the handshake and single small
   UDP round-trips slip through, but a sustained stream toward the client gets cut. That matched
   every observation: handshake up, DNS working, TCP and steady flows dying. Generated a matching
   obfuscation set, wired it into the client interface through the playbook (the template already
   supported it behind a flag), and pushed identical parameters into the client configs. After
   this, server→client ping succeeded at full size in both directions — the DPI throttling was
   gone.

2. **A route/rule that lived only in PostUp.** The last blocker: the source-routing needed to
   push client-subnet traffic into the backbone had partially fallen out of sync — the routing
   table entry was present but the matching `ip rule` was missing, so client packets never entered
   the backbone. Restoring the rule made real, full-size, bidirectional traffic flow immediately.

Client traffic is live end to end through the exit node. This one belongs in the same family as
every other rule this project has taught the hard way: **a route and its rule are a pair, and a
policy-routing rule that only exists in PostUp is a runtime-only artifact — it has to be added
atomically and idempotently so it survives restarts.**

The real win here isn't "a ping succeeded." It's that any of these nodes can now be destroyed and
rebuilt from a single playbook run and come back correct, because every rake this project stepped
on — modules, iptables, peers, forwarding, fwmarks, wide-AllowedIPs lockouts, DPI obfuscation,
route/rule pairing — is now encoded, with the lesson written next to it. Next: roll the remaining
client configs and migrate real users over in stages.

---

## 2026-07-13
### 🔀 Port change 443 → 8443 (mobile DPI) + server key pinned
Test users on the new Aeza chain reported intermittent full drops — **mobile networks only, home Wi-Fi fine**, no pattern. Server-side diagnosis ruled out causes one at a time with data:
- Backbone stable (fresh handshakes, GiB flowing) → not a backbone flap.
- `ip rule from 10.66.66.0/24 lookup 200` present and in PostUp → source-routing not slipping.
- **Differentiator:** the proven-working Beget config listens on `8443`; the new chain used `443`. RU mobile carriers inspect/shape UDP on `443` (a web port) far harder than `8443`; wired/Wi-Fi tolerate `443`, mobile does not.

Changed the port through the playbook (`awg_listen_port`, firewall list, iptables INPUT `--dport`). Critically, **pinned `awg_private_key`/`awg_public_key` in `entry.yml`** so the role's `Generate a new private key` task (`when: awg_private_key is not defined`) can't fire and silently invalidate all 40 client configs. Server key now stable across redeploys — correct practice regardless.

### 🐛 Self-inflicted: 35 production peers wiped by a playbook run
After the port change, `deploy-awg.yml` rebuilt `awg0.conf` from the template — and the **35 production peers (client6–40) vanished**, because they'd been added earlier *with a script directly into the live file*, never into `awg_peers` in the inventory. Only the 5 inventory-defined test peers survived.
Nothing lost (client configs + keys saved in `~/vpn-configs-bridge/NEW/`). **Rebuilt all 40 peers into `entry.yml`**, deriving each peer's `public_key` from the `PrivateKey` in its `.conf` via `awg pubkey` — so server peer and client key **cannot drift** (the mismatch that burned us before, prevented by construction). Same rule, re-taught: *what isn't in code gets wiped on the next run.*

### 🧱 Mobile DPI wall — port alone didn't fix it
On `8443` the handshake succeeds on mobile, but real traffic still dies. `tcpdump` on `net0:8443` was decisive: **all packets `server → client`, none `client → server`** after the handshake. Not MTU — `ping -M do` failed at *every* size (1000 → 1400), including small. The server encrypts and sends to the live endpoint; the client's return path is cut by the carrier.
Confirmed against the working Beget config, same phone, same MTS SIM: Beget punches through, Aeza does not. Difference narrowed to the **obfuscation parameter set** (Beget `S1=72/S2=146/H1-4=…` vs ours `S1=86/S2=112/…`) and possibly Aeza's IP range being shaped harder. This is **carrier-level DPI, not an infra bug** — server, backbone, and Wi-Fi path all work.

### 📋 Next (pick up here)
- Test the Beget obfuscation set (`S1=72/S2=146/H1-4`) on the Aeza `awg0` + one client → isolates "params vs IP/ASN" as the cause.
- If params fix it → roll the Beget set across `awg0` via Ansible. If not → the RU-Aeza IP range is DPI-shaped; consider a different host/IP.

---

## 2026-07-14
### 🗺 Decision — pause Aeza migration, restore the proven exit chain
18 real users are live on the older **Beget → Cloud4Box(DE)** chain right now. It punches through mobile DPI *and* Wi-Fi, and ran 1.5 months / 2 weeks unattended. The new Aeza chain is architecturally cleaner but **does not pass mobile DPI yet**. Chasing the clean rebuild while live users depend on the working one = risk for aesthetics. **Restore the proven chain, finish Aeza later without live users hanging on it.** (No Aeza work discarded — roles, obfuscation, backbone, 40 configs all in code.)
Reframe worth keeping: the inter-provider connectivity loss that triggered days of emergency work looks, in hindsight, like a **transient network fault** — it healed on its own (clean pings, open ports, SSH to every node). A flare-up over-escalated into a fire. Wait-and-verify before the next "everything's broken" reaction.

### 🔧 Root cause — one-way backbone tunnel (peer pointed at a dead node)
Users were online via the RU node but on a **domestic exit only** (no foreign IP → no AI services / geo-blocked sites). Reading both ends found it without guessing:
- Cloud4Box `awg0` peer for Beget: **`0 B received, 271 MiB sent`** → one-way tunnel, no handshake.
- Beget's backbone iface (`awg1`) had the *correct* key (`vpZ1KP…`) and address (`10.77.77.2/30`) for Germany — but its single `[Peer]` `Endpoint` pointed at **the old Vienna node (`45.86.245.86`)**, a leftover from an abandoned relay attempt. PSKs had also drifted (`RkDHQU…` vs the `vCyQst…` Cloud4Box expected).

### 🔁 Bring-up — cleared a stale default that blocked the interface
`awg-quick up awg1` failed: `RTNETLINK answers: File exists` — PostUp's `ip route add default via 10.77.77.1 dev awg1 table 200` collided with a **stale `default via 100.100.1.1 dev eth0`** the emergency domestic-exit had left in table 200. Deleted the stale default → interface came up → **handshake with Cloud4Box immediately, transfer both ways**.
(Note: re-adding the eth0 default needs the `onlink` flag — `Nexthop has invalid gateway` without it, since the gateway isn't in an on-link subnet.)

### ✅ Cutover — tested on one client, then whole subnet with rollback in hand
Rather than flip all 18 blind: added a narrow `ip rule from 10.88.88.44/32 lookup 201 priority 40` → **test client only** egresses via Germany, other 17 untouched on domestic. After confirming the path, switched the whole subnet (`table 200 default → via 10.77.77.1 dev awg1`), cleaned a duplicate `10.88.88.0/24 lookup 200` rule, **rollback command prepared before the change**. Verified foreign exit IP from a client. All 18 back on foreign exit, **zero dropped during the operation**.

### 🔒 Persistence confirmed
`systemctl is-enabled awg-quick@awg0 awg-quick@awg1` → both `enabled`. `awg1.conf` PostUp restores `default via 10.77.77.1 dev awg1 table 200` on bring-up → **cold reboot comes back correct, no manual step**. Backup `awg1.conf.bak-venatocloud4box` kept on the node (records the working Cloud4Box key/PSK).

### 📋 Rules reinforced today
- What isn't in code gets wiped on the next run — server peers belong in the inventory, not hand-scripted into the live file.
- Pin the server key; never regenerate on redeploy.
- Before touching a shared resource 18 people depend on: test on one `/32`, hold a rollback ready.
- Not every lost-connectivity moment is a fire — sometimes the network self-heals; the calm move is wait-and-verify.

---

## 2026-07-16
### 🗺 Strategy — give the DPI-shaped node a job where its flaw doesn't apply
Two chains exist: the proven entry→foreign-exit chain carrying 18 live users, and the
Aeza pair that is architecturally clean but doesn't survive mobile DPI. Rather than spend
another week forcing obfuscation params through a carrier that shapes that IP range,
**repurposed the Aeza RU node as the PWA + database host.** The shaping targets obfuscated
UDP; HTTPS is a different protocol with a different signature and is unaffected. The node's
weakness is irrelevant in its new role.

Falls out for free: the PWA currently lives *on the live entry node*. Moving it to a
dedicated box is the isolation the roadmap wanted anyway — a public web app with SSH keys
should not share a host with 18 users' tunnels.

Constraint that forced the decision: **Docker cannot go on a VPN node.** So "spare VPN
entry" and "app host" are mutually exclusive. Fallback becomes entry→Aeza-GE instead — a
three-field re-point, already rehearsed on 07-14.

### 🔍 Pre-teardown check caught a live user
Before destroying anything, checked whether anyone was actually on the Aeza chain. Expected
nothing (mobile DPI never let it work). Found **one peer with a handshake 24 seconds old and
5.5 GiB served over three days.** A real person, mid-session. Confirmed who it was, waited
for them to move, then tore down. The check cost 30 seconds and was the difference between a
clean migration and cutting someone off without warning.

### 🗑 Teardown + Docker — two predictions, both wrong
Archived the configs (server key + 40 PSKs), pulled the archive off the box, disabled the
units, deleted the key material, cleaned FORWARD rules left orphaned by `systemctl disable`
(PostDown never ran). Moved the host from `[entry]` to `[app]` in the inventory so a stray
playbook run can't resurrect a VPN on top of Docker. Roles and vars stay in git — the work
is paused, not discarded.

Two things I predicted and got wrong, both caught by scripting the check instead of trusting
memory:
- **Docker's repo does have a build for this release.** Assumed it would lag like the
  Amnezia PPA did and need pinning to the previous LTS. It didn't.
- **Docker no longer sets FORWARD policy to DROP.** It installs its own chains instead. The
  rule "Docker breaks forwarding on a VPN node" still holds — its chains still decide the
  fate of forwarded traffic — but the mechanism I'd been repeating is out of date. Worth
  writing the real mechanism down rather than inheriting a legend.

### 🔒 PWA audit — four ways to fail open
Read the code before deploying it. The pattern across every finding: **the app was written
to live on a VPN node and silently inherited things from its host.** Move it, and the
inheritance vanishes without a word.

- **`FERNET_KEY` unset → `return plain`.** The comment said "dev only"; nothing enforced it.
  Client private keys and PSKs would be written to the database in **plaintext**, and the
  system would work *perfectly* — configs valid, users happy, no log line. Worse, adding the
  key later would make those rows undecryptable forever.
- **`JWT_SECRET` fell back to a default that is public in this repo.** Anyone who read the
  code could forge a token for any account, including admin. (The var I'd flagged as the
  risk — `API_SECRET` — turned out to be defined and used nowhere.)
- **`ADMIN_PASSWORD` fell back to admin/changeme**, and wasn't in `.env.example` at all.
- **`ping` isn't in the image**, so the network-quality check piped a missing binary through
  `grep | awk` and returned an empty string as a successful result. Silent garbage.

Every one of these **failed open**. The one variable that failed *closed* — `DATABASE_URL`
raises on absence — was the model: made the other three refuse to start. The bar is now
"the container doesn't come up and tells you why", not "it runs and quietly does the wrong
thing".

### 🐛 The billing could never have worked
`verify_webhook` called `hashlib.compare_digest` — **which does not exist**; it lives in
`hmac`. Every incoming payment webhook would raise `AttributeError` → 500 → the gateway
never gets its confirmation → the user pays and receives nothing. Confirmed against the
exact Python version the image uses rather than assuming.

Why it survived: the line only runs on an *incoming* webhook. Outgoing signing uses
`hashlib.md5`, which exists — so every test that creates an invoice passes. The trap sits at
the point you reach last.

Fixed, and added a byte-level mismatch log, because there's a second latent problem behind
it: the sender's `json_encode` and our re-serialization can still diverge on numeric types
(`10.00` → `10.0` breaks the signature). Verified strings and unicode round-trip correctly;
numbers don't. The first real webhook gets logged raw so that's diagnosed from evidence
rather than guesswork.

### 🔧 Key generation moved in-process
Provisioning shelled out to `awg genkey`/`pubkey`/`genpsk`. **The binary isn't in the
image** — it would have thrown `FileNotFoundError` on the first paying customer. Same root
cause as the missing `ping`.

Rejected installing the tools into the image (another external repo at build time) and
generating over SSH (client private keys crossing the wire). WireGuard keys are plain X25519
pairs and the PSK is 32 random bytes — `cryptography` was already a dependency. Rewrote all
three in-process and **verified byte-identical output against `awg pubkey`** before trusting
it. The image is now self-contained: no PPA, no host inheritance, no hidden coupling.

### 🔍 The foreign exit had been running on borrowed time since 30 June
Chased a side question and found the interface up but its **unit in `failed` since 30 June**
— running purely at runtime, surviving only because the box hadn't rebooted. Reconstructed
the cause from apt history: unattended-upgrades pulled a new kernel, the module wasn't
DKMS-registered, reboot → `Unknown device type` → unit died → fixed by hand, never restarted
through systemd. The old incident that produced the DKMS rule, still fossilised in the unit
state.

Talked myself into a panic (a reboot would drop all 18 users — the entry node routes them
through this interface) and then out of it, on evidence: the DKMS hook is present, the module
is registered for the running kernel, and the bootloader takes the newest. The next reboot
should be a non-event. But "should" is a prediction, not a fact — so a **controlled restart
is scheduled for tonight**, when most clients are offline, with a runbook and a rollback
prepared in daylight rather than improvised at 3am.

Also verified, and this is the part I'd skipped before: the persistence check on 07-14 was
run on **one side of the tunnel only**. Half the chain went unverified, and the gap was
exactly where the fossil was.

### 🔒 Real secrets in the public repo — the .gitignore never matched
Checked `.gitignore` before the first `git add`. It **wasn't ignoring anything it claimed to**:
one rule had its path glued onto a `# ====` divider line, making the whole thing a comment;
the rest pointed at paths missing a directory segment. `git check-ignore -v` said, plainly,
"not ignored by any rule".

Two backbone private keys were already pushed. Scoped the damage before reacting:
- **The live entry node's vars held no secrets.** The thing that mattered didn't leak.
- **Client PSKs never leaked** — and without them the key alone can't impersonate a node.
- Forward secrecy means the static key can't decrypt past traffic.
- One leaked key was for the node whose VPN I'd torn down **that morning** — obsolete by
  accident of timing.
- One was still live: the foreign fallback's backbone key. Rotated it. Its only peer was the
  node torn down hours earlier, so nobody was connected — the rotation window was free.

**Deliberately did not rewrite history.** A secret that has been public is compromised
permanently; a force-push is theatre that also destroys the commit narrative. Rotation is
the remedy. `git rm --cached` + a fixed `.gitignore` stops the *next* one, which is the part
that actually matters.

### 🐛 And I broke it further while fixing it
While "fixing" `.gitignore` I deleted two rules, reasoning they pointed at a directory that
didn't exist. **It exists** — there are two parallel `group_vars/` dirs, and I'd only looked
at one. The rules were correct; I removed protection from files that had it. Caught it
because `git status` showed them as `??` immediately after.

Restored wider: match on the **directory name** (`**/group_vars/*.yml`) rather than a full
path, so a third parallel copy would be covered by default too. The narrow-path rule is what
failed in the first place; replacing it with another narrow path would have been the same
bug with different coordinates.

Bonus find: the second `group_vars/` is an April duplicate that **Ansible doesn't read** —
it loads the one beside the inventory file. A trap: edit it, nothing happens, lose an hour.

### 📋 Next
- Tonight: controlled restart of the exit node's unit — runbook + rollback ready.
- Tomorrow: dedicated SSH keypair for the PWA (never the personal key on a public web host)
  + a narrow-sudoers user instead of the passwordless-sudo account it would otherwise use.
- Then: secrets → `.env` → deploy compose → new DB via `alembic upgrade head` → verify on
  localhost **before** nginx and a certificate. The app answers on loopback first; the
  internet comes after.
- Before real money moves: forced-command SSH dispatcher (the command list is short and
  finite). The right end state — invert the direction so an agent on the node polls a queue,
  and the web host holds no inbound SSH at all — goes on the roadmap, not today's plate.
- Cleanup, unhurried: the dead duplicate `group_vars/`, the monitoring bot's stale topology
  vars, today's `.bak` files.

### 📌 Rules reinforced
- **Check, don't predict.** Three times today the check disagreed with me: a live user on a
  "dead" chain, a repo build I assumed was missing, a directory I declared nonexistent.
- **Fail closed, not open.** A secret with a default is a hole that reports success.
- **Verify both ends.** A persistence check on one side of a tunnel is half a check.
- **A public secret is compromised forever** — rotate, don't rewrite.
- The trap sits where you reach last: outgoing signing worked, incoming never could.

---

## 2026-07-18
### 🗺 Frame
Domain (out of money) and the exit-node restart (deferred) both blocked
publication. Underneath them: a full day of work needing neither — harden the
PWA's access to the nodes before it ever faces the internet. Least access that
works: not the personal key, not passwordless root, not an arbitrary shell.

### 🔒 The code was still on dead paths
Three of four PWA routers still SSH'd into Moldova, decommissioned six weeks ago.
Retargeted `_ssh` to the live exit and renamed the vars honestly (`EXIT_*`, not
`MOLDOVA_*`). Repurposed a dead IPIP check to measure the backbone /30 — the
link whose failure cost a week.

### 🐛 Two "works until it doesn't" bugs
- `verify_webhook` called `hashlib.compare_digest`, which doesn't exist (it's in
  `hmac`). Every incoming payment webhook would 500 — user pays, gets nothing.
  Survived because only incoming webhooks hit that line; outgoing signing uses
  `md5`, which exists, so tests passed. The trap sits where you reach last.
- Key generation shelled out to `awg`, absent from the image — would fail on the
  first paying customer. Rewrote as in-process X25519, verified byte-identical
  against `awg pubkey`.

### 🔒 Second git leak, and a fix that opened a new hole
`git status` before pushing showed real group_vars tracked and pushed. Scoped
before reacting: the live node's vars were clean, PSKs never leaked, one leaked
key was already obsolete (that node's VPN torn down that morning). Rotated the
one still-live key in a free window; left history intact (a public secret is
compromised for good — rotation, not a force-push). Then while fixing
`.gitignore` I deleted two rules on the reasoning the dir didn't exist — it does.
`git status` caught it seconds later. Restored wider: match on directory name.

### 🔐 SSH layers 1+2 — the main build
One `pwa-provisioner` key (splitting keys buys nothing while both mount into one
container — that waits for layer 4). A restricted user on both nodes. Writes go
through `pwa-add-peer`, which re-validates server-side: key format, /32 in the
client subnet, octet range, duplicate key AND duplicate IP. Reads via
`pwa-awg-show`/`pwa-logs`. sudoers allows only the wrappers.

### 🧱 Newer sudo refused the wildcard — correctly
Exit node's newer sudo rejected `awg show*`: wildcards not allowed in args. Not
an obstacle — it blocks exactly the hole the entry node's older sudo waved
through (a wildcard matches spaces). Brought the entry node to the same standard
rather than keep the looser rule because it "worked".

### 🔧 Wiring, and the check that caught me
Rewired net_manager/clients/provisioner to the new user and wrappers; client
names now come from the DB, not `sudo cat`. `py_compile` passed twice on a call
to a function I'd deleted — it checks syntax, not names. The real import caught
both. For Python, "it compiles" ≠ "it runs"; the check is `import`.

### 📋 Next
- At deploy: key at `/opt/pwa/ssh_keys/pwa-provisioner` (600, root:root) before
  `compose up`. Watch `:ro` mount vs `accept-new` wanting to write known_hosts.
- Local compose bring-up (no domain needed): new DB, migrations, curl loopback.
- Waiting on money/quiet window: domain, night restart.
- Before payments: layer 3 dispatcher. Layer 4 (on-node agent polls a queue) —
  roadmap.

### 📌 Rules
- A public web app gets the least access that works.
- A constraint that blocks the loose path is often protecting you.
- "It compiles" ≠ "it runs" in Python — verify with a real import.
- The trap sits where you reach last.
- Scope a leak before reacting; a hurried fix can open the next hole.

---

## 2026-07-19
### 🗺 Frame
Domain still unpaid, so publication (nginx + TLS) stays blocked. The
unblocked piece: bring the PWA up for real. Local dry-run with stubs first —
verify it even starts — then the actual deploy on the app server.

### 🐳 Local bring-up with stubs — the whole start chain, live
Generated a stub `.env` (format-valid secrets, no production values, SSH not
exercised), then `docker compose up`. Confirmed on a real run what had only
been import-tested:
- postgres reports healthy *before* pwa starts — the race the healthcheck was
  added to close is closed
- entrypoint's `set -e` runs 4 migrations, then uvicorn — a broken migration
  couldn't start the server on a half-built schema
- no `FERNET_KEY is not set` / `JWT_SECRET is not set` — the fail-closed
  defaults from the 16th are satisfied, not tripped
- `/`, `/api`, `/docs` → 200, listening on 127.0.0.1 only
- auth end-to-end: `/api/auth/token` → JWT → `/api/auth/verify` returns the
  admin identity. That exercises ADMIN_PASSWORD → argon2 → JWT_SECRET signing
  in one shot.
- DB schema matches the models — `configs.name` / `public_key` present, the
  columns `_names_from_db` reads.

Two small self-corrections along the way: I guessed the login path twice
(`/api/auth/login`, then `/login`) before reading `/openapi.json` for the real
one (`/api/auth/token`). Read the route list, don't guess it — FastAPI hands it
over for free, and the list doubles as proof every router imported cleanly.

### 🚀 Deploy on the app server — and the SSH floor holds in production
Docker needed a group add first (`usermod -aG docker`; group applies in a new
session). Then, on ru-aeza:
- pwa-provisioner key → `/opt/pwa/ssh_keys/` (600, root:root); the compose mount
  and the code's default key path line up on an absolute path, so no env var
- code cloned from the public repo; `.env` generated *on the server* with real
  secrets and live node IPs (Heleket/SMTP/OpenRouter left as `stub` for now)
- stack came up identically to local: healthy → migrations → uvicorn, loopback
  only
- **the part local couldn't test:** a live SSH from inside the container to
  Beget, as pwa-provisioner, through the pwa-awg-show wrapper — returned awg0's
  real status. The whole least-access path works end to end in production:
  container → key from a read-only mount → restricted user → validating wrapper
  → live node. Not root, not the personal key.

Caught myself mid-deploy: pasted the *local* stub admin password when the
server generates its own. Different secret; the server's is the real one. Also
skipped the `.env`-generation step once and only noticed when compose warned
`POSTGRES_PASSWORD not set` and nothing came up — the missing file, not a bug.

### 🧱 Known nit, not a blocker
The SSH warned `Failed to add the host to known_hosts` and connected anyway:
`/root/.ssh` is mounted read-only, so `accept-new` can't persist the host key.
It works, but MITM protection is effectively off (it accepts any key each time
— the very thing accept-new was meant to prevent). Fix later, with the compose
change for nginx: mount a writable known_hosts pre-filled via ssh-keyscan.

### 📋 Next
Publication is now a short pass on top of a working stack, gated only on money
for the domain:
- buy sov3r3ign.com → A-record → propagate
- nginx :443 → TLS (Let's Encrypt) → proxy to 127.0.0.1:8000
- SITE_URL / PORTAL_BASE_URL → https://sov3r3ign.com (restart pwa so payment
  callbacks and reset emails get the right address)
- writable known_hosts in the same compose change
- swap Heleket/SMTP/OpenRouter stubs for real keys
- RF-reachability check without a VPN
Still waiting on a quiet window: the Cloud4Box awg0 restart.

### 📌 Rules
- Serve on loopback until there's TLS in front — a bare public :8000 leaks
  credentials and can't satisfy https-only callbacks.
- Read the route list, don't guess it.
- "It's up" is proven from the server (curl loopback), not from a browser —
  the two aren't the same until a reverse proxy exists.
- A missing file looks like a bug until you check for the file.

---

## 2026-07-23
### 🔎 Mobile one-directional-traffic incident — resolved
Handshake succeeded but "received" only ticked up every ~25s (keepalive-sized)
while "sent" climbed normally — independent of carrier and location. Cause:
a 07-18 test had assigned a live client's AllowedIPs to a
throwaway test peer, before pwa-add-peer had duplicate-IP checking. Removing
the test peer never restored the route, so the server had nowhere to route
return traffic to that client — handshake doesn't depend on AllowedIPs, data
does. Fixed by reassigning allowed-ips back to the real peer on Beget.

### 🗺 Decision — full Prometheus + Grafana stack on fra-aeza
fra-aeza is retiring from the backbone-fallback-exit role (a different server
is being rented for that in early August), so it becomes a dedicated
monitoring node — no conflict with the established Docker-vs-VPN-forwarding
rule. Installed natively (apt packages, no Docker): lighter on 1-core/2GB
hardware, standard practice for exporters regardless.

### 🛠 Built: node_exporter on all four nodes, firewalled to fra-aeza only
fra-aeza, Beget (entry), Cloud4Box (exit), Aeza-RU (app) all now run
node_exporter, each restricted so only fra-aeza's IP can scrape :9100.
Verified with both directions on every node — a scrape from fra-aeza
succeeds, a scrape from anywhere else times out. All five Prometheus targets
report "up". Added 1-2GB swap on all four nodes (none had any).

### 🐛 Found: netfilter-persistent "enabled" but rules.v4 was empty on Aeza-RU
Same class of bug as the Cloud4Box awg0 unit found in July — persistence
looked configured but wasn't. The existing udp/443 rule there is still not
saved (TODO); the new node_exporter rule was saved correctly this time.
Aeza-RU also has no default-deny firewall policy at all (unlike Beget/
Cloud4Box's UFW) — works today, but is a standard gap to close later.

### 🐛 Grafana dashboard silently broken after "successful" provisioning
File-provisioned dashboard (community id 1860) loaded with no errors in the
logs, but every panel showed No data / N/A. Cause: the dashboard's datasource
variable `${ds_prometheus}` is never auto-resolved by file provisioning (only
manual UI import does that) — and it wasn't just the one variable, it was
127 separate references throughout the JSON. Fixed by replacing all 127 with
the literal datasource UID. Lesson: "no errors in the log" and "finished to
provision dashboards" did not mean it worked — the dashboard had to be opened
and checked visually.

### 📋 Next (tomorrow)
- Alertmanager → Telegram
- Alert rule for config-vs-runtime AllowedIPs drift (directly targets today's
  root cause, would have caught it in seconds instead of days)
- Aeza-RU: default-deny firewall policy, persist the udp/443 rule
- Still waiting: Cloud4Box night restart, domain purchase

### 📌 Rules reinforced
- Handshake succeeding is not proof AllowedIPs is intact — check the actual
  route, not just connectivity.
- "No errors in the logs" is not "it works" — open the UI and look.
- A duplicate-IP check exists for a reason: the incident it would have
  prevented took days to surface and diagnose.

---

## 2026-07-24
### 🛠 Alertmanager → Telegram wired up
Installed Alertmanager on fra-aeza, bound to loopback, connected to Prometheus,
delivering to the existing ai-bot-monitoring Telegram bot. Reused the old
bot's token rather than creating a new one.

### 🐛 Two permission misses before it actually ran
`amtool check-config` passed clean, but the service still failed to start —
config syntax being valid said nothing about whether the process could read
the file. Root cause: alertmanager.yml was `600 root:root`, but the service
runs as user `prometheus`, not root. First fix attempt matched the *pattern*
of the already-working prometheus.yml (which is root:root, 644) instead of
checking who reads it — set `640 root:root`, still failed, because 640 only
grants group-read and `prometheus` isn't in the root group. Only checking
`id prometheus` (uid 105, gid 107, its own group) and setting the file's
group to match fixed it. Two guesses based on "the other file looks like
this" before actually looking at who reads the file — same shape of mistake
as checking assumptions against real output, just one layer removed (checking
against a *similar* configuration instead of the *actual* runtime user).

### ✅ End-to-end delivery confirmed
Sent a manual test alert through Alertmanager's API — it arrived in Telegram,
just later than expected. Not a bug: `group_wait: 30s` in the config means
Alertmanager deliberately holds new alert groups briefly before the first
send, to batch multiple simultaneous alerts into one message rather than
spamming one at a time.

### 🗺 Decision — no automated AllowedIPs drift detection, for now
Considered building a textfile-collector script + alert rule to catch
config-vs-runtime AllowedIPs drift automatically (the exact class of bug
behind the 07-20 incident). Decided against it: the vector that caused that
incident — a test peer silently taking over a live client's AllowedIPs — is
now closed by pwa-add-peer's duplicate-IP check. Building detection for a
now-mitigated one-off risk isn't worth the added monitoring surface today.
Caveat noted: the wrapper only protects writes that go through it: a future
direct `awg set` outside the wrapper could still hit the same bug, but that's
a rare path now, not the main one.

### 📋 Next
- Aeza-RU: bring firewall to default-deny (currently ACCEPT-by-default with
  point rules only — works, but inconsistent with Beget/Cloud4Box's UFW)
- Aeza-RU: persist the still-unsaved udp/443 rule (found 07-23 that
  netfilter-persistent reported enabled while rules.v4 was empty)
- Domain purchase and Cloud4Box night restart still waiting

### 📌 Rules reinforced
- A config passing its own syntax checker says nothing about whether the
  process can actually read the file — check the runtime user, not the tool.
- Matching an existing file's *permission pattern* isn't the same as checking
  who *actually* needs to read the new one — verify the specific user, don't
  extrapolate from a similar-looking case.
- A slow-arriving alert isn't necessarily broken — check the config
  (group_wait) before assuming failure.

---

## 2026-07-28
### 🛠 Aeza-RU brought to default-deny — the last inconsistent node
Beget and Cloud4Box have run UFW with default-deny for a while; Aeza-RU (the
app server) still had a bare ACCEPT policy with only point rules. Closed the
gap: built the full rule set first (loopback, established/related, SSH,
the existing 9100 rule) *before* touching the default policy, verified it,
then switched both iptables and ip6tables to DROP.

### 🐛 Found and removed a dead rule instead of persisting it
A standing `udp/443 ACCEPT` rule had nothing listening behind it — likely a
leftover from before this node was repurposed from a VPN role to a pure app
server. The 07-23 plan had this marked "TODO: persist it"; checked first
instead of carrying old TODOs forward blindly, found no listener, removed it
rather than preserving dead config.

### 🔎 A firewall command showed two different answers seconds apart — investigated before proceeding
`ip6tables -S INPUT` showed empty, then showed a full rule set moments later
in the same session, with no code change in between. Root cause: `ip6tables`
resolves to the nft backend on this host (`update-alternatives` confirmed:
best version is `-nft`), and `ip6tables-legacy` is empty and inert — so
there's no live second backend actually fighting for control. What produced
the one inconsistent read is unresolved (file mtime, Docker restart time, and
login history all ruled out as the cause) — didn't invent an explanation
for it. Confirmed no real risk (no active second backend) before continuing,
rather than either ignoring the anomaly or over-reacting to it.

### ✅ Verified before AND after switching default policy
Before flipping to DROP: opened a second, separate SSH session and kept it
open as a safety net. After flipping: the held-open session survived (proves
established/related works), a brand-new SSH connection succeeded (proves the
port-22 rule works), and a scrape from fra-aeza still returned metrics
(proves the existing 9100 rule wasn't disturbed). Saved only after all three
passed, then confirmed the saved *filter* table (not the unrelated *nat
table, which naturally still shows ACCEPT) actually reads DROP on disk.

### 📌 Monitoring track now complete
All four nodes on one firewall model (default-deny, explicit allow-lists).
Prometheus + Grafana + node_exporter + Alertmanager→Telegram all confirmed
working end to end across the last week of sessions.

### 📌 Rules reinforced
- Build and verify the full allow-list before touching a default policy —
  never flip default first and patch gaps after.
- Keep a second, already-open session as a rollback path whenever changing
  a live host's default network policy.
- An old TODO ("persist this rule") deserves a fresh check, not blind
  execution — the rule turned out to be dead and didn't need persisting at
  all, just removing.
- An unexplained anomaly gets investigated for real risk, not narrated away
  with a plausible-sounding guess — and if the exact cause can't be pinned
  down, say so rather than inventing a tidy story.

  ---

  ## 2026-08-01
### 🗺 Domain purchased — Njalla, paid in ETH
Compared Aeza (bundled with the server) against dedicated registrars first:
Aeza's own .com pricing came in notably higher, and neither Namecheap nor
Porkbun accept Russian MIR cards directly — both do accept crypto natively,
which matches money flows already in use for this project. Landed on Njalla
instead: privacy-focused registrar, WHOIS proxied by default, crypto-native —
a better fit for a censorship-circumvention project than either alternative
considered. sov3r3ign.com bought for €15 in ETH, active within ~10 minutes.

### 🛠 Full publication: DNS → nginx → firewall → TLS
- A-record pointed at the app server; caught and fixed a one-digit IP typo
  before saving (45.141... vs the real 45.151...) — same class of small,
  high-consequence mistake as the AllowedIPs incident, caught this time
  before it went live instead of after.
- nginx installed, reverse-proxying to the existing Docker container on
  loopback:8000 — the container itself never changed, it just got a public
  front door.
- Opened 80/443 on Aeza-RU's default-deny firewall (set up 07-28),
  verified, then persisted.
- certbot issued a Let's Encrypt certificate and rewrote the nginx config
  itself (HTTPS + HTTP→HTTPS redirect) — no manual TLS config needed.
- Updated .env's SITE_URL/PORTAL_BASE_URL to the real domain, restarted the
  PWA container. Confirmed end-to-end: valid TLS, admin login works over
  HTTPS (retrieved the forgotten admin password straight from .env, still
  there from the 07-19 deploy).

### 🔎 Heleket integration — code audit before wiring real keys
Reviewed the existing webhook handler before touching production keys.
Good news: the `hmac.compare_digest` fix from 07-16 is already in place, the
signature verification correctly recreates PHP's json_encode escaping, and
the webhook is idempotent (checks `payment.status == "paid"` before
re-processing).

Found a real, not-yet-tested architectural risk: `provision_basic()` commits
to an `AsyncSession` that was created in the main request's event loop, but
the function itself runs inside `asyncio.run()` in a separate thread
(necessary because the SSH calls to the entry node are blocking). Async
sessions are generally tied to the event loop that created their connection —
crossing that boundary is a known source of `RuntimeError`s that show up
under real load rather than in a quiet test. Not fixed yet — planned to
verify with a real, small (150 RUB) payment while watching logs live, rather
than guessing at the fix without evidence either way.

### 🗺 Decision — one tier, not three
Launching with a single 150 RUB/month plan. Extended and Family, plus the
multi-config dashboard mechanic, are deferred and won't be mentioned anywhere
for now. Simplified the backend's PLANS dict to match (removed the two
unused tiers and the now-unnecessary 409 special case).

### 🐛 Frontend caught two real mismatches before going live
- The pricing card still showed 200 ₽/mo — stale from before today's
  150 ₽ decision. Would have shown a different price than what Heleket
  actually charged at checkout.
- A features list claimed "Stockholm exit node" — never true for the
  current topology (the real exit is in Germany). Same class of drift as
  the outdated README, except this one is client-facing and provable by
  anyone checking the exit IP's geolocation. Reworded to a topology-neutral
  claim instead of hardcoding a location that will change again.

Checked the disabled "Extended — Coming Soon" card before assuming it was a
risk: its button has no onclick handler at all, so it can't actually reach
the backend. No fix needed there — already built defensively.

### 📋 Next
- Wire real Heleket merchant ID + API key once moderation clears (up to
  24h), then a live 150 RUB test payment with logs open, specifically
  watching for the cross-event-loop commit issue
- If it does throw: fix by having provision_basic open its own DB session
  rather than reusing one from a different event loop
- Cloud4Box night restart still waiting
- README rewrite — more overdue now that monitoring and billing have both
  moved since it was last touched

### 📌 Rules reinforced
- A small typo (one digit in an IP) in a DNS record is the same class of
  mistake as a config typo anywhere else — worth the same double-check
  before saving, not just in server configs.
- An architectural risk found by reading code carefully doesn't get "fixed"
  on paper — it gets verified with real traffic and open logs before being
  called resolved either way.
- Client-facing copy is a production surface, not documentation — a stale
  price or a false location claim there is a user-visible bug, not a
  cosmetic one.

  ---

  ## 2026-08-02
### 🐛 Mobile hamburger button overlapping page content — fixed
The fixed-position hamburger (z-index 200) sat directly on top of the sidebar
logo when the menu was open, and on top of page titles when closed — same
root cause, two visible symptoms. Fixed with a `padding-left` on page headers
plus a `:has()` selector hiding the button while the sidebar is open.
Confirmed on a real iPhone, not just assumed from the CSS.

### 🎉 Heleket moderation passed on the first attempt
No revisions requested — likely because the price mismatch and the false
"Stockholm" claim were caught and fixed before submission, not after.

### 🐛 The day's recurring bug: static edits vs `docker compose restart`
Hit this same root cause three separate times today (hamburger fix, Extended
card removal, price change) before fully internalizing it: the Dockerfile
does `COPY . .` at build time, not a live mount, so editing static/index.html
on the server has zero effect until `docker compose build` + `up
--force-recreate` — a plain `restart` just relaunches the old image. `.env`
changes are read at process start, which is why the domain switch worked with
just a restart and masked this the first time it mattered.

### 🐛 Real payment test surfaced a second instance of the same root cause
Wired what looked like real Heleket keys — got a 401, first suspected wrong
key type (Payout vs Payment). Root cause was simpler: `.env` still held
`stub` for both values because the container hadn't been recreated, only
restarted. A live diagnostic script confirmed it directly (printed key
lengths rather than guessing) before touching anything else.

### 🔎 Checked wallet/network compatibility before writing the client guide
Before recommending MetaMask, confirmed which network Heleket actually offers
at checkout: BSC (BEP-20), Tron (TRC-20), ETH (ERC-20). MetaMask supports the
first and third but not Tron. BSC is also Heleket's own "Best choice" (lowest
fees), so MetaMask + BSC is a correct, non-arbitrary recommendation — this
was checked against the real checkout screen, not assumed from general
MetaMask knowledge.

### 🛠 Built a client-facing FAQ (payment page → wallets, seed phrases, network selection)
Added an accordion FAQ to the Support page: how to get crypto without
already owning any, installing MetaMask, seed-phrase security (repeated
warning, most important section), which network to pick and why, adding BSC
to MetaMask, how to send the payment, what to do if status doesn't update.

### ⚠️ Declined a second payment provider (platega.io)
Considered as an SBP-native alternative. Researched it: all sources were
forum ads and Telegram-manager posts, not independent reviews, and its own
positioning ("payments without a legal entity") is a red flag for a project
that just passed legitimate moderation — that framing is typically aimed at
gray-market use cases. Recommended staying with Heleket rather than adding a
provider found through promotional posts.

### 🔧 Pricing raised 150 → 300 RUB/month
Grepped both the backend and frontend for every occurrence of "150" before
changing anything, rather than editing from memory — caught a third mention
buried in the FAQ text itself ("only 150 ₽ per invoice"), which would have
made the site contradict its own explanation the next day if missed.
Verified inside the running container afterward: price display, FAQ text,
and the backend PLANS dict all read 300.

### 🗺 Process finding: local repo and server have diverged
The last several days of fixes were made directly on the server via SSH;
deploy.sh syncs from the local workstation's copy, which is now stale.
Running it today would silently overwrite the server's working fixes.
Needs reconciling before deploy.sh is trusted again — not done yet.

### 📋 Next (tomorrow)
Full client-journey test end to end: find an exchanger via BestChange, buy
USDT, create a MetaMask wallet, pay 300 RUB on the site through BSC, confirm
webhook processing, and check that the config actually gets delivered.

### 📌 Rules reinforced
- `docker compose restart` ≠ picking up new static files — anything baked in
  via `COPY` needs `build` + `--force-recreate`. This bit three times today
  before it was fully internalized.
- Before recommending a specific wallet/network, check the actual checkout
  screen — not general knowledge about the wallet.
- Grep for every occurrence of a value before changing it — a stale copy can
  hide inside content you wrote yourself, not just in code.
- A payment provider's own marketing ("no legal entity needed") is itself
  evidence worth weighing, not just its fees.

  ---

  ## 2026-08-21
### 🗺 Returning after a pause — new working pattern
Adopted a fixed sequence for coming back to the project: **assess state → plan →
implement**, reconstructing reality from `git log` and server output rather than
from memory. Work had happened in unrecorded sessions, so recollection was not a
trustworthy source.

### 🔧 SSH aliases for the production nodes
Beget and Cloud4Box had never had aliases — every login was `user@IP` by hand.
Added `sov-entry` and `sov-exit`, named by **role** rather than provider, since
providers have already changed twice while the roles stayed constant. Verified
with `ssh -G` (what ssh will actually apply, not what the file appears to say).
Added `ControlMaster` — noticeably faster across long diagnostic chains.

### 🐛 `docs/` is in `.gitignore` — `docs/runbook.md` was never committed
Files tracked before the rule survive; `runbook.md` was created after it and
silently never entered git, which is why the README's link to it 404s. `git status`
stays clean, the file exists locally. Forward-looking damage is the real problem:
any new documentation file would fail to commit the same way.

### 🐛 The pushed README is the original draft, not the rework
No Project Phases section, none of the PMTU / canary / split-tunnel content;
14261 bytes against the rework's 22771. The commit message describes the rework in
detail. Checked against `origin` after first confirming the local clone wasn't
stale — `git fetch` showed the same hash on both sides.

### 🔎 Repo audit: other findings
Real production IPs published across `docs/`, `pwa/` source defaults,
`static/index.html` and the committed journal. Three `__init.py__` typos in
`monitoring/ai-bot-monitoring/` breaking those packages. `tests/` holding only an
empty `__init__.py`. `lint.yml` still pointing at `infrastructure/terraform/`,
which now lives in `archive/`. A README claim of an Ansible `firewall` role that
doesn't exist. The repo also has exactly one commit, which contradicts months of
iterative work at a glance.

### ✅ Split tunneling verified end to end
Checked all three components rather than trusting the `ip rule` entries: ipset
`ru_nets` with 11419 prefixes, the mangle `PREROUTING` mark rule, and table 200's
default via `awg1`. If the ipset were empty or the mangle rule missing, nothing
would be marked and *all* traffic — including domestic banking — would leave via
the foreign exit, with no visible symptom.

### 🐛 Exit node's `awg-quick@awg0` has been `failed` since 30 June
The interface is up and carrying all production traffic while its unit sits in
`failed`. Same runtime-only condition found on 16 July; the controlled restart
planned then never happened. Uptime of 52 days dates it to the 30 June boot.
`journalctl` gave the original cause verbatim: `ip link add awg0 type amneziawg`
→ `Unknown device type` — the module was missing for the new kernel. Brought up by
hand afterwards, never started through systemd again; systemd holds `failed` until
something attempts a start, and a running interface hides it from the outside.
**Cause is already gone**: `dkms status` shows the module built for both 7.0.0-27
(running) and 7.0.0-30 (installed, not yet booted) — July's DKMS registration has
already done its job on a future kernel.

### 🔎 Compared runtime against config before planning the restart
The config was last modified 5 July, *after* the manual bring-up, so the two could
have diverged. A first attempt with `diff <(...) <(...)` under `sudo` failed —
`/dev/fd/63: No such file or directory`, since sudo closes inherited descriptors
before the root-owned `diff` can read them. Compared by eye instead, with keys
filtered out. Everything matches except two things: the backbone peer runs
`AdvancedSecurity = on` with no such line in the file, and a dead `awg-de` peer
exists in runtime only.

### 🔎 Used the healthy node as a control group
Rather than guess the `AdvancedSecurity` default, checked the entry node: its file
also lacks the line, its unit starts normally, and its runtime shows `off`. So
start-from-config yields `off` — and the backbone is currently **asymmetric**
(`on` at the exit, `off` at the entry) while moving terabytes without trouble.
Decision: don't add the line. Letting the exit fall to `off` makes both ends
symmetric and reproducible from configuration, which is the whole point. Runtime
saved to `/root/awg0-runtime-2026-08-21.conf` for rollback.

### 🔎 Duplicated firewall rules — restart is net-neutral
Both MASQUERADE rules and both `FORWARD` pairs for `awg0` exist twice, one copy per
manual bring-up, since `PostUp` appends unconditionally. `PostDown` removes one and
`PostUp` re-adds one. `FORWARD` policy is `ACCEPT`, so these aren't load-bearing
today — they become so the moment it's tightened to `DROP`.

### ⚠️ Docker chains on the VPN entry node
`DOCKER`, `DOCKER-FORWARD`, `DOCKER-USER` and friends are present in iptables on
the entry node, despite the standing rule that Docker never shares a host with the
data plane — the rule that exists because Docker's chain manipulation broke
forwarding once already. Leftover from when the portal lived there. Harmless while
`FORWARD` is `ACCEPT`; a mine under any future hardening.

### ⚠️ Monitoring is gone
`fra-aeza` wasn't renewed and the server is deleted — the whole
Prometheus/Grafana/Alertmanager stack went with it. Until a replacement is rented,
the first notification of a production failure would come from a client.

### 📋 Next (tonight / tomorrow)
Controlled restart of `awg-quick@awg0` on the exit node at low traffic, rollback
ready. Verification is a real client loading a foreign site, not the command
output. Tomorrow: confirm it survived the night, then remove `awg-de` and the six
dead peers one change at a time, drop `docs/` from `.gitignore`, push the real
README.

### 📌 Rules reinforced
- A clean `git status` is not evidence a file is tracked — an ignore rule added
  after the fact hides only new files, and hides them silently.
- `systemd` holds `failed` until something tries to start the unit again; fixing
  the root cause doesn't clear it, and a running interface hides it entirely.
- Use an existing healthy node as the control group before changing a production
  one — the entry node answered the `AdvancedSecurity` question at zero risk.
- Diagnose from a sample that actually includes production. Concluded the
  infrastructure was down after snapshotting only the two migration nodes; prod
  was never in the loop that was written.