"""
api/clients.py — the admin's list of peers on the entry node.

Each peer is named from what we know about it:

    portal    issued by the portal: "<username> · <device>", from configs
    trial     the same, for a trial device
    manual    not from the portal, named by the operator (peer_labels)
    unknown   on the node and nowhere else — the first 12 characters of its key

"unknown" is the list to work through when moving customers to the portal:
each such peer is either labelled (it is someone's) or removed.
"""
import asyncio
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_admin
from db.base import get_db
from db.models import Config, PeerLabel, User
from services.net_manager import get_bridge_status_data

router = APIRouter()
executor = ThreadPoolExecutor()


async def run_sync(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)


async def _known(db: AsyncSession) -> tuple[dict, dict]:
    """(portal configs by public key, operator labels by public key)."""
    rows = (await db.execute(
        select(Config.public_key, Config.name, Config.kind, Config.is_active, User.username)
        .join(User, User.id == Config.user_id)
    )).all()
    configs = {}
    for pk, name, kind, active, username in rows:
        # A key reissued after a revoke cannot happen (keys are generated per
        # config), but prefer the active row if it ever does.
        if pk not in configs or active:
            configs[pk] = {"name": f"{username} · {name}", "kind": kind}
    labels = dict((await db.execute(select(PeerLabel.public_key, PeerLabel.label))).all())
    return configs, labels


def _describe(peer, configs: dict, labels: dict) -> dict:
    key = peer.public_key
    if key in configs:
        c = configs[key]
        name, source = c["name"], ("trial" if c["kind"] == "trial" else "portal")
    elif key in labels:
        name, source = labels[key], "manual"
    else:
        name, source = key[:12], "unknown"
    return {
        "name": name,
        "source": source,
        "key": key,
        "public_key": key[:12] + "...",
        "status": _classify_handshake(peer.handshake),
        "handshake": peer.handshake,
        "transfer": peer.transfer,
        "endpoint": peer.endpoint,
    }


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

    configs, labels = await _known(db)
    clients = [_describe(p, configs, labels) for p in (peers or [])]

    order = {"active": 0, "idle": 1, "inactive": 2}
    clients.sort(key=lambda c: (order[c["status"]], c["name"].lower()))

    def count(field, value):
        return sum(1 for c in clients if c[field] == value)

    return {
        "ok": True,
        "total": len(clients),
        "active": count("status", "active"),
        "idle": count("status", "idle"),
        "inactive": count("status", "inactive"),
        "sources": {s: count("source", s) for s in ("portal", "trial", "manual", "unknown")},
        "clients": clients,
    }


@router.get("/api/clients/{name}")
async def get_client(name: str, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    peers, err = await run_sync(get_bridge_status_data)
    if err:
        return {"ok": False, "error": err}

    configs, labels = await _known(db)
    for peer in (peers or []):
        c = _describe(peer, configs, labels)
        if c["name"] == name:
            return {"ok": True, **c}

    return {"ok": False, "error": f"Client '{name}' not found"}


class LabelRequest(BaseModel):
    public_key: str
    label: str = Field(max_length=60)


def _valid_key(key: str) -> bool:
    try:
        return len(base64.b64decode(key, validate=True)) == 32
    except (binascii.Error, ValueError):
        return False


@router.post("/api/admin/peer-label")
async def set_label(req: LabelRequest, _: dict = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Name a peer the portal did not issue. An empty label removes the name."""
    key, label = req.public_key.strip(), req.label.strip()
    if not _valid_key(key):
        raise HTTPException(status_code=422, detail="Not a public key")
    if (await db.execute(select(Config.id).where(Config.public_key == key))).first():
        raise HTTPException(status_code=409, detail="This peer belongs to a portal account")
    row = await db.get(PeerLabel, key)
    if not label:
        if row:
            await db.delete(row)
            await db.commit()
        return {"ok": True, "label": None}
    if row:
        row.label = label
    else:
        db.add(PeerLabel(public_key=key, label=label))
    await db.commit()
    return {"ok": True, "label": label}
