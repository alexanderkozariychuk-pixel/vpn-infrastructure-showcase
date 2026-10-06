"""
api/notifications.py — the bell.

    GET  /api/client/notifications              the latest messages + unread count
    POST /api/client/notifications/read         mark read: {"ids": [...]} or {} for all
    POST /api/admin/notifications/broadcast     {"title", "body"} to every active account

What produces the messages, and which of them also go by email, is in
services/notify.py. Each customer sees only their own feed: every query here
is filtered by the user from the token, never by an id from the request.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_admin, require_auth
from db.base import get_db
from db.models import Notification, User
from services import notify

router = APIRouter()

FEED_SIZE = 30


async def _user(db: AsyncSession, payload: dict) -> User:
    user = (await db.execute(select(User).where(User.username == payload.get("sub")))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/api/client/notifications")
async def list_notifications(db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    user = await _user(db, payload)
    rows = (await db.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(FEED_SIZE)
    )).scalars().all()
    unread = (await db.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )).scalar_one()
    return {"items": [notify.describe(n) for n in rows], "unread": unread}


class ReadRequest(BaseModel):
    ids: list[str] | None = Field(default=None, max_length=100)


@router.post("/api/client/notifications/read")
async def mark_read(body: ReadRequest, db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    user = await _user(db, payload)
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if body.ids is not None:
        q = q.where(Notification.id.in_(body.ids))
    result = await db.execute(q.values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"marked": result.rowcount}


class BroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1000)


@router.post("/api/admin/notifications/broadcast")
async def broadcast(body: BroadcastRequest, db: AsyncSession = Depends(get_db), _: dict = Depends(require_admin)):
    title, text = body.title.strip(), body.body.strip()
    if not title or not text:
        raise HTTPException(status_code=422, detail="Title and text are required")
    sent = await notify.broadcast(db, title, text)
    return {"sent": sent}
