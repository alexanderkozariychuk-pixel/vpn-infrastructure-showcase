"""
api/password_reset.py — forgot/reset password flow.

Security notes:
- /forgot always returns the same response whether or not the email exists
  (prevents email enumeration).
- Reset tokens are cryptographically random (secrets.token_urlsafe), single-use,
  and expire after 1 hour.
- New password is re-hashed with the same argon2 context as registration.
"""
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.base import get_db
from db.models import User
from auth.jwt import hash_password
from services.mailer import send_email, password_reset_email

logger = logging.getLogger(__name__)
router = APIRouter()

RESET_TOKEN_TTL_HOURS = 1
PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://sov3r3ign.com")


class ForgotRequest(BaseModel):
    email: EmailStr
    lang: str = "ru"


class ResetRequest(BaseModel):
    token: str
    new_password: str


@router.post("/api/auth/forgot")
async def forgot_password(
    req: ForgotRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a reset token and email a reset link.
    Always returns success — never reveals whether the email is registered.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)
        await db.commit()

        reset_url = f"{PORTAL_BASE_URL}/reset?token={token}"
        try:
            subject, html, text = password_reset_email(reset_url, req.lang)
            await send_email(user.email, subject, html, text)
        except Exception as e:
            logger.error("Reset email failed for %s: %s", user.email, e)

    # identical response regardless of whether the user exists
    return {"ok": True, "message": "If that email is registered, a reset link has been sent."}


@router.post("/api/auth/reset")
async def reset_password(
    req: ResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate the reset token and set a new password.
    """
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    result = await db.execute(select(User).where(User.reset_token == req.token))
    user = result.scalar_one_or_none()

    if not user or not user.reset_expires:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    # normalize expiry to timezone-aware for comparison
    expires = user.reset_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > expires:
        # clear the stale token
        user.reset_token = None
        user.reset_expires = None
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    # set new password, invalidate token (single-use)
    user.password_hash = hash_password(req.new_password)
    user.reset_token = None
    user.reset_expires = None
    await db.commit()

    logger.info("Password reset completed for user %s", user.username)
    return {"ok": True, "message": "Password updated successfully"}
