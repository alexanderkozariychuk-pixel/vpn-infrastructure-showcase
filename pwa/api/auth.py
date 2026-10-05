import os
from fastapi import APIRouter, HTTPException, Request, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from db.base import get_db
from db.models import User
from auth.jwt import verify_password, create_token, hash_password, require_auth
from services import ratelimit
from services.net import resolve_source_ip

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
    # Caps, not rules: a megabyte "password" would otherwise be fed to argon2.
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "client"


@router.post("/api/auth/token", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = resolve_source_ip(request)
    fail_key = f"{ip}|{req.username.lower()}"
    ratelimit.take(ratelimit.LOGIN_PER_IP, ip)
    ratelimit.check(ratelimit.LOGIN_FAILS, fail_key)

    def refuse(code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"):
        ratelimit.LOGIN_FAILS.add(fail_key)
        return HTTPException(status_code=code, detail=detail)

    # Проверяем admin
    if req.username == ADMIN_USERNAME:
        if not verify_password(req.password, ADMIN_PASSWORD_HASH):
            raise refuse()
        token = create_token({"sub": req.username, "role": "admin"})
        return TokenResponse(access_token=token, role="admin")

    # Проверяем клиентов в БД. Usernames are unique regardless of case
    # (register.py), so a customer who types "Ivan" for "ivan" still gets in.
    result = await db.execute(
        select(User).where(func.lower(User.username) == req.username.lower())
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise refuse()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    # The token carries the stored spelling: everything downstream looks the
    # user up by `sub` exactly.
    token = create_token({"sub": user.username, "role": "client"})
    return TokenResponse(access_token=token, role="client")


@router.get("/api/auth/verify")
async def verify(payload: dict = Depends(require_auth)):
    return {"ok": True, "user": payload.get("sub"), "role": payload.get("role")}
