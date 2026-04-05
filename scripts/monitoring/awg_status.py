#!/usr/bin/env python3
"""
Send AmneziaWG status and metrics to the Uptime Kuma push monitor.
Copy this file to /usr/local/bin/awg_status.py on your server and replace the token.
"""

import subprocess
import re
import urllib.request
import urllib.parse
from datetime import datetime

# Replace with your actual Uptime Kuma push URL (without query parameters)
PUSH_URL = "http://YOUR_UPTIME_KUMA_IP:3001/api/push/YOUR_TOKEN"

def get_awg_status():
    """Parse output of `sudo awg show awg0` and return dict with metrics."""
    try:
        output = subprocess.check_output(["sudo", "awg", "show", "awg0"], text=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        return {"status": "down", "peers": 0, "rx_bytes": 0, "tx_bytes": 0, "handshake": None}
    
    peers = len(re.findall(r"^peer:", output, re.MULTILINE))
    handshake_match = re.search(r"latest handshake: (.*)", output)
    handshake = handshake_match.group(1).strip() if handshake_match else "never"
    
    rx_total = 0.0
    tx_total = 0.0
    for match in re.finditer(r"transfer: ([\d.]+) ([\w]+) received, ([\d.]+) ([\w]+) sent", output):
        rx_val = float(match.group(1))
        rx_unit = match.group(2)
        tx_val = float(match.group(3))
        tx_unit = match.group(4)
        def to_bytes(val, unit):
            if unit == "B":
                return val
            elif unit == "KiB":
                return val * 1024
            elif unit == "MiB":
                return val * 1024 * 1024
            elif unit == "GiB":
                return val * 1024 * 1024 * 1024
            else:
                return val
        rx_total += to_bytes(rx_val, rx_unit)
        tx_total += to_bytes(tx_val, tx_unit)
    
    status = "up" if handshake != "never" else "down"
    return {
        "status": status,
        "peers": peers,
        "rx_bytes": rx_total,
        "tx_bytes": tx_total,
        "handshake": handshake
    }

def send_to_kuma(status, msg):
    """Send status and message to Uptime Kuma push endpoint."""
    url = f"{PUSH_URL}?status={status}&msg={urllib.parse.quote(msg)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.getcode() == 200
    except Exception as e:
        print(f"Failed to send to Kuma: {e}")
        return False

def main():
    data = get_awg_status()
    if data["status"] == "up":
        msg = (f"Peers: {data['peers']}, "
               f"RX: {data['rx_bytes']:.0f} B, TX: {data['tx_bytes']:.0f} B, "
               f"Handshake: {data['handshake']}")
        send_to_kuma("up", msg)
        print(f"{datetime.now()}: AWG UP - {msg}")
    else:
        send_to_kuma("down", "No active handshake or interface down")
        print(f"{datetime.now()}: AWG DOWN")

if __name__ == "__main__":
    main()
