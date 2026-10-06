"""
api/admin_grant.py — opening access without a payment.

    POST /api/admin/grant   {"username", "plan"}

For a gift, or for moving a customer over from before the portal with the
time they already paid for. It goes through the same activation as a real
payment (provisioner.activate_payment), so the account ends up exactly as a
buyer's would: the plan's device limit, a first device issued if there is
none, the period added after any days left, reminders and expiry as usual.

What is different is recorded, not hidden: a payments row with amount 0 and
provider "manual", so the account's history says where its time came from
and a grant can never pass for revenue. No referral reward (nothing was paid
in cash) and no receipt — the customer gets an "access is open" letter.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_admin
from config import PLANS, config_limit
from db.base import get_db
from db.models import Payment, User
from services import provisioner

logger = logging.getLogger(__name__)
router = APIRouter()


class GrantRequest(BaseModel):
    username: str
    plan: str


@router.post("/api/admin/grant")
async def grant(req: GrantRequest, db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    # Current plans only: a legacy alias would be activated under a name the
    # portal no longer sells.
    if req.plan not in PLANS:
        raise HTTPException(status_code=422, detail="Unknown plan")
    user = (await db.execute(select(User).where(User.username == req.username.strip()))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=409, detail="Account is disabled")

    payment = Payment(user_id=user.id, plan=req.plan, amount=0, currency="RUB",
                      provider="manual", status="pending")
    db.add(payment)
    await db.commit()

    if not await provisioner.activate_payment(user, payment, db):
        # No device could be issued. Drop the row rather than leave a
        # "pending" grant behind; nothing else was changed.
        await db.delete(payment)
        await db.commit()
        raise HTTPException(status_code=502, detail="No device could be issued; nothing was granted")

    logger.info("Access granted by %s: %s to %s, until %s",
                admin.get("sub"), req.plan, user.username, user.subscribed_until)
    return {"username": user.username, "plan": user.plan, "devices": config_limit(user.plan),
            "subscribed_until": user.subscribed_until}
