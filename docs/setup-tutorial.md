```markdown
Installing and configuring VPN infrastructure

Requirements
- VPS with Ubuntu 24.04 (minimum 1 vCPU, 1 GB RAM, 15 GB disk)
- SSH access to the server (password or key)
- Basic familiarity with the command line

```

---
1. Server Preparation
 
1.1. System Update

```bash
sudo apt update && sudo apt upgrade -y
```

1.2. User creation and configuration (recommended)

Create a user (replace vpnadmin with the desired name):

```bash
sudo adduser vpnadmin
sudo usermod -aG sudo vpnadmin
```

Copy the public key (run on your computer; instead of <ip_server>, specify the IP address of your server):

```bash
ssh-copy-id vpnadmin@<ip_server>
```

1.3. Configuring the firewall

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 443/udp  # AmneziaWG (port can be changed)
sudo ufw enable
```

---

2. Installing AmneziaWG

2.1. Download and run the installation script

```bash
curl -O https://raw.githubusercontent.com/Varckin/amneziawg-install/main/amneziawg-install.sh
chmod +x amneziawg-install.sh
sudo ./amneziawg-install.sh
```

2.2. Installation parameters

- Public IPv4 or IPv6 address: enter the IP of your VPS
- Public interface: usually eth0 or ens3 (check with ip a command)
- AmneziaWG interface name: leave awg0
- Server AmneziaWG IPv4: 10.66.66.1/24
- Server AmneziaWG port: 443 (you can use another one)
- DNS resolvers: 1.1.1.1 and 1.0.0.1
- Allowed IPs for clients: 0.0.0.0/0,::/0
- Jc, Jmin, Jmax, S1, S2, H1–H4: leave the default values (they are randomly generated)

After installation, check the status:

```bash
sudo systemctl status awg-quick@awg0
sudo awg show
```

2.3. Adding a client

Run the script again:

```bash
sudo ./amneziawg-install.sh
```

The script will prompt you to add a client. Enter a name (for example, macbook) and get the configuration file.

The client configuration is saved in /root/awg0-client-<name>.conf. Copy it to your device (execute the following command on your MacBook, for example):

```bash
scp root@<IP_server>:/root/awg0-client-<name>.conf ~/Downloads/
```

---

3. Installing Xray + 3X-UI (additional protocol)

3.1. Installing the panel

```bash
bash <(curl -Ls https://raw.githubusercontent.com/mhsanaei/3x-ui/master/install.sh)
```

Follow the instructions:

- Panel port: 54321
- SSL certificate: select 2 (Let's Encrypt for IP) or skip if HTTPS is not needed.
- Remember the login and password you set (by default, admin / admin).

3.2. Creating an inbound (VLESS+Reality)

1. Open the panel: http://<IP_server>:54321
2. Go to Inbounds → Add Inbound.
3. Fill in:
   - Protocol: VLESS
   - Port: 443
   - Network: tcp
   - Security: reality
   - Reality Settings:
     - Dest: www.microsoft.com:443
     - ServerNames: www.microsoft.com
     - PrivateKey: click Generate
     - ShortIds: 6ba85179e30d4fc2
     - Fingerprint: chrome
4. Add a client (click Add Client, generate an ID).
5. Save.

Copy the link (Link button) — it will be useful for the client.

---

4. Monitoring (Uptime Kuma + Prometheus + Node Exporter + Alertmanager)

4.1. Installing Docker

```bash
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker --now
```

4.2. Creating docker-compose.yml

Create the /opt/monitoring folder and the file docker-compose.yml with the following content:

```yaml
version: '3.8'

services:
  node-exporter:
    image: prom/node-exporter:latest
    container_name: node-exporter
    restart: unless-stopped
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--path.rootfs=/rootfs'

  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    restart: unless-stopped
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager-data:/alertmanager

  uptime-kuma:
    image: louislam/uptime-kuma:latest
    container_name: uptime-kuma
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - uptime-kuma-data:/app/data

volumes:
  prometheus-data:
  alertmanager-data:
  uptime-kuma-data:
```

4.3. Configuration files

Create in the same folder:

prometheus.yml

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

rule_files:
  - "alerts.yml"

scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
```

alerts.yml

```yaml
groups:
  - name: node_alerts
    rules:
      - alert: HighCPU
        expr: 100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU on {{ $labels.instance }}"
          description: "CPU usage is above 80% for 5 minutes."

      - alert: LowDiskSpace
        expr: (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100 < 15
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Only {{ $value }}% free on root partition."

      - alert: ServerDown
        expr: up{job="node"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Server is down"
          description: "VPS is not responding to scrape."
```

alertmanager.yml

```yaml
route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'telegram'

receivers:
  - name: 'telegram'
    telegram_configs:
      - bot_token: 'YOUR_BOT_TOKEN'  # enter your bot token from Telegram (@BotFather)
        chat_id: YOUR_CHAT_ID        # enter your Telegram ID (get it from @userinfobot)
        parse_mode: 'HTML'
        api_url: 'https://api.telegram.org'
```

4.4. Launching monitoring

```bash
cd /opt/monitoring
docker-compose up -d
```

4.5. AmneziaWG verification script for Uptime Kuma

Create the file /usr/local/bin/check_awg.sh:

```bash
#!/bin/bash
PUSH_URL="http://localhost:3001/api/push/<TOKEN>?status=up&msg=OK"

if sudo awg show awg0 > /dev/null 2>&1; then
    if sudo awg show awg0 | grep -q "latest handshake"; then
        curl -s -o /dev/null "$PUSH_URL"
        echo "$(date): AWG OK"
    else
        curl -s -o /dev/null "http://localhost:3001/api/push/<TOKEN>?status=down&msg=NO_HANDSHAKE"
        echo "$(date): AWG NO HANDSHAKE"
    fi
else
    curl -s -o /dev/null "http://localhost:3001/api/push/<TOKEN>?status=down&msg=INTERFACE_DOWN"
    echo "$(date): AWG INTERFACE DOWN"
fi
```

Add to cron:

```bash
sudo crontab -e
```

Add the following line:

```
* * * * * /usr/local/bin/check_awg.sh >> /var/log/awg_health.log 2>&1
```

---

5. Health check

- AmneziaWG: Connect to the client, check the IP (it must be the server’s IP).
- Xray: Use the link from 3X-UI in Hiddify or V2RayNG.
- Monitoring: open in the browser:
  - Uptime Kuma: http://<IP_server>:3001
  - Prometheus: http://<IP_server>:9090
  - Node Exporter: http://<IP_server>:9100
- Alerts: wait for it to be triggered (for example, turn off AmneziaWG) — a Telegram message should arrive.

---

Notes

- UDP port 443 is used for AmneziaWG, TCP port 443 is used for Xray. They do not conflict.
- The SSL certificate of the 3X-UI panel requires a domain if you want HTTPS.
- This guide describes only the entry server. In the next steps, an exit node and automation will be added.


