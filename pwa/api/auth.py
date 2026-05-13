import os
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from auth.jwt import verify_password, create_token, hash_password

router = APIRouter()

# Один admin пользователь — из env переменных
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv(
    "ADMIN_PASSWORD_HASH",
    hash_password(os.getenv("ADMIN_PASSWORD", "changeme"))
)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/api/auth/token", response_model=TokenResponse)
async def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not verify_password(req.password, ADMIN_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_token({"sub": req.username})
    return TokenResponse(access_token=token)


@router.get("/api/auth/verify")
async def verify(payload: dict = __import__('fastapi').Depends(
    __import__('auth.jwt', fromlist=['require_auth']).require_auth
)):
    return {"ok": True, "user": payload.get("sub")}
