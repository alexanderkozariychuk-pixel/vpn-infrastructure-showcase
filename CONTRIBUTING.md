# Contributing to Multi-Hop VPN Infrastructure

Thank you for your interest in contributing! This project is a hands‑on infrastructure showcase, and contributions that improve reliability, documentation, or automation are welcome.

## How to Contribute

### Report Bugs or Suggest Features
- Open a GitHub issue with a clear title and description.
- Include steps to reproduce, environment details (OS, VPS provider), and relevant logs.

### Submit Code Changes
1. **Fork** the repository and create a new branch.
2. **Follow the existing style**:
   - Bash scripts: use `#!/bin/bash`, handle errors (`set -e`), and keep lines under 100 characters.
   - YAML (Ansible, Docker Compose): use 2‑space indentation.
   - Markdown: keep tables and lists readable.
3. **Test your changes** on a staging VPS if possible.
4. **Commit with a clear message** (e.g., `Fix healthcheck script`, `Add troubleshooting note about MTU`).
5. **Open a pull request** against the `main` branch.

### Improve Documentation
- Clarify unclear sections in `README.md`, `setup-tutorial.md`, `troubleshooting.md`, or `architecture.md`.
- Fix typos, grammar, or formatting.
- Add missing examples or expand explanations.

## Code of Conduct
Be respectful and constructive. Harassment, offensive language, or unhelpful criticism will not be tolerated.

## Development Priorities
- **Automation**: Python scripts for Aeza API, Ansible playbooks.
- **Observability**: Prometheus, Grafana, Uptime Kuma.
- **Stability**: Ensure VPN works reliably across Wi‑Fi and mobile networks.

## Getting Help
If you are unsure about something, open a discussion issue. I will try to respond as soon as possible.

Thank you for helping make this project better!
