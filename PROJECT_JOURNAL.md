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

## Next steps (planned)

### Immediate (April 2, 2026)
- **Complete automation templates**  
  - Write basic Ansible playbook for AmneziaWG installation (`ansible/playbooks/deploy-awg.yml`).  
  - Create Terraform example for VPS provisioning (`terraform/main.tf.example` with Timeweb provider).  
  - Fill `terraform/terraform.tfvars.example` and `ansible/group_vars/all.yml.example` with placeholders.

- **Add contributing and security guidelines**  
  - Create `CONTRIBUTING.md` and `SECURITY.md` to show readiness for collaboration.

- **Stability experiments**  
  - Perform extended connectivity tests on the Moldova VPS: monitor uptime, handshake stability, and reconnect behaviour.  
  - Simulate network disruptions (e.g., restarting the `awg-quick` service, changing client MTU, toggling firewall rules) and document results in `troubleshooting.md`.  
  - Validate the effectiveness of the current monitoring scripts (`check_awg.sh`, Uptime Kuma) under different failure scenarios.

- **Documentation**  
  - Add a section in `troubleshooting.md` about stability testing and observed behaviour.  
  - Ensure all new scripts and config examples are properly linked from `README.md`.


### Future Roadmap
- Rent a second VPS in Germany, install AmneziaWG, and establish an exit tunnel (entry → exit).  
- Automate full deployment with Ansible + Terraform.  
- Add a proxy pool for fault tolerance.  
- Write a custom metrics exporter for AmneziaWG.  
- Implement CI/CD (GitHub Actions) for automated testing.
