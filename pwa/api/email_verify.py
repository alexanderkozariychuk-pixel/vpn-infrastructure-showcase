"""
api/email_verify.py — proving that a customer reads the address they gave.

A purchase needs a confirmed address (api/payment.py, _open_order): the
receipt, the reset link and any notice about the service go there, and an
address nobody reads — or someone else's — leaves the customer unreachable
and the letters landing in a stranger's inbox.

The link in the letter opens /verify, a page that posts the token here. The
token is never acted on by a plain GET: mail scanners and link previews fetch
every URL in a letter, and would otherwise confirm addresses nobody opened.

As with reset tokens, only a SHA-256 of the token is stored.
"""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_auth
from db.base import get_db
from db.models import User
from services import ratelimit
from services.mailer import send_email, verification_email
from services.net import resolve_source_ip

logger = logging.getLogger(__name__)
router = APIRouter()

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://sov3r3ign.com")
VERIFY_TOKEN_TTL = timedelta(hours=48)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(user: User) -> str:
    """Give `user` a fresh confirmation token; any earlier one stops working."""
    token = secrets.token_urlsafe(32)
    user.email_verify_token = _digest(token)
    user.email_verify_expires = datetime.now(timezone.utc) + VERIFY_TOKEN_TTL
    return token


def verify_url(token: str) -> str:
    return f"{PORTAL_BASE_URL}/verify?token={token}"


def mark_verified(user: User) -> None:
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(timezone.utc)
    user.email_verify_token = None
    user.email_verify_expires = None


class VerifyRequest(BaseModel):
    token: str = Field(max_length=128)


@router.post("/api/auth/verify-email")
async def verify_email(req: VerifyRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ratelimit.take(ratelimit.VERIFY_PER_IP, resolve_source_ip(request))

    result = await db.execute(select(User).where(User.email_verify_token == _digest(req.token)))
    user = result.scalar_one_or_none()
    if not user or not user.email_verify_expires:
        raise HTTPException(status_code=400, detail="Invalid or used confirmation link")

    expires = user.email_verify_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        raise HTTPException(status_code=400, detail="Confirmation link has expired")

    mark_verified(user)
    await db.commit()
    logger.info("Email confirmed for %s", user.username)
    return {"ok": True}


@router.post("/api/auth/resend-verification")
async def resend_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email_verified_at is not None:
        return {"ok": True, "already_verified": True}

    # Per account as well as per address: a signed-in script could otherwise
    # point this at one inbox from many networks.
    ratelimit.take(ratelimit.VERIFY_RESEND, user.id)
    ratelimit.take(ratelimit.VERIFY_RESEND_PER_IP, resolve_source_ip(request))

    token = issue_token(user)
    await db.commit()
    try:
        subject, html, text = verification_email(verify_url(token), user.lang or "ru")
        await send_email(user.email, subject, html, text)
    except Exception as e:
        logger.error("Confirmation email failed for %s: %s", user.email, e)
    return {"ok": True, "already_verified": False}
