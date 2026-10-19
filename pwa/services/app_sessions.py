"""
The Android app's long-lived sign-in (db.models.AppSession).

A refresh token is 256 random bits, handed to the app once at sign-in and
stored here only as its SHA-256. It does not rotate: a trade whose answer is
lost on a bad mobile network would otherwise cost the customer their
sign-in. What limits a stolen one is the password: a reset removes every
session of the account.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSession, User

APP_SESSION_DAYS = 90
# One account, a handful of phones; past this the oldest go. Keeps a script
# that signs in in a loop from growing the table without bound.
MAX_SESSIONS_PER_USER = 10


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt: datetime) -> datetime:
    # SQLite hands back naive datetimes; PostgreSQL does not.
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def open_session(db: AsyncSession, user: User) -> str:
    """A new refresh token for [user]. The caller commits."""
    now = datetime.now(timezone.utc)
    await db.execute(delete(AppSession).where(AppSession.user_id == user.id, AppSession.expires_at < now))
    rows = (await db.execute(
        select(AppSession.id).where(AppSession.user_id == user.id).order_by(AppSession.last_used_at.desc())
    )).scalars().all()
    stale = rows[MAX_SESSIONS_PER_USER - 1:]
    if stale:
        await db.execute(delete(AppSession).where(AppSession.id.in_(stale)))
    token = secrets.token_urlsafe(32)
    db.add(AppSession(user_id=user.id, token_hash=digest(token),
                      created_at=now, last_used_at=now, expires_at=now + timedelta(days=APP_SESSION_DAYS)))
    return token


async def use_session(db: AsyncSession, token: str) -> User | None:
    """
    The account behind a refresh token, its expiry moved ahead; None when the
    token is unknown, expired, or the account is disabled. The caller commits.
    """
    if not token or len(token) > 128:
        return None
    row = (await db.execute(select(AppSession).where(AppSession.token_hash == digest(token)))).scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    if _aware(row.expires_at) <= now:
        await db.delete(row)
        return None
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    row.last_used_at = now
    row.expires_at = now + timedelta(days=APP_SESSION_DAYS)
    return user


async def close_session(db: AsyncSession, token: str) -> None:
    if token and len(token) <= 128:
        await db.execute(delete(AppSession).where(AppSession.token_hash == digest(token)))


async def close_all(db: AsyncSession, user: User) -> None:
    """Every app signed in to [user]: after a password reset."""
    await db.execute(delete(AppSession).where(AppSession.user_id == user.id))
