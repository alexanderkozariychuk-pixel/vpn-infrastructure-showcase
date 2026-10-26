"""
api/config.py — Client config endpoints.

GET    /api/client/config            — .conf text for the newest device
GET    /api/client/config/raw        — the same, as a downloadable file
GET    /api/client/configs           — every device on the account, and each location's slots
POST   /api/client/configs           — add a device in a location, up to the plan's limit there
GET    /api/client/configs/{id}/raw  — one device's .conf as a file
PATCH  /api/client/configs/{id}      — rename a device
DELETE /api/client/configs/{id}      — remove a device and free the slot
"""
import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import Config, User
from auth.jwt import require_auth
from config import config_limit
from services.provisioner import (
    _remove_peer_from_bridge,
    remove_peer_for,
    active_configs,
    get_client_config,
    issue_config,
    render_config,
)
from services.subscriptions import has_access, has_active_subscription
from services import locations

logger = logging.getLogger(__name__)
router = APIRouter()


async def _current_user(db: AsyncSession, payload: dict) -> User:
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/api/client/config")
async def client_config(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not has_access(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    try:
        conf = await get_client_config(user, db)
    except ValueError:
        raise HTTPException(status_code=503, detail="Location unavailable")
    if not conf:
        raise HTTPException(status_code=404, detail="Config not found")

    return {"ok": True, "config": conf, "peer_ip": user.peer_ip, "plan": user.plan}


@router.get("/api/client/config/raw", response_class=PlainTextResponse)
async def client_config_raw(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Returns the .conf file as plain text for direct download."""
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not has_access(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    try:
        conf = await get_client_config(user, db)
    except ValueError:
        raise HTTPException(status_code=503, detail="Location unavailable")
    if not conf:
        raise HTTPException(status_code=404, detail="Config not found")

    return PlainTextResponse(
        content=conf,
        headers={"Content-Disposition": f"attachment; filename=sovereign-{username}.conf"}
    )


# ── devices ──────────────────────────────────────────────────────────────────
#
# A plan buys a number of devices, not one tunnel. Everything below enforces
# that number server-side: the limit comes from the plan on the account, never
# from the request.
#
# Since the second location (services/locations.py) the plan's number holds in
# each location separately: a Basic plan is two devices in Germany and two in
# the Netherlands. The locations are independent chains, and a customer whose
# one stops working is meant to have the other ready, not to choose between
# them inside one allowance.


class NewConfigRequest(BaseModel):
    # Short on purpose. The Android client refuses .conf filenames longer than
    # five or six characters, and this name is what the download is called.
    name: str = Field(default="device", min_length=1, max_length=6)
    # Germany when not given: the Android app predates locations.
    location: str = Field(default=locations.DEFAULT, max_length=8)


class RenameConfigRequest(BaseModel):
    # Same bound as a new device's name: it is the download's filename.
    name: str = Field(min_length=1, max_length=6)


def _describe(config: Config) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "peer_ip": config.peer_ip,
        "created_at": config.created_at,
        "kind": config.kind,
        "location": config.location or locations.DEFAULT,
    }


def _location_slots(configs: list[Config], limit: int) -> list[dict]:
    """Each configured location, recommended first, with its own count."""
    rec = locations.recommended()
    return [
        {
            "key": loc.key,
            "limit": limit,
            "used": sum(1 for c in configs if (c.location or locations.DEFAULT) == loc.key),
            "recommended": loc.key == rec and len(locations.keys()) > 1,
        }
        for loc in locations.all_locations()
    ]


@router.get("/api/client/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    user = await _current_user(db, payload)
    if not has_access(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    configs = await active_configs(user, db)
    paid = has_active_subscription(user)
    # During a trial alone, the trial device is the whole allowance, in
    # Germany only (the trial net lives there).
    limit = config_limit(user.plan) if paid else 1
    slots = _location_slots(configs, limit) if paid else [
        {"key": locations.DEFAULT, "limit": 1, "used": len(configs), "recommended": False}
    ]
    return {
        "ok": True,
        "plan": user.plan,
        # `limit` and `used` are Germany's, as before locations: what the
        # Android app reads. `locations` is the full picture.
        "limit": limit,
        "used": sum(1 for c in configs if (c.location or locations.DEFAULT) == locations.DEFAULT),
        "locations": slots,
        "configs": [_describe(c) for c in configs],
    }


@router.post("/api/client/configs", status_code=201)
async def add_config(
    req: NewConfigRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Add a device, provided the plan has room for it."""
    user = await _current_user(db, payload)
    # Paid only. A trial is one device in the trial subnet; a device added
    # here would come from the paid pool, outside the trial's ceiling.
    if not has_active_subscription(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    if locations.get(req.location) is None:
        raise HTTPException(status_code=422, detail="Unknown location")

    configs = [
        c for c in await active_configs(user, db)
        if c.kind != "trial" and (c.location or locations.DEFAULT) == req.location
    ]
    limit = config_limit(user.plan)
    if len(configs) >= limit:
        raise HTTPException(
            status_code=409,
            detail=f"Plan allows {limit} device(s) in this location; remove one first",
        )

    config = await issue_config(user, db, name=req.name, location=req.location)
    if config is None:
        # The node refused or the pool is exhausted. Nothing was written, and
        # the customer is told plainly rather than being handed a config row
        # with no peer behind it.
        raise HTTPException(status_code=503, detail="Could not provision a device")

    await db.commit()
    return {"ok": True, "config": _describe(config), "used": len(configs) + 1, "limit": limit}


@router.get("/api/client/configs/{config_id}/raw", response_class=PlainTextResponse)
async def config_raw(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    user = await _current_user(db, payload)
    if not has_access(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    # Scoped to the caller: a config id from someone else's account must read
    # as missing, not as forbidden — and certainly not as a download.
    result = await db.execute(
        select(Config).where(
            Config.id == config_id,
            Config.user_id == user.id,
            Config.is_active.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    try:
        content = render_config(config)
    except ValueError:
        # The device's location is no longer configured on the portal.
        raise HTTPException(status_code=503, detail="Location unavailable")
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename={config.name}.conf"},
    )


@router.patch("/api/client/configs/{config_id}")
async def rename_config(
    config_id: str,
    req: RenameConfigRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """
    Rename a device. Only the label changes — keys, address and the peer on
    the node are untouched, so a working tunnel keeps working.

    The first device is issued automatically when a plan is bought, before the
    customer has had a chance to name it; this is how they do.
    """
    user = await _current_user(db, payload)
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is empty")

    # Scoped like the download: someone else's id reads as missing.
    result = await db.execute(
        select(Config).where(
            Config.id == config_id,
            Config.user_id == user.id,
            Config.is_active.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.name = name
    await db.commit()
    return {"ok": True, "config": _describe(config)}


@router.delete("/api/client/configs/{config_id}")
async def delete_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """
    Remove a device and free its slot.

    The row is only marked inactive once the node confirms the peer is gone.
    Freeing the slot on an unconfirmed removal would let a customer trade one
    working tunnel for another and keep both.
    """
    user = await _current_user(db, payload)

    result = await db.execute(
        select(Config).where(
            Config.id == config_id,
            Config.user_id == user.id,
            Config.is_active.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    if config.kind == "trial":
        # It cannot be replaced (adding is paid-only), so deleting it would
        # only end the trial early by mistake. It goes when the trial ends.
        raise HTTPException(status_code=409, detail="trial_device")

    ok, reason = await asyncio.get_event_loop().run_in_executor(
        None, remove_peer_for, config, _remove_peer_from_bridge
    )
    if not ok:
        logger.error("Could not remove peer %s for %s: %s", config.peer_ip, user.username, reason)
        raise HTTPException(status_code=503, detail="Could not remove the device")

    config.is_active = False
    if user.peer_ip == config.peer_ip:
        remaining = [c for c in await active_configs(user, db) if c.id != config.id]
        user.peer_ip = remaining[0].peer_ip if remaining else None
    await db.commit()

    return {"ok": True, "removed": config_id}


# ── a download link for the Telegram Mini App ───────────────────────────────
#
# Inside Telegram a page cannot save a file it built itself; Telegram's
# WebApp.downloadFile takes a URL and fetches it without our bearer token.
# So the account asks for a link that is good for one device and two minutes,
# signed with the portal's JWT secret; the file is the same as /raw.

DL_TTL = 120


def _dl_sig(config_id: str, exp: int) -> str:
    import hashlib
    import hmac
    from auth.jwt import SECRET_KEY
    return hmac.new(SECRET_KEY.encode(), f"dl:{config_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]


@router.post("/api/client/configs/{config_id}/download-link")
async def config_download_link(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    import time
    user = await _current_user(db, payload)
    if not has_access(user):
        raise HTTPException(status_code=402, detail="No active subscription")
    config = (await db.execute(select(Config).where(
        Config.id == config_id, Config.user_id == user.id, Config.is_active.is_(True)))).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    exp = int(time.time()) + DL_TTL
    token = f"{config.id}.{exp}.{_dl_sig(config.id, exp)}"
    return {"path": f"/api/public/dl/{token}/{config.name}.conf", "file_name": f"{config.name}.conf"}


@router.get("/api/public/dl/{token}/{filename}", response_class=PlainTextResponse)
async def config_download(token: str, filename: str, db: AsyncSession = Depends(get_db)):
    import hmac
    import time
    try:
        config_id, exp_s, sig = token.split(".")
        exp = int(exp_s)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if exp < time.time() or not hmac.compare_digest(sig, _dl_sig(config_id, exp)):
        raise HTTPException(status_code=404, detail="Not found")
    config = (await db.execute(select(Config).where(
        Config.id == config_id, Config.is_active.is_(True)))).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Not found")
    owner = await db.get(User, config.user_id)
    if owner is None or not has_access(owner):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        content = render_config(config)
    except ValueError:
        raise HTTPException(status_code=503, detail="Location unavailable")
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f"attachment; filename={config.name}.conf",
                 "Cache-Control": "no-store"},
    )
