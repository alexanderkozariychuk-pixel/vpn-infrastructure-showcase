# Troubleshooting

```markdown

This document contains typical problems that have arisen during the deployment of VPN infrastructure, and ways to solve them.

```

## 1. Common connection problems

### 1.1. The client is not connecting, there is a handshake timeout in the logs
**Reason**: UDP port 443 (or another one specified in the configuration) is blocked by the provider or firewall.

**Solution**:
⁃	 Check if the port on the server is open: `sudo ufw status verbose'. If not, add:

  ```bash
  sudo ufw allow 443/udp
```

- Make sure that AmneziaWG listens to the port: sudo ss -ulpn | grep 443.
- If the port is open, but the handshake is not working, try reducing the MTU on the client by adding the line MTU = 1280 (or 1200) to the config

### 1.2. There is a connection, but the Internet is not working

**Reason**: IP‑forward is not enabled on the server or NAT is not configured.

**Solution**:

- Enable packet forwarding:
```bash
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
  sudo sysctl -p
  ```
- 	Make sure that the AmneziaWG config (/etc/amneziawg/awg0.conf) has the PostUp and PostDown rules for iptables.:
  ```ini
  PostUp = iptables -A FORWARD -i awg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
  PostDown = iptables -D FORWARD -i awg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
  ```
(replace eth0 with your external interface).

### 1.3. The client connects via Wi‑Fi, but not via a mobile network (intermittent connectivity)

#### Problem
- VPN works reliably over Wi‑Fi.
- On mobile network, connection often fails with handshake timeout.
- However, sometimes after waiting 10–30 seconds, toggling Airplane mode, or retrying a few times, the connection succeeds.
- Even when connected, the tunnel may stay active for minutes or hours, but re‑establishing it after a disconnect is unpredictable.

#### Environment
- **VPS**: Moldova (Cloud4Box), Ubuntu 24.04
- **VPN protocol**: AmneziaWG (UDP/443) with obfuscation (Jc, Jmin, Jmax, H1–H4)
- **Clients**: iOS / macOS (tested with AmneziaWG and WireGuard apps)
- **Alternative protocols tested**: Xray (Reality), Trojan, Hysteria2
- **Network**: Mobile LTE (operator with known DPI/whitelist filtering)

#### Hypothesis
1. Mobile operator uses a **dynamic DPI** that temporarily blacklists the server IP/port after detecting a VPN handshake attempt.
2. The blacklist is short‑lived (10–30 seconds) and can be cleared by resetting the network state (Airplane mode).
3. UDP traffic may be throttled or rate‑limited, making the first handshake more likely to fail.
4. Once the tunnel is established, keep‑alive packets may prevent re‑detection for a while.

#### Tests

| Test | Description | Result |
|------|-------------|--------|
| **Ping** | `ping 45.140.146.134` from mobile network | Successful (server reachable) |
| **DNS** | `nslookup google.com` | Resolved, but HTTP access blocked |
| **AmneziaWG (first attempt)** | Connect immediately after enabling mobile data | Handshake timeout after 5 seconds |
| **AmneziaWG (retry immediately)** | Re‑attempt connection without any delay | Still fails (may extend block) |
| **AmneziaWG (wait 10–30 sec)** | Wait before retrying | Often succeeds |
| **AmneziaWG (Airplane mode)** | Toggle Airplane mode, then connect | Usually works on first try |
| **AmneziaWG (MTU 1280)** | Reduce MTU on client | Same pattern: fails first, works after delay |
| **Port change** | Move AmneziaWG to UDP/8443 | Same intermittent behaviour |
| **Xray Reality (TCP/443)** | Switch to Xray on TCP/443 | Fails initially, sometimes works after delay |
| **SSH (TCP/22)** | `ssh root@45.140.146.134` | Works reliably (port 22 not filtered) |

#### Results
- The server IP is reachable (ping, SSH work).
- DNS resolution works, but HTTP/HTTPS to non‑whitelisted domains fails.
- VPN handshake fails on first attempt but may succeed after a short delay or network reset.
- Behaviour is consistent with **dynamic filtering**: the operator blocks the IP/port temporarily after detecting VPN activity, then lifts the block after a short period.
- Once a connection is established, it can remain active for extended periods, indicating that established flows are not constantly re‑inspected.

#### Conclusion
The mobile network employs a **dynamic DPI system** that:
- Detects VPN handshake attempts and temporarily blacklists the destination IP/port.
- Clears the blacklist after ~10–30 seconds or when the device renews its network session (Airplane mode).
- This behaviour explains why retrying after a delay or toggling Airplane mode often succeeds.

The VPN infrastructure itself is correctly configured; the issue is the network's **rate‑limiting / temporary blacklisting** mechanism.

#### Next Steps
- **Client‑side workarounds**:
  - Add `PersistentKeepalive = 25` to the client config to keep the tunnel alive once connected.
  - Implement retry logic with delays (e.g., `wg-quick down wg0; sleep 10; wg-quick up wg0`).
  - Use Airplane mode toggle as a quick reset when needed.
- **Protocol‑level improvements**:
  - Use TCP‑based protocols like Xray Reality (TCP/443), which may be less affected by UDP‑specific rate limits.
  - Experiment with other obfuscation methods (e.g., Xray with WebSocket over TLS) to reduce detection.
- **Long‑term**:
  - If the problem persists, consider using a different mobile operator or relying on Wi‑Fi where possible.

> **Note**: This intermittent behaviour is a common characteristic of modern DPI‑based filtering. It demonstrates that the network does not permanently block our infrastructure but applies dynamic, short‑term restrictions. Our monitoring scripts (Uptime Kuma) can be used to track connectivity patterns and alert when the tunnel goes down for an extended period.
## 2. Errors in the installation and configuration of AmneziaWG

### 1.4. VLESS + XHTTP fails under strict domain whitelist

**Observation**:  
Even with XHTTP transport (attempting to mimic allowed domains such as Microsoft.com), the connection fails on mobile networks enforcing strict domain/IP whitelisting.  

On Wi-Fi networks (without strict filtering), VLESS + XHTTP works but shows lower performance compared to AmneziaWG.

---

**Analysis**:  
The failure is not related to DPI, but to **strict whitelist enforcement at the network level**.

Such filtering typically allows traffic only to:
- specific domains (e.g., Yandex, VK)
- or predefined IP ranges

Technologies like VLESS, Reality, or XHTTP can disguise traffic patterns, but **cannot bypass restrictions based on destination IP/domain**, since:
- DNS resolution and SNI still reveal the target
- connections to non-whitelisted endpoints are blocked before protocol-level obfuscation becomes relevant

---

**Conclusion**:  
In a strict whitelist environment, protocol-level obfuscation (Xray, VLESS, Reality, etc.) is ineffective.

The only theoretical workaround would involve:
- tunneling traffic through already whitelisted services (e.g., WebRTC-based platforms like VK Calls or Yandex Telemost)
- or leveraging allowed infrastructure as a relay

However, such approaches are:
- highly complex
- unstable
- and out of scope for this project

---

**Recommendation**:  
- Accept the limitation in strictly whitelisted mobile networks  
- Use alternative networks/operators where possible  
- For standard or DPI-based restrictions, AmneziaWG (UDP/443) remains the most reliable and performant solution



### 2.1. The installation script does not run or returns an error.

**Reason**: the script is incompatible with the Ubuntu version, or there is no access to GitHub.

**Solution**:

- 	Make sure you are using Ubuntu 22.04 or 24.04.
- Download the script manually from GitHub via the mobile Internet or another channel if it is blocked.
-	Run with sudo rights.

### 2.2. After adding the client, it is not visible in the sudo awg show.

**Reason**: The AmneziaWG service has not been restarted.

**Solution**:

```bash
sudo systemctl restart awg-quick@awg0
sudo systemctl status awg-quick@awg0
```

## 3. Problems with Xray and the 3X-UI panel

### 3.1. The 3X-UI panel does not open in the browser

**Reason**: port 54321 is not open in the firewall or the service is not running.

**Solution**:

-	Check the status: sudo systemctl status x-ui. If not active, run: sudo systemctl start x-ui.
-	Open the port: sudo ufw allow 54321/tcp.
- If the panel was set to HTTPS and you don't have a domain, try opening http://<IP>:54321 instead of https.

### 3.2. Unable to log in to the panel (incorrect login/password)

**Reason**: The standard admin/admin has been changed or random data has been installed.

**Solution**:

-  In the terminal, run:
```bash
x-ui settings
  ```
or
  ```bash
  /usr/local/x-ui/x-ui settings
  ```
  The output will show the login, password, port and path.
	⁃	If you forgot your password, reset it.:
  ```bash
  x-ui reset
  ```

### 3.3. Xray does not start, error in invalid privateKey logs

**Reason**: the Reality key format is incorrect (for example, it was not generated via xray x25519).

**Solution**:

-	Generate the keys again:
  ```bash
  /usr/local/bin/xray x25519
  ```
-	Copy the private key into the config (in the 3X-UI panel, click Generate or paste it manually).
-	If the error repeats, create an inbound through the panel using the Generate button — the panel will create the correct keys by itself.

### 3.4. After updating the 3X-UI, access is lost.

**Reason**: the update may have changed the port or path.

**Solution**:

- Check the settings via x-ui settings.
- Restore SSH access and reinstall the panel if necessary.

## 4. Monitoring (Uptime Kuma, Prometheus, Alertmanager)

### 4.1. Docker containers are not running

**Reason**: error in docker-compose.yml, I don't have enough permissions, or the ports are busy.

**Solution**:

- Check the syntax: docker-compose config.
-	View the logs: docker-compose logs <service>.
- Make sure that ports 3001, 9090, 9093, 9100 are not occupied by other processes.

### 4.2. Uptime Kuma does not receive push notifications from the script

**Reason**: invalid URL or token, or the script is not executed by cron.

**Solution**:

- Run the script manually: sudo /usr/local/bin/check_awg.sh .
- Make sure that the script specifies the correct PUSH_URL with the Uptime Kuma token.
- Check the cron logs: sudo tail -f /var/log/awg_health.log.
- Make sure that the script is added to the crontab with the full path.

### 4.3. Alerts are not sent to Telegram

**Reason**: invalid bot_token or chat_id, or Alertmanager is not configured.

**Solution**:

- Make sure that the bot was created in Telegram via @BotFather and the token is copied without unnecessary characters.
- Get your chat_id via @userinfobot.
- Check the configuration of alertmanager.yml and restart the container: docker-compose restart alertmanager.
- 	Check that Prometheus sees the Alertmanager: in the Prometheus interface (port 9090), go to Status → Targets.

## 5. Problems with clients on macOS

### 5.1. The AmneziaVPN application crashes when trying to connect

**Reason**: Client version is incompatible with the server or there is a bug in the application.

**Solution**:

- Use the official WireGuard client instead of AmneziaVPN (configs are compatible).
- If WireGuard is unavailable, try installing AmneziaVPN version 4.8.11.4 (older, but working).
- Delete all the AmneziaVPN files from the ~/Library/Caches, ~/Library/Application Support folders, then reinstall.

### 5.2. wg-quick error: line 1: syntax error near unexpected token '<'

**Reason**: wg and wg-quick were downloaded as HTML pages, not as scripts.

**Solution**:

-	Download the correct files from GitHub:
```bash
  sudo curl -L -o /usr/local/bin/wg https://raw.githubusercontent.com/WireGuard/wireguard-tools/master/src/wg
  sudo curl -L -o /usr/local/bin/wg-quick https://raw.githubusercontent.com/WireGuard/wireguard-tools/master/src/wg-quick
  sudo chmod +x /usr/local/bin/wg /usr/local/bin/wg-quick
  ```
- If links are unavailable, build from source or install via MacPorts.

### 5.3. Request a password from a keychain

**Reason**: in macOS, AmneziaVPN tries to create or use a record in a bundle, but the password does not fit.

**Solution**:

- Open the Keychain Access application, find the AmneziaVPN records and delete them.
- 	Restart AmneziaVPN. The first time you start, a new account will be created, and the password will no longer be requested.
- If it doesn't help, reset the keychain via the menu "Keychain" → "Settings" → "Reset default bundles".

## 6. Miscellaneous

### 6.1. GitHub or other sites do not open when connected via VPN

**Reason**: There may be a DNS conflict or AllowedIPs is incorrectly configured.

**Solution**:

- In the client's configuration, add or change DNS to 1.1.1.1 and 1.0.0.1.
- Make sure that the [Peer] section contains AllowedIPs = 0.0.0.0/0, ::/0.

### 6.2. The Failed to fetch error appears in the Uptime Kuma logs.

**Reason**: The Push URL uses http://localhost but monitoring is running in a container, and the localhost for it is the container itself, not the host.

**Solution**:

- In the check_awg script.sh use the host's IP address or host name (http://<Server ip>:3001/...), not localhost.
- Make sure that port 3001 is open for access from the host.

### 6.3. After restarting the server, the VPN does not rise automatically.

**Reason**: Autorun of services is not enabled.

**Solution**:

```bash
sudo systemctl enable awg-quick@awg0
sudo systemctl enable x-ui
sudo systemctl enable docker
```

## 7. Stability tests (2026-04-02)

These tests were performed on the Moldova entry node to validate recovery mechanisms and monitoring.

### Test 1: Restarting AmneziaWG service
- **Action**: `sudo systemctl restart awg-quick@awg0`
- **Expected**: Clients automatically reconnect within 5‑10 seconds.
- **Result** (Wi‑Fi clients): Reconnected immediately and automatically.
- **Result** (Mobile clients): Did **not** reconnect automatically. Manual intervention (Airplane mode toggle) was required to restore connection.
- **Conclusion**: Mobile networks are less tolerant to service disruptions. For mobile clients, consider implementing a keep‑alive mechanism or advising users to toggle network.

### Test 2: Changing client MTU
- **Action**: Modify client config from `MTU = 1280` to `1200`, then reconnect.
- **Result**: No noticeable difference in performance or stability.
- **Conclusion**: MTU = 1280 is safe; reducing further is unnecessary.

### Test 3: Simulating server unreachable (temporary firewall block)
- **Action**: On server: `sudo ufw deny 443/udp` for 30 seconds, then `sudo ufw delete deny 443/udp`.
- **Expected**: Client loses connection, then automatically recovers after the block is lifted (handshake retry).
- **Result**: Exactly as expected. Clients re‑established handshake within 30 seconds after the block was removed.
- **Conclusion**: The VPN client handles temporary network outages correctly.

### Test 4: Push monitor validation
- **Action**: Stop AmneziaWG (`sudo systemctl stop awg-quick@awg0`), wait 2 minutes, then start again.
- **Expected**: Uptime Kuma push monitor shows `down`, then `up`. Telegram alert fires.
- **Result**: Exactly as expected. Alert received within 1 minute of service stop; recovery notification sent after restart.
- **Conclusion**: The monitoring stack (`check_awg.sh` + Uptime Kuma + Telegram) is fully functional.

### Summary of findings
- Mobile networks are less robust to VPN service interruptions than Wi‑Fi.
- The monitoring stack is reliable.
- MTU adjustments are not critical for this setup.
- The client can recover from temporary server‑side blocks.

## Notes

- Run all commands that require root access via sudo.
- 	Service logs can be viewed through journalctl -u <service>.
- 	If the problem persists, check the current versions of the software (Ubuntu, AmneziaWG, Xray, Docker).

