"""
AmneziaWG management: parse state, manage peers, generate keys.
All subprocess calls are synchronous — run via asyncio.run_in_executor
from async handlers.
"""
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Optional

import aiohttp

from config import AWG_CONF_PATH, AWG_INTERFACE, AWG_SERVICE

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class Peer:
    public_key: str
    endpoint: str = "N/A"
    allowed_ips: str = ""
    handshake: str = "never"
    transfer: str = "0 B"
    keepalive: str = "off"


# ----------------------------------------------------------------------
# AWG state
# ----------------------------------------------------------------------

def parse_awg_show() -> tuple[list[Peer], Optional[str]]:
    """
    Run `awg show` and return a list of Peer objects.
    Returns (peers, None) on success, ([], error_message) on failure.
    """
    try:
        result = subprocess.run(
            ["sudo", "/usr/bin/awg", "show"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        return [], str(e)

    if result.returncode != 0:
        return [], result.stderr.strip()

    peers: list[Peer] = []
    current: dict = {}

    for line in result.stdout.splitlines():
        if line.startswith("peer:"):
            if current:
                peers.append(_dict_to_peer(current))
            current = {"public_key": line.split()[1]}
        elif ": " in line:
            key, _, value = line.partition(": ")
            key = key.strip()
            value = value.strip()
            _AWG_KEY_MAP.get(key, lambda d, v: None)(current, value)

    if current:
        peers.append(_dict_to_peer(current))

    return peers, None


_AWG_KEY_MAP = {
    "endpoint":           lambda d, v: d.update({"endpoint": v}),
    "allowed ips":        lambda d, v: d.update({"allowed_ips": v}),
    "latest handshake":   lambda d, v: d.update({"handshake": v}),
    "transfer":           lambda d, v: d.update({"transfer": v}),
    "persistent keepalive": lambda d, v: d.update({"keepalive": v}),
}


def _dict_to_peer(d: dict) -> Peer:
    return Peer(
        public_key=d.get("public_key", ""),
        endpoint=d.get("endpoint", "N/A"),
        allowed_ips=d.get("allowed_ips", ""),
        handshake=d.get("handshake", "never"),
        transfer=d.get("transfer", "0 B"),
        keepalive=d.get("keepalive", "off"),
    )


# ----------------------------------------------------------------------
# Server info
# ----------------------------------------------------------------------

def get_server_public_key() -> Optional[str]:
    """
    Read PrivateKey from awg0.conf and derive the public key.
    No shell=True — each command is a list.
    """
    try:
        cat = subprocess.run(
            ["sudo", "cat", AWG_CONF_PATH],
            capture_output=True, text=True, check=True,
        )
        priv_key = None
        for line in cat.stdout.splitlines():
            if line.strip().startswith("PrivateKey"):
                priv_key = line.split("=", 1)[1].strip()
                break

        if not priv_key:
            logger.error("PrivateKey not found in %s", AWG_CONF_PATH)
            return None

        pub = subprocess.run(
            ["wg", "pubkey"],
            input=priv_key,
            capture_output=True, text=True, check=True,
        )
        return pub.stdout.strip()

    except Exception as e:
        logger.error("get_server_public_key failed: %s", e)
        return None


async def get_server_public_ip() -> Optional[str]:
    """
    Fetch public IP via aiohttp (async, no subprocess).
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://ifconfig.me", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                return (await resp.text()).strip()
    except Exception as e:
        logger.error("get_server_public_ip failed: %s", e)
        return None


# ----------------------------------------------------------------------
# IP management
# ----------------------------------------------------------------------

def get_next_client_ip() -> Optional[str]:
    """
    Find the next free IP in CLIENT_SUBNET (10.66.66.0/24).
    Starts from .2 — .1 is the server.
    """
    peers, _ = parse_awg_show()
    used = set()
    for peer in peers:
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)/32", peer.allowed_ips)
        if match:
            used.add(match.group(1))

    for i in range(2, 255):
        ip = f"10.66.66.{i}"
        if ip not in used:
            return ip

    logger.error("No free IPs in 10.66.66.0/24")
    return None


# ----------------------------------------------------------------------
# Key generation
# ----------------------------------------------------------------------

def generate_keys() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Generate (private_key, public_key, preshared_key).
    Returns (None, None, None) on failure.
    """
    try:
        priv = subprocess.run(
            ["wg", "genkey"], capture_output=True, text=True, check=True,
        ).stdout.strip()

        pub = subprocess.run(
            ["wg", "pubkey"], input=priv,
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        psk = subprocess.run(
            ["wg", "genpsk"], capture_output=True, text=True, check=True,
        ).stdout.strip()

        return priv, pub, psk

    except Exception as e:
        logger.error("generate_keys failed: %s", e)
        return None, None, None


# ----------------------------------------------------------------------
# Peer management
# ----------------------------------------------------------------------

def add_peer_to_server(public_key: str, psk: str, allowed_ip: str) -> bool:
    """
    Append a new [Peer] block to awg0.conf.
    """
    last_octet = allowed_ip.split(".")[-1]
    peer_block = (
        f"\n[Peer]\n"
        f"PublicKey = {public_key}\n"
        f"PresharedKey = {psk}\n"
        f"AllowedIPs = {allowed_ip}/32,"
        f"fd42:42:42::{last_octet}/128\n"
    )
    try:
        subprocess.run(
            ["sudo", "tee", "-a", AWG_CONF_PATH],
            input=peer_block, text=True,
            capture_output=True, check=True,
        )
        return True
    except Exception as e:
        logger.error("add_peer_to_server failed: %s", e)
        return False


def remove_peer_from_server(public_key: str) -> bool:
    """
    Remove a [Peer] block from awg0.conf by public key.
    Writes atomically via a temp file + sudo cp.
    """
    try:
        cat = subprocess.run(
            ["sudo", "cat", AWG_CONF_PATH],
            capture_output=True, text=True, check=True,
        )
        new_content = _remove_peer_block(cat.stdout, public_key)

        # Write to temp file, then copy with sudo (atomic-ish)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as tmp:
            tmp.write(new_content)
            tmp_path = tmp.name

        subprocess.run(
            ["sudo", "cp", tmp_path, AWG_CONF_PATH],
            check=True,
        )
        return True

    except Exception as e:
        logger.error("remove_peer_from_server failed: %s", e)
        return False

    finally:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _remove_peer_block(content: str, public_key: str) -> str:
    """
    Parse conf content and return it without the matching [Peer] block.
    Preserves [Interface] section exactly.
    """
    lines = content.splitlines()
    result: list[str] = []
    current_block: list[str] = []
    in_peer = False

    for line in lines:
        if line.strip() == "[Peer]":
            # Flush previous peer block if it doesn't match
            if current_block:
                if public_key not in "\n".join(current_block):
                    result.extend(current_block)
                    result.append("")
            current_block = [line]
            in_peer = True
        elif in_peer:
            current_block.append(line)
        else:
            result.append(line)

    # Flush last block
    if current_block and public_key not in "\n".join(current_block):
        result.append("")
        result.extend(current_block)

    return "\n".join(result).strip() + "\n"


# ----------------------------------------------------------------------
# Service control
# ----------------------------------------------------------------------

def restart_wireguard() -> bool:
    """
    Restart the AWG systemd service.
    """
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", AWG_SERVICE],
            check=True, timeout=30,
        )
        return True
    except Exception as e:
        logger.error("restart_wireguard failed: %s", e)
        return False