import asyncio
"""
services/provisioner.py — Auto-provisioning of AWG peers after payment.

Flow (Basic plan):
  1. Generate AWG keypair + PSK
  2. Find next free IP in the Basic pool (10.88.88.42–10.88.88.99)
  3. Add peer to Bridge awg0 via SSH (awg set)
  4. Save Config row to DB (private key encrypted with Fernet)
  5. Mark user as subscribed
"""
import os
import base64
import subprocess
import logging
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import User, Config, Payment

logger = logging.getLogger(__name__)

BRIDGE_USER = os.getenv("BRIDGE_USER", "vpnadmin")
BRIDGE_IP   = os.getenv("BRIDGE_IP", "")
BRIDGE_AWG  = os.getenv("BRIDGE_AWG_INTERFACE", "awg0")
BRIDGE_PUB  = os.getenv("BRIDGE_PUBLIC_KEY", "kCq1FK/tYvvB68h9luTRX5PAV0a2pIn2klbyNUKRMm0=")
BRIDGE_ENDPOINT = os.getenv("BRIDGE_ENDPOINT", "")

# Obfuscation params matching Bridge awg0
AWG_PARAMS = {
    "Jc": "3", "Jmin": "50", "Jmax": "1000",
    "S1": "72", "S2": "146",
    "H1": "1163059398", "H2": "1787455160",
    "H3": "970047041",  "H4": "133143559",
}

# IP pools per plan
POOLS = {
    "Basic":  ("10.88.88", 42, 99),   # 10.88.88.42 – 10.88.88.99
    "Family": ("10.88.88", 100, 149), # reserved for future
}

# Fernet key for encrypting private keys in DB
_fernet_key = os.getenv("FERNET_KEY")
if not _fernet_key:
    raise RuntimeError(
        "FERNET_KEY is not set — refusing to start. Without it, client private "
        "keys and PSKs would be written to the database in plaintext, silently."
    )
_fernet = Fernet(_fernet_key.encode())


# ── helpers ────────────────────────────────────────────────────────────

# WireGuard keys are plain X25519 pairs (32 raw bytes, base64) and the PSK is
# 32 random bytes. Generating them in-process instead of shelling out to `awg`
# keeps the image self-contained: no amneziawg-tools, no PPA at build time, and
# no silent dependency on whatever the host happens to have installed — which
# is exactly what broke when this container moved off the VPN node.
# Verified byte-identical against `awg pubkey`.
def _awg_genkey() -> str:
    key = X25519PrivateKey.generate()
    return base64.b64encode(
        key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    ).decode()


def _awg_pubkey(priv: str) -> str:
    key = X25519PrivateKey.from_private_bytes(base64.b64decode(priv))
    return base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()


def _awg_genpsk() -> str:
    return base64.b64encode(os.urandom(32)).decode()


# Reaches the entry node as the restricted pwa-provisioner user with a
# dedicated key. The only write it can perform is the validated pwa-add-peer
# wrapper — no `awg set`, no `tee`, no arbitrary sudo.
PWA_SSH_KEY = os.getenv("PWA_SSH_KEY", "/root/.ssh/pwa-provisioner")
PWA_SSH_USER = "pwa-provisioner"


