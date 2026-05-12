# services/net_manager.py
import logging
import subprocess
from dataclasses import dataclass

from config import (
    AWG_SERVICE,
    AWG_INTERFACE,
    MOLDOVA_IP,
    MOLDOVA_USER,
    IPIP_INTERFACE,
    BRIDGE_IP,
    BRIDGE_USER,
    BRIDGE_AWG_INTERFACE,
)

logger = logging.getLogger(__name__)


@dataclass
class PeerStatus:
    public_key: str
    endpoint: str = "N/A"
    handshake: str = "never"
    transfer: str = "0 B"


# ----------------------------------------------------------------------
# SSH helper
# ----------------------------------------------------------------------

def _ssh(cmd: str, timeout: int = 10) -> tuple[str, str]:
    """
    Run command on Moldova via SSH.
    Returns (stdout, stderr).
    """
    result = subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{MOLDOVA_USER}@{MOLDOVA_IP}",
            cmd,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip(), result.stderr.strip()

def _ssh_bridge(cmd: str, timeout: int = 10) -> tuple[str, str]:
    """Run command on Bridge via SSH."""
    result = subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=5",
            f"{BRIDGE_USER}@{BRIDGE_IP}",
            cmd,
        ],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip(), result.stderr.strip()


def get_bridge_status_data() -> tuple[list[PeerStatus] | None, str | None]:
    """Fetch AWG peers from Bridge."""
    stdout, stderr = _ssh_bridge(f"sudo awg show {BRIDGE_AWG_INTERFACE}")
    if not stdout or "interface" not in stdout.lower():
        return None, stderr or "No data from Bridge"

    peers = []
    current = None
    for line in stdout.split("\n"):
        line = line.strip()
        if line.startswith("peer:"):
            if current:
                peers.append(current)
            current = PeerStatus(public_key=line.split(": ", 1)[1])
        elif current and "latest handshake:" in line:
            current.handshake = line.split(": ", 1)[1]
        elif current and "transfer:" in line:
            current.transfer = line.split(": ", 1)[1]
        elif current and "endpoint:" in line:
            current.endpoint = line.split(": ", 1)[1]
    if current:
        peers.append(current)

    return peers, None


def get_bridge_client_names() -> dict:
    """Parse client names from awg0.conf on Bridge."""
    stdout, _ = _ssh_bridge(
        f"sudo cat /etc/amnezia/amneziawg/{BRIDGE_AWG_INTERFACE}.conf"
    )
    names = {}
    current_name = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("### "):
            current_name = line[4:].strip()
        elif line.startswith("PublicKey") and current_name:
            key = line.split("=", 1)[1].strip()
            names[key[:12]] = current_name
            current_name = None
    return names

# ----------------------------------------------------------------------
# AWG status
# ----------------------------------------------------------------------

def get_amnezia_status() -> str:
    """Fetch raw awg show output from Moldova."""
    stdout, stderr = _ssh("sudo /usr/bin/awg show")
    return stdout if stdout else f"Error: {stderr}"


def get_full_status_data() -> tuple[list[PeerStatus] | None, str | None]:
    """Parse awg show output into PeerStatus list."""
    raw = get_amnezia_status()
    if not raw or "interface" not in raw.lower():
        return None, raw

    peers = []
    current = None
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("peer:"):
            if current:
                peers.append(current)
            current = PeerStatus(public_key=line.split(": ", 1)[1])
        elif current and "latest handshake:" in line:
            current.handshake = line.split(": ", 1)[1]
        elif current and "transfer:" in line:
            current.transfer = line.split(": ", 1)[1]
        elif current and "endpoint:" in line:
            current.endpoint = line.split(": ", 1)[1]
    if current:
        peers.append(current)

    return peers, None


# ----------------------------------------------------------------------
# Logs
# ----------------------------------------------------------------------

def get_logs_text(lines: int = 30) -> str:
    """Fetch recent AWG journal logs from Moldova via SSH."""
    cmd = (
        f"sudo journalctl -u {AWG_SERVICE} "
        f"-n {lines} --no-pager --output short-iso "
        f""
    )
    stdout, stderr = _ssh(cmd)
    if stdout:
        return stdout
    return f"❌ Log error: {stderr or 'empty output'}"


def clear_logs() -> bool:
    """Vacuum old logs on Moldova via SSH."""
    stdout, stderr = _ssh(
        "sudo journalctl --vacuum-time=2d", timeout=15
    )
    if stderr and "error" in stderr.lower():
        return False
    return True


# ----------------------------------------------------------------------
# System health
# ----------------------------------------------------------------------

