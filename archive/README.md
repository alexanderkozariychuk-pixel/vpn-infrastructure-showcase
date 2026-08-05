# Archive

Earlier approaches that were built, tested, and deliberately replaced —
kept here as a record of what was tried and why it didn't become the
production setup, not as working code.

## ai-bot-monitoring-prototype/
A Telegram bot (FastAPI + Gemini) for infrastructure monitoring and
AI-assisted log analysis. Worked, but superseded by a native Prometheus +
Grafana + Alertmanager stack (see `/monitoring` and the main README) —
a standard, more maintainable observability stack rather than a bespoke bot.

## uptime-kuma-monitoring/
Uptime Kuma with a custom AWG-tunnel healthcheck script pushing status
updates. Replaced for the same reason as above — consolidated into the
Prometheus/Grafana stack instead of running a second monitoring system.

## experimental-protocols/
Ansible playbooks for alternative VPN protocols and locations tried during
early infrastructure exploration (Shadowsocks, tun2socks, a Bulgaria node,
the original Moldova relay). Dropped for performance reasons under real
mobile-network DPI — AmneziaWG's obfuscated WireGuard consistently
outperformed them and became the production protocol. See the main
project journal for the underlying research (DPI behavior on mobile
networks, whitelist-based filtering, tethering detection via TTL).

## early-tooling/
Standalone scripts (config generation, key rotation, VPS provisioning)
written before the infrastructure's current complexity. Superseded by the
PWA's own provisioning pipeline and direct, verified SSH operations — kept
here rather than deleted since they reflect real early tooling decisions.

## terraform-yandex-cloud/
Infrastructure-as-code trial for provisioning via Yandex Cloud. Tested but
not adopted for production — Yandex Cloud's policies didn't fit the
project's needs, so the infrastructure moved to direct VPS providers
(Beget, Cloud4Box, Aeza) with manual, verified SSH-based configuration
instead.
