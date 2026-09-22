"""
api/referral.py — the customer's own credit and referral code.

Three read endpoints and one that issues a code. Nothing here moves money:
credit is earned and spent by the payment flow, and this module only shows
what the ledger already says.

The shape of the response is deliberate. A balance alone is what makes a
customer suspect they were shortchanged — they remember a reward landing and
see a smaller number today. So the portal gets three things: what is
spendable, what is still vesting, and the entries behind both.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.base import get_db
from db.models import User
from auth.jwt import require_auth
from services import credit
from services.subscriptions import has_active_subscription

logger = logging.getLogger(__name__)
router = APIRouter()


async def _current_user(db: AsyncSession, payload: dict) -> User:
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/api/client/credit")
async def get_credit(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Spendable credit, credit still vesting, and the ledger behind them."""
    user = await _current_user(db, payload)
    entries = await credit.history(db, user)
    return {
        "balance": await credit.balance(db, user),
        "pending": await credit.pending_balance(db, user),
        "max_share_percent": int(credit.MAX_CREDIT_SHARE * 100),
        "history": [
            {
                "delta": e.delta,
                "reason": e.reason,
                "note": e.note,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "vests_at": e.vests_at.isoformat() if e.vests_at else None,
                "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            }
            for e in entries
        ],
    }


@router.get("/api/client/referral")
async def get_referral(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """
    The customer's referral code, if they have one.

    Returns `code: null` rather than issuing one, so that looking at the page
    does not create a code for someone who never asked. Issuing is a POST.
    """
    user = await _current_user(db, payload)
    promo = await credit.code_for(db, user)
    return {
        "code": promo.code if promo else None,
        "uses": promo.uses if promo else 0,
        "discount_percent": promo.discount_percent if promo else credit.DEFAULT_DISCOUNT_PERCENT,
        "reward": credit.REFERRAL_REWARD,
        "eligible": has_active_subscription(user),
    }


@router.post("/api/client/referral", status_code=201)
async def create_referral(
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """
    Issue the customer a referral code.

    Only for someone with a live subscription. The programme rewards
    customers for bringing other customers, and an account that has never
    paid is exactly the shape a sockpuppet takes: register, mint a code, use
    it, register again. Paying first is what makes that cost more than it
    earns.
    """
    user = await _current_user(db, payload)
    if not has_active_subscription(user):
        raise HTTPException(
            status_code=403,
            detail="A referral code is available with an active subscription",
        )

    promo = await credit.issue_code(db, user)
    await db.commit()
    await db.refresh(promo)
    return {
        "code": promo.code,
        "uses": promo.uses,
        "discount_percent": promo.discount_percent,
        "reward": credit.REFERRAL_REWARD,
    }
