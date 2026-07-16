import os
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User
from auth.jwt import verify_password, create_token, hash_password, require_auth

router = APIRouter()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_admin_password = os.getenv("ADMIN_PASSWORD")
if not _admin_password:
    raise RuntimeError(
        "ADMIN_PASSWORD is not set — refusing to start rather than exposing "
        "admin/changeme on a public domain."
    )
ADMIN_PASSWORD_HASH = hash_password(_admin_password)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "client"


@router.post("/api/auth/token", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Проверяем admin
    if req.username == ADMIN_USERNAME:
        if not verify_password(req.password, ADMIN_PASSWORD_HASH):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_token({"sub": req.username, "role": "admin"})
        return TokenResponse(access_token=token, role="admin")

    # Проверяем клиентов в БД
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_token({"sub": req.username, "role": "client"})
    return TokenResponse(access_token=token, role="client")


@router.get("/api/auth/verify")
async def verify(payload: dict = Depends(require_auth)):
    return {"ok": True, "user": payload.get("sub"), "role": payload.get("role")}
