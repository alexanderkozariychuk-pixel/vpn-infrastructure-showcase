from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User, Payment
from auth.jwt import hash_password, require_auth
from services.mailer import send_email, welcome_email
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    lang: str = "ru"


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


@router.post("/api/client/register", response_model=UserResponse, status_code=201)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Username '{req.username}' already exists")
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Email already registered")
    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # send welcome email (best-effort — never blocks registration)
    try:
        subject, html, text = welcome_email(user.username, req.lang)
        send_email(user.email, subject, html, text)
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
    _: dict = Depends(require_auth),
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
    _: dict = Depends(require_auth),
):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{req.username}' not found")
    user.peer_ip = req.peer_ip
    user.is_subscribed = True
    await db.commit()
    return {"ok": True, "username": user.username, "peer_ip": user.peer_ip}


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
        "is_subscribed": user.is_subscribed,
        "peer_ip": user.peer_ip,
        "subscribed_until": user.subscribed_until,
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
                "currency": p.currency,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "paid_at": p.paid_at.isoformat() if p.paid_at else None,
            }
            for p in rows
        ],
    }
