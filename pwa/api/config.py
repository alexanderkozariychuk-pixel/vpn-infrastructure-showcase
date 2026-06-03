"""
api/config.py — Client config endpoints.

GET  /api/client/config      — returns .conf text for the authenticated client
GET  /api/client/config/raw  — returns raw .conf as downloadable file
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User
from auth.jwt import require_auth
from services.provisioner import get_client_config

router = APIRouter()


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
    if not user.is_subscribed:
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
    if not user.is_subscribed:
        raise HTTPException(status_code=402, detail="No active subscription")

    conf = await get_client_config(user, db)
    if not conf:
        raise HTTPException(status_code=404, detail="Config not found")

    return PlainTextResponse(
        content=conf,
        headers={"Content-Disposition": f"attachment; filename=sovereign-{username}.conf"}
    )
