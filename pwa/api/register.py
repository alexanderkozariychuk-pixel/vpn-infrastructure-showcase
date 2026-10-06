import asyncio
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from db.base import get_db
from db.models import User, Payment
from auth.jwt import hash_password, require_auth, require_admin
from services.mailer import send_email, welcome_email
from api.email_verify import issue_token, verify_url
from services.subscriptions import has_active_subscription
from services.trial import trial_state
from services import credit, ratelimit
from services.net import resolve_source_ip
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# The username becomes part of a peer name on the entry node: a paid device is
# issued as "auto-<username>", and pwa-add-peer accepts [A-Za-z0-9_-]{1,32}.
# Anything wider here registers fine, takes the money and then fails to get a
# device — so the rule is the wrapper's alphabet, and 27 = 32 - len("auto-").
# It also keeps markup out of the name before it is ever put in a letter.
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,27}$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128
# Names that would read as the operator. Compared without case.
RESERVED = {os.getenv("ADMIN_USERNAME", "admin").lower(), "admin", "root",
            "support", "sovereign", "sovrn"}


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    lang: str = "ru"
    # From a referral link (/?ref=CODE), kept by the page until registration.
    ref: str | None = Field(default=None, max_length=32)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        if not USERNAME_RE.fullmatch(v):
            raise ValueError("3-27 characters: Latin letters, digits, - and _")
        if v.lower() in RESERVED:
            raise ValueError("This username is reserved")
        return v

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        return v if v in ("ru", "en") else "ru"

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        # One mailbox, one account: "Ivan@x.ru" and "ivan@x.ru" are the same
        # inbox to every provider a customer is likely to use.
        return v.lower()


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    is_subscribed: bool
    peer_ip: str | None


class AssignPeerRequest(BaseModel):
    username: str
    peer_ip: str
    # Every subscription carries an end date. Granting one by hand without a
    # date used to produce a row the gate reads as permanent access; it now
    # reads as no access at all, so the default is an explicit month rather
    # than nothing.
    days: int = Field(default=30, ge=1, le=365)


@router.post("/api/client/register", response_model=UserResponse, status_code=201)
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ratelimit.take(ratelimit.REGISTER_PER_IP, resolve_source_ip(request))

    result = await db.execute(
        select(User).where(func.lower(User.username) == req.username.lower())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")
    result = await db.execute(select(User).where(func.lower(User.email) == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Email already registered")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        lang=req.lang,
    )
    token = issue_token(user)
    db.add(user)
    await db.flush()
    # A code that does not resolve (mistyped link, expired campaign) is
    # dropped without a word: registration is not the place to argue about it.
    if req.ref:
        promo, _ = await credit.resolve_code(db, req.ref, user)
        if promo is not None:
            user.referred_code = promo.code
    await db.commit()
    await db.refresh(user)

    # Welcome and confirmation in one letter (best-effort — never blocks
    # registration; a lost letter is re-sent from the portal).
    try:
        subject, html, text = welcome_email(user.username, verify_url(token), user.lang)
        await send_email(user.email, subject, html, text)
    except Exception as e:
        logger.error("Welcome email failed for %s: %s", user.email, e)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        is_subscribed=user.is_subscribed,
        peer_ip=user.peer_ip,
    )


@router.get("/api/client/list", response_model=list[UserResponse])
async def list_clients(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            is_active=u.is_active,
            is_subscribed=u.is_subscribed,
            peer_ip=u.peer_ip,
        )
        for u in users
    ]


@router.post("/api/admin/assign-peer")
async def assign_peer(
    req: AssignPeerRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{req.username}' not found")
    now = datetime.now(timezone.utc)
    base = max(now, user.subscribed_until or now)
    user.peer_ip = req.peer_ip
    user.is_subscribed = True
    user.subscribed_until = base + timedelta(days=req.days)
    await db.commit()
    return {
        "ok": True,
        "username": user.username,
        "peer_ip": user.peer_ip,
        "subscribed_until": user.subscribed_until,
    }


@router.get("/api/client/me")
async def get_me(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "ok": True,
        "username": user.username,
        "email": user.email,
        # Purchases need it; the portal shows a banner while it is false.
        "email_verified": user.email_verified_at is not None,
        "is_subscribed": user.is_subscribed,
        # The plan key ("basic-1m"). The portal read it all along and never
        # got it, so every customer's plan showed as "no subscription".
        "plan": user.plan,
        # The gate's own answer — flag *and* a paid period still ahead — so a
        # client does not have to re-derive it from the raw flag, which the
        # expiry sweep only clears some time after the date has passed.
        "active": has_active_subscription(user),
        "peer_ip": user.peer_ip,
        "subscribed_until": user.subscribed_until,
        # What the portal offers on "My config" when there is no paid period.
        "trial": {
            "state": trial_state(user, has_paid=user.subscribed_until is not None),
            "until": user.trial_until,
        },
    }


@router.get("/api/client/payments")
async def my_payments(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc())
    )
    rows = result.scalars().all()
    return {
        "ok": True,
        "payments": [
            {
                "plan": p.plan,
                "amount": p.amount,
                "granted": p.provider == "manual",
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in rows
        ],
    }
