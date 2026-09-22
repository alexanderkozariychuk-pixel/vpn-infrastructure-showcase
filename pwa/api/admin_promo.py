"""
api/admin_promo.py — campaign promo codes.

A referral code belongs to a customer and is minted by them. A campaign code
belongs to nobody: it goes to a blogger, into a mailing, onto a card in a
parcel. The schema has always had room for both — `owner_user_id` is nullable
— but nothing could create the second kind, so the only way to run a campaign
was to write a row by hand in psql.

Campaign codes cost money with no referral behind them, so the guards here
are about not giving away more than intended:

  * the discount is capped well below 100%. A code that makes an order free
    is not a discount, it is a subscription generator, and a typed zero too
    many should not be able to produce one.
  * a code can be switched off but not deleted. Payments reference the code
    they were bought with, and deleting the row throws away the only record
    of what a campaign actually did.
  * uses are counted from paid orders, so a limit of 50 means fifty paid
    orders, not fifty checkouts opened.
"""
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.base import get_db
from db.models import PromoCode
from auth.jwt import require_admin
from services import credit

logger = logging.getLogger(__name__)
router = APIRouter()

# Far enough below 100 that no campaign code can produce a free subscription,
# and low enough that a slipped digit is refused rather than honoured.
MAX_DISCOUNT_PERCENT = 60

_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,31}$")


class CreatePromoRequest(BaseModel):
    # Left out, a code is generated. Given, it is the readable kind a campaign
    # wants — SEPT15, BLOGGER-A.
    code: str | None = None
    discount_percent: int = Field(default=10, ge=1, le=MAX_DISCOUNT_PERCENT)
    max_uses: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    note: str | None = Field(default=None, max_length=255)


async def _describe(db: AsyncSession, promo: PromoCode) -> dict:
    return {
        "code": promo.code,
        "kind": "referral" if promo.owner_user_id else "campaign",
        "discount_percent": promo.discount_percent,
        "max_uses": promo.max_uses,
        "uses": await credit.uses_of(db, promo.code),
        "is_active": promo.is_active,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "created_at": promo.created_at.isoformat() if promo.created_at else None,
        "note": promo.note,
    }


@router.get("/api/admin/promo")
async def list_promo_codes(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """Every code, campaign and referral alike, newest first."""
    result = await db.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
    return {"codes": [await _describe(db, p) for p in result.scalars().all()]}


@router.post("/api/admin/promo", status_code=201)
async def create_promo_code(
    req: CreatePromoRequest,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """
    Create a campaign code: no owner, so nobody earns points from it.

    `reward_for_payment` already refuses to pay a code with no owner, which is
    what keeps a campaign from quietly becoming a referral.
    """
    if req.code:
        code = req.code.strip().upper()
        if not _CODE_RE.match(code):
            raise HTTPException(
                status_code=400,
                detail="A code is 3–32 characters: A–Z, 0–9 and dashes",
            )
    else:
        code = await credit.unused_code(db)

    clash = await db.execute(select(PromoCode).where(PromoCode.code == code))
    if clash.scalars().first() is not None:
        raise HTTPException(status_code=409, detail="That code already exists")

    expires_at = req.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="That expiry is in the past")

    promo = PromoCode(
        code=code,
        owner_user_id=None,
        discount_percent=req.discount_percent,
        max_uses=req.max_uses,
        expires_at=expires_at,
        note=req.note,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)

    logger.info(
        "Created campaign code %s at %d%%, max_uses=%s, expires=%s",
        code, req.discount_percent, req.max_uses, expires_at,
    )
    return await _describe(db, promo)


@router.post("/api/admin/promo/{code}/deactivate")
async def deactivate_promo_code(
    code: str,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_admin),
):
    """
    Switch a code off. Not delete — the payments that used it point at it, and
    the row is the only record of what the campaign cost.
    """
    result = await db.execute(select(PromoCode).where(PromoCode.code == code.strip().upper()))
    promo = result.scalars().first()
    if promo is None:
        raise HTTPException(status_code=404, detail="No such code")

    promo.is_active = False
    await db.commit()
    logger.info("Deactivated promo code %s", promo.code)
    return await _describe(db, promo)