def _parse_metrics(output: str) -> dict:
    """Parse uptime/free/df output into metrics dict."""
    lines = [l.strip() for l in output.split("\n") if l.strip()]
    if len(lines) >= 4:
        return {
            "cpu": lines[0],
            "ram": lines[1],
            "swap": lines[2],
            "disk": lines[3] + " free",
        }
    return {"cpu": "N/A", "ram": "N/A", "swap": "N/A", "disk": "N/A"}


_METRICS_CMD = (
    "uptime | awk -F'load average:' '{print $2}'; "
    "free -m | awk '/^Mem:/ {print $3\"/\"$2\" MB\"}'; "
    "free -m | awk '/^Swap:/ {print $3\"/\"$2\" MB\"}'; "
    "df -h / | awk 'NR==2 {print $4}'"
)


def get_system_health() -> tuple[dict, dict, str | None]:
    """
    Collect CPU/RAM/Swap/Disk from Bulgaria (local) and Moldova (SSH).
    Returns (local_metrics, remote_metrics, error).
    """
    # Local — Bulgaria (inside container)
    local = {}
    try:
        res = subprocess.run(
            _METRICS_CMD, shell=True,
            capture_output=True, text=True, timeout=5,
        )
        local = _parse_metrics(res.stdout)
    except Exception as e:
        logger.error("Local health check failed: %s", e)
        local = {"cpu": "N/A", "ram": "N/A", "swap": "N/A", "disk": "N/A"}

    # Remote — Moldova via SSH
    remote = {}
    err = None
    try:
        stdout, stderr = _ssh(_METRICS_CMD, timeout=15)
        if stdout:
            remote = _parse_metrics(stdout)
        else:
            err = stderr or "Empty response"
            remote = {"cpu": "N/A", "ram": "N/A", "swap": "N/A", "disk": "N/A"}
    except Exception as e:
        err = str(e)
        remote = {"cpu": "N/A", "ram": "N/A", "swap": "N/A", "disk": "N/A"}

    return local, remote, err


# ----------------------------------------------------------------------
# Network quality
# ----------------------------------------------------------------------

def get_network_quality() -> dict:
    """Check packet loss and RX/TX stats on IPIP tunnel."""
    tunnel_peer = "10.0.0.1"
    ping_cmd = (
        f"ping -c 5 -W 2 {tunnel_peer} "
        f"| grep 'packet loss' | awk -F', ' '{{print $3}}'"
    )
    stats_cmd = (
        f"ip -s link show {IPIP_INTERFACE} "
        f"| awk 'NR==4 {{print $1}} NR==6 {{print $1}}'"
    )
    quality = {"loss": "N/A", "rx": "0", "tx": "0"}
    try:
        res = subprocess.run(
            ping_cmd, shell=True, capture_output=True, text=True, timeout=15,
        )
        if res.returncode == 0:
            quality["loss"] = res.stdout.strip()

        res2 = subprocess.run(
            stats_cmd, shell=True, capture_output=True, text=True, timeout=5,
        )
        stats = res2.stdout.strip().split("\n")
        if len(stats) >= 2:
            quality["rx"] = stats[0]
            quality["tx"] = stats[1]
    except Exception as e:
        logger.error("Network quality check failed: %s", e)

    return quality


# ----------------------------------------------------------------------
# Fix operations (via SSH on Moldova)
# ----------------------------------------------------------------------

def fix_awg_interface() -> bool:
    """Restart AWG on Moldova via SSH."""
    try:
        stdout, stderr = _ssh(
            f"sudo systemctl restart {AWG_SERVICE}", timeout=30
        )
        if stderr and "error" in stderr.lower():
            logger.error("AWG restart error: %s", stderr)
            return False
        logger.info("AWG restarted successfully")
        return True
    except Exception as e:
        logger.error("AWG fix failed: %s", e)
        return False


def fix_ipip_bridge() -> bool:
    """
    Reset IPIP tunnel on Bulgaria (local container).
    Requires privileged: true in docker-compose.
    """
    try:
        subprocess.run(
            ["ip", "link", "set", IPIP_INTERFACE, "down"], check=True
        )
        subprocess.run(
            ["ip", "link", "set", IPIP_INTERFACE, "up"], check=True
        )
        logger.info("IPIP bridge reset successfully")
        return True
    except Exception as e:
        logger.error("IPIP fix failed: %s", e)
        return False


def get_logs(lines: int = 50) -> dict:
    """Fetch recent logs from Moldova via SSH."""
    services = {
        "awg": f"sudo journalctl -u awg-quick@{AWG_INTERFACE} -n {lines} --no-pager --output short-iso ",
        "sshd": f"sudo journalctl -u ssh -n {lines} --no-pager --output short-iso ",
        "fail2ban": f"sudo journalctl -u fail2ban -n {lines} --no-pager --output short-iso ",
    }
    result = {}
    for name, cmd in services.items():
        stdout, stderr = _ssh(cmd)
        result[name] = stdout if stdout else f"No entries: {stderr}"
    return result
