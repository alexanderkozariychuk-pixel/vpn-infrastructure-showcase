"""
AIKVPN Network Manager: Focus on IPIP and AWG interface health.
"""
import logging
import subprocess
from dataclasses import dataclass
from typing import Optional

from config import AWG_SERVICE, AWG_INTERFACE

logger = logging.getLogger(__name__)

@dataclass
class PeerStatus:
    public_key: str
    endpoint: str = "N/A"
    handshake: str = "never"
    transfer: str = "0 B"

def get_amnezia_status():
    # Данные берем из окружения или прописываем вручную для теста
    MOLDOVA_IP = "45.140.146.134" 
    MOLDOVA_USER = "alex"

    # Команда для выполнения через SSH
    # -o StrictHostKeyChecking=no чтобы бот не завис на вопросе "доверять ли серверу"
    ssh_command = [
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{MOLDOVA_USER}@{MOLDOVA_IP}",
        "sudo /usr/bin/awg show"
    ]

    try:
        result = subprocess.run(ssh_command, capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout
        return f"⚠️ Ошибка Молдовы: {result.stderr}"
    except Exception as e:
        return f"❌ Ошибка подключения: {str(e)}"

# --- Инфраструктурные фиксы ---

def fix_ipip_bridge() -> bool:
    """Reset IPIP tunnel between Moldova and Bulgaria."""
    try:
        subprocess.run(["sudo", "ip", "link", "set", "ipip0", "down"], check=True)
        subprocess.run(["sudo", "ip", "link", "set", "ipip0", "up"], check=True)
        logger.info("IPIP bridge reset successful")
        return True
    except Exception as e:
        logger.error(f"IPIP reset failed: {e}")
        return False

def fix_awg_interface() -> bool:
    """Soft restart of AWG interface."""
    try:
        subprocess.run(["sudo", "awg-quick", "down", AWG_INTERFACE], check=True)
        subprocess.run(["sudo", "awg-quick", "up", AWG_INTERFACE], check=True)
        logger.info("AWG interface reset successful")
        return True
    except Exception as e:
        logger.error(f"AWG reset failed: {e}")
        return False

def restart_full_service() -> bool:
    """Hard restart via systemd."""
    try:
        subprocess.run(["sudo", "systemctl", "restart", AWG_SERVICE], check=True)
        return True
    except Exception as e:
        logger.error(f"Full restart failed: {e}")
        return False