def _ssh_bridge(cmd: str, timeout: int = 15) -> tuple[str, str]:
    result = subprocess.run(
        ["ssh",
         "-i", PWA_SSH_KEY,
          "-o", "StrictHostKeyChecking=yes",
         "-o", "UserKnownHostsFile=/root/.ssh/known_hosts",
         "-o", "ConnectTimeout=5",
         f"{PWA_SSH_USER}@{BRIDGE_IP}",
         cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return result.stdout.strip(), result.stderr.strip()

def _bridge_used_ips() -> set[str]:
    """
    Addresses currently assigned on the entry node.

    The local Config table is a mirror, not the source of truth: it can be
    empty after a fresh migration, or stale after manual peer work. Asking
    the node itself means the first candidate is already correct and the
    retry loop below stays a guard against races rather than the mechanism
    that finds the address.

    Returns an empty set on failure — the caller still has the retry loop
    and the wrapper's own duplicate-IP rejection behind it.
    """
    try:
        stdout, _ = _ssh_bridge("sudo pwa-awg-show")
    except Exception as e:
        logger.warning("Could not read peer list from bridge: %s", e)
        return set()

    used: set[str] = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("allowed ips:"):
            for part in line.split(":", 1)[1].split(","):
                addr = part.strip().split("/")[0]
                if addr:
                    used.add(addr)
    return used

def _encrypt(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()

def _decrypt(cipher: str) -> str:
    return _fernet.decrypt(cipher.encode()).decode()


# ── find free IP ───────────────────────────────────────────────────────

async def _find_free_ip(db: AsyncSession, plan: str, exclude: set[str] | None = None) -> str | None:
    """Return next available VPN IP for the given plan."""
    prefix, start, end = POOLS.get(plan, ("10.88.88", 42, 99))
    result = await db.execute(select(Config.peer_ip))
    used = {row[0] for row in result.fetchall() if row[0]}
    if exclude:
        used |= exclude
    for i in range(start, end + 1):
        candidate = f"{prefix}.{i}"
        if candidate not in used:
            return candidate
    return None


# ── add peer to Bridge ────────────────────────────────────────────────

def _add_peer_to_bridge(pub: str, psk: str, peer_ip: str, client_name: str) -> tuple[bool, str]:
    """Add a peer via the validated wrapper on the entry node.

    The wrapper (pwa-add-peer) re-validates every argument server-side —
    key format, that the IP is a /32 in the client subnet, no duplicate key
    or IP — then does both the runtime `awg set` and the config append
    atomically. We pass args positionally; the wrapper does the escaping.
    """
    # shlex-quote each arg so a hostile name/value can't break out of the
    # remote shell before the wrapper's own validation even runs.
    import shlex
    args = " ".join(shlex.quote(a) for a in (pub, psk, f"{peer_ip}/32", client_name))
    stdout, stderr = _ssh_bridge(f"sudo pwa-add-peer {args}")

    out = (stdout + " " + stderr).strip()
    if stdout.startswith("ok:"):
        logger.info("Peer added to bridge: %s (%s)", client_name, peer_ip)
        return True, "ok"

    # wrapper rejected it — surface why, don't retry blindly
    logger.error("pwa-add-peer refused peer %s (%s): %s", client_name, peer_ip, out)
    return False, out


# ── build client config text ──────────────────────────────────────────

def _build_conf(priv: str, psk: str, peer_ip: str) -> str:
    params = "\n".join(f"{k} = {v}" for k, v in AWG_PARAMS.items())
    return (
        f"[Interface]\n"
        f"PrivateKey = {priv}\n"
        f"Address = {peer_ip}/32\n"
        f"DNS = 1.1.1.1\n"
        f"MTU = 1300\n"
        f"{params}\n\n"
        f"[Peer]\n"
        f"PublicKey = {BRIDGE_PUB}\n"
        f"PresharedKey = {psk}\n"
        f"Endpoint = {BRIDGE_ENDPOINT}\n"
        f"AllowedIPs = 0.0.0.0/0\n"
        f"PersistentKeepalive = 25\n"
    )


# ── main entry point ──────────────────────────────────────────────────

async def provision_basic(user: User, payment: Payment, db: AsyncSession) -> bool:
    """
    Full auto-provisioning for Basic plan:
      generate keys → find free IP → add to Bridge → save Config → activate user.
    Returns True on success.
    """
    try:
        priv = _awg_genkey()
        pub  = _awg_pubkey(priv)
        psk  = _awg_genpsk()
    except Exception as e:
        logger.error("Key generation failed: %s", e)
        return False

    client_name = f"auto-{user.username}"
    loop = asyncio.get_event_loop()

    # Seed from the node's live state, not from the local mirror.
    tried_ips: set[str] = await loop.run_in_executor(None, _bridge_used_ips)
    logger.info("Bridge reports %d addresses in use", len(tried_ips))

    peer_ip = None
    peer_ip = None
    for attempt in range(10):
        peer_ip = await _find_free_ip(db, "Basic", exclude=tried_ips)
        if not peer_ip:
            logger.error("No free IPs in Basic pool")
            return False
        ok, reason = await loop.run_in_executor(None, _add_peer_to_bridge, pub, psk, peer_ip, client_name)
        if ok:
            break
        tried_ips.add(peer_ip)
        if "ip in use" not in reason:
            logger.error("Failed to add peer to Bridge for user %s: %s", user.username, reason)
            return False
        logger.warning("IP %s already in use on Bridge (stale local tracking) - retrying with next IP", peer_ip)
    else:
        logger.error("Exhausted retries finding a free IP for user %s", user.username)
        return False

    # save Config to DB
    conf_text = _build_conf(priv, psk, peer_ip)
    config = Config(
        user_id=user.id,
        name="Basic",
        peer_ip=peer_ip,
        private_key=_encrypt(priv),
        public_key=pub,
        preshared_key=_encrypt(psk),
        is_active=True,
    )
    db.add(config)

    # activate subscription
    now = datetime.now(timezone.utc)
    user.is_subscribed = True
    user.plan = "Basic"
    user.peer_ip = peer_ip
    user.subscribed_until = now + timedelta(days=30)
    payment.status = "paid"
    payment.paid_at = now

    await db.commit()
    logger.info("Provisioned Basic for user %s → %s", user.username, peer_ip)
    return True


async def get_client_config(user: User, db: AsyncSession) -> str | None:
    """Return decrypted .conf text for the user's active config."""
    result = await db.execute(
        select(Config)
        .where(Config.user_id == user.id, Config.is_active == True)
        .order_by(Config.created_at.desc())
    )
    config = result.scalar_one_or_none()
    if not config:
        return None
    priv = _decrypt(config.private_key)
    psk  = _decrypt(config.preshared_key)
    return _build_conf(priv, psk, config.peer_ip)
