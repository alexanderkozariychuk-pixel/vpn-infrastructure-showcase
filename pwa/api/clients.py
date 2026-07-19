from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from concurrent.futures import ThreadPoolExecutor
import asyncio
from auth.jwt import require_auth
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


def _classify_handshake(handshake: str) -> str:
    if handshake == "never":
        return "inactive"
    if "second" in handshake or "minute" in handshake:
        return "active"
    if "hour" in handshake:
        hours = int(handshake.split()[0])
        return "active" if hours < 3 else "idle"
    return "idle"


@router.get("/api/clients")
async def get_clients(_: dict = Depends(require_auth), db: AsyncSession = Depends(get_db)):
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
async def get_client(name: str, _: dict = Depends(require_auth), db: AsyncSession = Depends(get_db)):
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
