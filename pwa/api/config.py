"""
api/config.py — Client config endpoints.

GET    /api/client/config            — .conf text for the newest device
GET    /api/client/config/raw        — the same, as a downloadable file
GET    /api/client/configs           — every device on the account
POST   /api/client/configs           — add a device, up to the plan's limit
GET    /api/client/configs/{id}/raw  — one device's .conf as a file
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
    active_configs,
    get_client_config,
    issue_config,
    render_config,
)
from services.subscriptions import has_active_subscription

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
    if not has_active_subscription(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    conf = await get_client_config(user, db)
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
    if not has_active_subscription(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    conf = await get_client_config(user, db)
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


class NewConfigRequest(BaseModel):
    # Short on purpose. The Android client refuses .conf filenames longer than
    # five or six characters, and this name is what the download is called.
    name: str = Field(default="device", min_length=1, max_length=6)


def _describe(config: Config) -> dict:
    return {
        "id": config.id,
        "name": config.name,
        "peer_ip": config.peer_ip,
        "created_at": config.created_at,
    }


@router.get("/api/client/configs")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    user = await _current_user(db, payload)
    if not has_active_subscription(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    configs = await active_configs(user, db)
    limit = config_limit(user.plan)
    return {
        "ok": True,
        "plan": user.plan,
        "limit": limit,
        "used": len(configs),
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
    if not has_active_subscription(user):
        raise HTTPException(status_code=402, detail="No active subscription")

    configs = await active_configs(user, db)
    limit = config_limit(user.plan)
    if len(configs) >= limit:
        raise HTTPException(
            status_code=409,
            detail=f"Plan allows {limit} device(s); remove one first",
        )

    config = await issue_config(user, db, name=req.name)
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
    if not has_active_subscription(user):
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

    return PlainTextResponse(
        content=render_config(config),
        headers={"Content-Disposition": f"attachment; filename={config.name}.conf"},
    )


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

    ok, reason = await asyncio.get_event_loop().run_in_executor(
        None, _remove_peer_from_bridge, config.public_key
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
