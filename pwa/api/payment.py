"""
Payment endpoints — Heleket integration.

Flow:
  client selects plan
    -> POST /api/payment/create  (auth)  -> creates Payment(pending), calls
       Heleket create_invoice, returns {url} to redirect the user
  user pays on Heleket
    -> POST /api/payment/webhook (public) -> verify signature, on 'paid'/'paid_over'
       mark Payment paid, activate subscription, then provision config (TODO).
"""
import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User, Payment
from auth.jwt import require_auth
from services import heleket

router = APIRouter()

SITE_URL = os.getenv("SITE_URL", "http://212.67.14.85")

# Server-side price table — NEVER trust amounts from the client.
# Amounts in RUB. First-month promo handled separately if needed.
PLANS = {
    "Basic":    {"amount": "350", "currency": "RUB", "days": 30},
    "Extended": {"amount": "750", "currency": "RUB", "days": 30},
    "Family":   {"amount": "600", "currency": "RUB", "days": 30},
}

# Heleket success statuses
PAID_STATUSES = {"paid", "paid_over"}


class CreatePaymentRequest(BaseModel):
    plan: str


@router.post("/api/payment/create")
async def create_payment(
    req: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    plan = req.plan
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    if plan == "Extended":
        raise HTTPException(status_code=409, detail="Plan not available yet")

    username = payload.get("sub")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    info = PLANS[plan]
    payment = Payment(
        user_id=user.id,
        plan=plan,
        amount=int(info["amount"]),
        currency=info["currency"],
        status="pending",
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # order_id must be unique & free of spaces/special chars — Payment.id (uuid) fits
    try:
        invoice = await heleket.create_invoice(
            amount=info["amount"],
            currency=info["currency"],
            order_id=payment.id,
            url_callback=f"{SITE_URL}/api/payment/webhook",
            url_return=SITE_URL,
            url_success=SITE_URL,
        )
    except Exception as e:
        payment.status = "error"
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Payment gateway error: {e}")

    payment.heleket_invoice_id = invoice.get("uuid")
    await db.commit()

    return {"ok": True, "url": invoice.get("url"), "payment_id": payment.id}


@router.post("/api/payment/webhook")
async def payment_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    data = heleket.verify_webhook(raw)
    if data is None:
        raise HTTPException(status_code=400, detail="Invalid signature")

    order_id = data.get("order_id")
    status = data.get("status")
    if not order_id:
        return {"ok": True}  # nothing to do

    result = await db.execute(select(Payment).where(Payment.id == order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return {"ok": True}  # unknown order — ack to stop retries

    # idempotent: ignore if already finalized
    if payment.status == "paid":
        return {"ok": True}

    if status in PAID_STATUSES:
        payment.status = "paid"
        payment.paid_at = datetime.now(timezone.utc)

        result = await db.execute(select(User).where(User.id == payment.user_id))
        user = result.scalar_one_or_none()
        if user:
            info = PLANS.get(payment.plan, {"days": 30})
            now = datetime.now(timezone.utc)
            base = user.subscribed_until if (user.subscribed_until and user.subscribed_until > now) else now
            user.is_subscribed = True
            user.plan = payment.plan
            user.subscribed_until = base + timedelta(days=info["days"])
            # TODO(next session): auto-provision AWG peer on Bridge:
            #   generate keys -> add peer to awg0.conf via SSH -> save Config row
            #   -> expose config + QR in client portal.
        await db.commit()
    else:
        payment.status = status or "unknown"
        await db.commit()

    return {"ok": True}
