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

