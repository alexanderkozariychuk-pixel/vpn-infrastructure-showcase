"""
api/google_auth.py — "Sign in with Google" on the site.

The page shows Google's button (Google Identity Services); Google hands it an
ID token — a JWT signed by Google naming the Google account (`sub`) and its
confirmed address. The token comes here and is checked against Google's
published keys: signature, issuer, audience (our client ID), expiry, and a
confirmed address. Nothing else from Google is used or kept but `sub` and the
address.

  * a Google account already tied to an account: signed in;
  * a new one whose address belongs to an account with a CONFIRMED address:
    tied to it and signed in. An unconfirmed address is not enough — anyone
    can type someone else's address at registration, and tying the real owner's
    Google to that account would hand the owner's sign-in to whoever typed it;
  * a new address: the page asks for a username, and the account is created
    with the address already confirmed (Google confirmed it).

"Remember me" works as with a password: a refresh token when asked for.
"""
import logging
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from api.register import USERNAME_RE
from auth.jwt import create_token, hash_password
from db.base import get_db
from db.models import User
from services import app_sessions, credit, ratelimit
from services.net import resolve_source_ip

logger = logging.getLogger(__name__)
router = APIRouter()

CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_keys: dict = {"at": 0.0, "jwks": None}
KEYS_TTL = 6 * 3600  # Google rotates its keys over days; six hours is safe


async def _google_keys() -> dict:
    if _keys["jwks"] and time.time() - _keys["at"] < KEYS_TTL:
        return _keys["jwks"]
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(CERTS_URL)
        r.raise_for_status()
        _keys.update(jwks=r.json(), at=time.time())
    return _keys["jwks"]


async def verify_id_token(credential: str) -> dict | None:
    """The token's claims if Google signed it for us; None otherwise."""
    if not config.GOOGLE_CLIENT_ID or not credential or len(credential) > 4096:
        return None
    try:
        claims = jwt.decode(credential, await _google_keys(), algorithms=["RS256"],
                            audience=config.GOOGLE_CLIENT_ID, options={"verify_at_hash": False})
    except Exception as e:  # noqa: BLE001
        logger.info("google token refused: %s", e.__class__.__name__)
        return None
    if claims.get("iss") not in ISSUERS or not claims.get("sub"):
        return None
    if not claims.get("email") or claims.get("email_verified") not in (True, "true"):
        return None
    return claims


class GoogleIn(BaseModel):
    credential: str = Field(max_length=4096)
    remember: bool = False
    username: str | None = Field(default=None, max_length=27)
    ref: str | None = Field(default=None, max_length=64)


@router.get("/api/public/auth-options")
async def auth_options():
    return {"google_client_id": config.GOOGLE_CLIENT_ID or None}


async def _signed_in(db: AsyncSession, user: User, remember: bool) -> dict:
    refresh = None
    if remember:
        refresh = await app_sessions.open_session(db, user)
    await db.commit()
    return {"access_token": create_token({"sub": user.username, "role": "client"}),
            "token_type": "bearer", "role": "client", "username": user.username,
            "refresh_token": refresh}


def _suggest(email: str) -> str:
    base = "".join(ch for ch in email.split("@")[0] if ch.isalnum() or ch in "_-")[:27]
    return base if len(base) >= 3 else ""


@router.post("/api/auth/google")
async def google_sign_in(body: GoogleIn, request: Request, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone

    ip = resolve_source_ip(request)
    ratelimit.take(ratelimit.LOGIN_PER_IP, ip)
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="google_off")
    claims = await verify_id_token(body.credential)
    if claims is None:
        raise HTTPException(status_code=401, detail="bad_google_token")
    sub, email = str(claims["sub"]), str(claims["email"]).strip().lower()

    user = (await db.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()
    if user is None:
        same = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
        if same is not None:
            if same.email_verified_at is None:
                # See the module's note: an unconfirmed address proves nothing.
                raise HTTPException(status_code=409, detail="email_unconfirmed")
            if same.google_sub is None:
                same.google_sub = sub
            user = same
    if user is not None:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")
        return await _signed_in(db, user, body.remember)

    # Someone new: a username first.
    if not body.username:
        raise HTTPException(status_code=404, detail={"code": "need_username", "suggest": _suggest(email)})
    ratelimit.take(ratelimit.REGISTER_PER_IP, ip)
    name = body.username.strip()
    if not USERNAME_RE.fullmatch(name):
        raise HTTPException(status_code=422, detail="bad_username")
    taken = (await db.execute(select(User.id).where(func.lower(User.username) == name.lower()))).first()
    if taken:
        raise HTTPException(status_code=409, detail="username_taken")
    referred = None
    if body.ref:
        promo, _ = await credit.resolve_code(db, body.ref, User(id="-"))
        referred = promo.code if promo else None
    user = User(username=name, email=email, email_verified_at=datetime.now(timezone.utc),
                google_sub=sub, password_hash=hash_password(secrets.token_urlsafe(32)),
                lang="ru", referred_code=referred)
    db.add(user)
    await db.flush()
    logger.info("Account %s created with Google", name)
    return await _signed_in(db, user, body.remember)
