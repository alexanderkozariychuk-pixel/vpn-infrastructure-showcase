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

## Long-term Plans

- Activate Russian Bridge node with full Policy-Based Routing
- Migrate all clients from Moldova to Russian Bridge
- Complete automation of deployment and configuration processes
- Migrate monitoring stack to a dedicated VPS in the Netherlands
- Implement automatic failover using residential proxy pool
- Prepare detailed portfolio materials for Junior DevOps / Linux SysAdmin positions
