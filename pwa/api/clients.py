from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from concurrent.futures import ThreadPoolExecutor
import asyncio
from auth.jwt import require_admin
from services.net_manager import get_bridge_status_data
from db.base import get_db
from db.models import Config

router = APIRouter()
executor = ThreadPoolExecutor()


async def run_sync(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)


async def _names_from_db(db: AsyncSession) -> dict:
    """Map public_key[:12] -> client name from our own DB. The PWA writes
    these rows at provisioning time, so there's no reason to SSH the node to
    re-read them — and reading the config over SSH is no longer permitted."""
    rows = (await db.execute(select(Config.public_key, Config.name))).all()
    return {pk[:12]: name for pk, name in rows}


_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}


def handshake_age(handshake: str) -> int | None:
    """
    Seconds since the last handshake, from `awg show`'s wording:
    "Now", "45 seconds ago", "1 day, 2 hours, 3 minutes, 4 seconds ago".
    None for "never" or anything unreadable.
    """
    text = handshake.strip().lower()
    if text == "now":
        return 0
    total, found = 0, False
    for part in text.removesuffix(" ago").split(","):
        bits = part.split()
        if len(bits) != 2 or not bits[0].isdigit():
            continue
        unit = _UNITS.get(bits[1].rstrip("s"))
        if unit:
            total += int(bits[0]) * unit
            found = True
    return total if found else None


def _classify_handshake(handshake: str) -> str:
    """
    active    handshake within 3 minutes — a live tunnel renews it every two
    idle      older than that: configured, not in use right now
    inactive  never connected

    The first version matched words: anything containing "second" or
    "minute" was active — which is every age, since `awg show` always ends
    in seconds ("3 days, … 4 seconds ago") — and "Now", which has neither,
    fell through to idle.
    """
    age = handshake_age(handshake)
    if age is None:
        return "inactive"
    return "active" if age <= 180 else "idle"


@router.get("/api/clients")
async def get_clients(_: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    peers, err = await run_sync(get_bridge_status_data)
    if err:
        return {"ok": False, "error": err}

    client_names = await _names_from_db(db)

    clients = []
    for peer in (peers or []):
        key_short = peer.public_key[:12]
        status = _classify_handshake(peer.handshake)
        clients.append({
            "name": client_names.get(key_short, key_short),
            "public_key": key_short + "...",
            "status": status,
            "handshake": peer.handshake,
            "transfer": peer.transfer,
            "endpoint": peer.endpoint,
        })

    order = {"active": 0, "idle": 1, "inactive": 2}
    clients.sort(key=lambda c: order[c["status"]])

    return {
        "ok": True,
        "total": len(clients),
        "active": sum(1 for c in clients if c["status"] == "active"),
        "idle": sum(1 for c in clients if c["status"] == "idle"),
        "inactive": sum(1 for c in clients if c["status"] == "inactive"),
        "clients": clients,
    }


@router.get("/api/clients/{name}")
async def get_client(name: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    peers, err = await run_sync(get_bridge_status_data)
    if err:
        return {"ok": False, "error": err}

    client_names = await _names_from_db(db)

    for peer in (peers or []):
        key_short = peer.public_key[:12]
        client_name = client_names.get(key_short, key_short)
        if client_name == name:
            return {
                "ok": True,
                "name": client_name,
                "public_key": key_short + "...",
                "status": _classify_handshake(peer.handshake),
                "handshake": peer.handshake,
                "transfer": peer.transfer,
                "endpoint": peer.endpoint,
            }

    return {"ok": False, "error": f"Client '{name}' not found"}
