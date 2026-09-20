"""
services/provisioner.py — issuing and activating AWG peers.

Issuing a device:
  1. Generate AWG keypair + PSK
  2. Find the next free address in the client pool
  3. Add the peer to Bridge awg0 through the pwa-add-peer wrapper
  4. Save a Config row (private key and PSK encrypted with Fernet)

Activating a payment extends `subscribed_until` from whichever is later — now
or the end of the period already paid for — and issues a device only on a first
purchase. The two are separate on purpose: a renewal is not a request for
another peer, which is what a repeat purchase used to produce.
"""
import asyncio
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
from config import plan_info

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

# One address pool for every client, regardless of plan.
#
# Splitting the subnet per plan made sense when a subscription meant exactly
# one peer. With tiers that allow several devices, the tier no longer predicts
# how many addresses a customer consumes, and a per-plan range would run out
# while the neighbouring one sat empty. Addresses below .42 are the hand-issued
# peers that predate the portal; the node's own list is what is actually
# checked, so they are excluded whether or not they appear in this database.
CLIENT_POOL = ("10.88.88", 42, 199)

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

async def _find_free_ip(db: AsyncSession, exclude: set[str] | None = None) -> str | None:
    """Return the next free address in the client pool."""
    prefix, start, end = CLIENT_POOL
    # Only active rows hold an address. A revoked config's peer is off the node,
    # so keeping its address reserved would leak the pool one expiry at a time.
    # The node's own list arrives separately in `exclude` and remains the
    # authority — this query is the mirror, and the mirror can be stale.
    result = await db.execute(select(Config.peer_ip).where(Config.is_active.is_(True)))
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


# ── remove peer from Bridge ───────────────────────────────────────────

def _remove_peer_from_bridge(pub: str) -> tuple[bool, str]:
    """Remove a peer via the validated wrapper on the entry node.

    The wrapper (pwa-del-peer) re-checks the key format, refuses anything
    outside the client subnet — so the backbone peer is unreachable through
    this path — and removes the peer from the config file before the runtime,
    so a failed edit leaves a working tunnel rather than a silently returning
    peer.

    A peer that is already gone is reported as a failure by the wrapper, not
    silently swallowed: the caller decides whether that is expected.
    """
    import shlex
    stdout, stderr = _ssh_bridge(f"sudo pwa-del-peer {shlex.quote(pub)}")

    out = (stdout + " " + stderr).strip()
    if stdout.startswith("ok:"):
        logger.info("Peer removed from bridge: %s", pub[:12])
        return True, "ok"

    logger.error("pwa-del-peer refused peer %s: %s", pub[:12], out)
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

async def issue_config(user: User, db: AsyncSession, name: str = "device") -> Config | None:
    """
    Create one peer for a user: keys → free address → node → Config row.

    Deliberately does not touch the subscription. Issuing a device and paying
    for a plan are different events — a customer adding a second phone in the
    middle of a paid period is not making a payment, and a renewal is not a
    request for another device. Keeping them apart is what stopped a repeat
    purchase from silently handing out a second peer.

    The row is added to the session but not committed: the caller decides what
    else belongs in the same transaction.
    """
    try:
        priv = _awg_genkey()
        pub  = _awg_pubkey(priv)
        psk  = _awg_genpsk()
    except Exception as e:
        logger.error("Key generation failed: %s", e)
        return None

    client_name = f"auto-{user.username}"
    loop = asyncio.get_event_loop()

    # Seed from the node's live state, not from the local mirror.
    tried_ips: set[str] = await loop.run_in_executor(None, _bridge_used_ips)
    logger.info("Bridge reports %d addresses in use", len(tried_ips))

    peer_ip = None
    for _ in range(10):
        peer_ip = await _find_free_ip(db, exclude=tried_ips)
        if not peer_ip:
            logger.error("No free addresses left in the client pool")
            return None
        ok, reason = await loop.run_in_executor(
            None, _add_peer_to_bridge, pub, psk, peer_ip, client_name
        )
        if ok:
            break
        tried_ips.add(peer_ip)
        if "ip in use" not in reason:
            logger.error("Failed to add peer to Bridge for user %s: %s", user.username, reason)
            return None
        logger.warning("IP %s already in use on Bridge (stale local tracking) - retrying with next IP", peer_ip)
    else:
        logger.error("Exhausted retries finding a free IP for user %s", user.username)
        return None

    config = Config(
        user_id=user.id,
        name=name,
        peer_ip=peer_ip,
        private_key=_encrypt(priv),
        public_key=pub,
        preshared_key=_encrypt(psk),
        is_active=True,
    )
    db.add(config)
    logger.info("Issued config '%s' for %s → %s", name, user.username, peer_ip)
    return config


async def activate_payment(user: User, payment: Payment, db: AsyncSession) -> bool:
    """
    Turn a confirmed payment into subscription time.

    Extends from whichever is later — now, or the end of the period already
    paid for — so renewing early keeps the days that are left instead of
    throwing them away.

    A first purchase gets one config. A renewal gets none: the customer already
    has their devices, and issuing another peer per payment is how a repeat
    purchase used to leave an extra tunnel behind. Additional devices, up to
    the plan's limit, are requested from the portal.
    """
    info = plan_info(payment.plan)
    if not info:
        logger.error("Unknown plan %r on payment %s — not activating", payment.plan, payment.id)
        return False

    existing = (
        await db.execute(
            select(Config).where(Config.user_id == user.id, Config.is_active.is_(True))
        )
    ).scalars().all()

    if not existing:
        config = await issue_config(user, db, name="device-1")
        if config is None:
            # The payment is real; the peer is not. Leave the payment pending
            # so the failure stays visible and recovery is deliberate — marking
            # it paid here would hide a customer who owes nothing and has
            # nothing.
            logger.error("Provisioning failed for %s on payment %s", user.username, payment.id)
            return False
        user.peer_ip = config.peer_ip

    now = datetime.now(timezone.utc)
    base = max(now, user.subscribed_until or now)

    user.is_subscribed = True
    user.plan = payment.plan
    user.subscribed_until = base + timedelta(days=info["days"])
    payment.status = "paid"
    payment.paid_at = now

    await db.commit()
    logger.info(
        "Activated %s for %s until %s (%s)",
        payment.plan, user.username, user.subscribed_until.date(),
        "renewal" if existing else "first purchase",
    )
    return True


async def active_configs(user: User, db: AsyncSession) -> list[Config]:
    """Every config the user currently holds, newest first."""
    result = await db.execute(
        select(Config)
        .where(Config.user_id == user.id, Config.is_active.is_(True))
        .order_by(Config.created_at.desc())
    )
    return list(result.scalars().all())


def render_config(config: Config) -> str:
    """Decrypted .conf text for one config row."""
    return _build_conf(
        _decrypt(config.private_key),
        _decrypt(config.preshared_key),
        config.peer_ip,
    )


async def get_client_config(user: User, db: AsyncSession) -> str | None:
    """
    The user's most recent config, as .conf text.

    Kept for the single-config view in the portal. This used to call
    scalar_one_or_none on a query that can match several rows, which raises —
    so the first customer with two devices would have got a 500 rather than a
    config.
    """
    configs = await active_configs(user, db)
    return render_config(configs[0]) if configs else None
