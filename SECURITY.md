# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability (e.g., insecure defaults, exposed ports, potential traffic leakage, or issues in custom scripts), **please do not open a public issue**.

Contact me via the email address associated with my GitHub account. I will acknowledge your report within 48 hours and work on a fix.

## Supported Versions

Only the latest version on the `main` branch is supported.

## Scope

This policy covers:
- Configuration examples (AmneziaWG, Xray, monitoring).
- Scripts in `scripts/`.
- Ansible playbooks and roles.
- Python automation code.

It does **not** cover third‑party software (Ubuntu, WireGuard, Xray, Docker, etc.) – refer to their respective security policies.

## Security Best Practices Applied

- **No secrets in the repository** – placeholders used for IPs, keys, tokens.
- **SSH key‑based authentication only** (password authentication disabled).
- **Firewall (UFW)** restricts access to essential ports (22, 443/udp, 443/tcp, 3001, 9090, 9093, 9100).
- **Monitoring alerts** configured for anomalies (high CPU, low disk, server down).
- **Automatic backups** of configuration files (`scripts/backup-configs.sh`).

## Responsible Disclosure

Once a vulnerability is confirmed and fixed, I will publicly acknowledge the reporter (unless anonymity is requested) and document the fix in `PROJECT_JOURNAL.md`.

Thank you for keeping the infrastructure secure.
