from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User
from auth.jwt import hash_password, require_auth

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


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
