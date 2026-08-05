"""
Payment endpoints — Heleket integration.
Flow:
  client selects plan
    -> POST /api/payment/create  (auth)  -> creates Payment(pending), calls
       Heleket create_invoice, returns {url} to redirect the user
  user pays on Heleket
    -> POST /api/payment/webhook (public) -> verify signature, on 'paid'/'paid_over'
       calls provision_basic -> AWG peer added to Bridge, Config saved to DB.
"""
import os
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User, Payment
from auth.jwt import require_auth
from services import heleket
from services.provisioner import provision_basic

logger = logging.getLogger(__name__)
router = APIRouter()

SITE_URL = os.getenv("SITE_URL", "http://212.67.14.85")

PLANS = {
    "Basic": {"amount": "300", "currency": "RUB", "days": 30},
}

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
    status   = data.get("status")
    if not order_id:
        return {"ok": True}

    result = await db.execute(select(Payment).where(Payment.id == order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        return {"ok": True}

    # idempotent
    if payment.status == "paid":
        return {"ok": True}

    if status in PAID_STATUSES:
        result = await db.execute(select(User).where(User.id == payment.user_id))
        user = result.scalar_one_or_none()

        if user and payment.plan == "Basic":
            # run provisioner in thread (SSH calls are blocking)
            ok = await provision_basic(user, payment, db)
            if not ok:
                logger.error("Provisioning failed for user %s", user.username)
                # still ack to Heleket — manual recovery needed
        elif user:
            # other plans: just activate, no auto-provisioning yet
            payment.status = "paid"
            payment.paid_at = datetime.now(timezone.utc)
            user.is_subscribed = True
            user.plan = payment.plan
            await db.commit()
    else:
        payment.status = status or "unknown"
        await db.commit()

    return {"ok": True}
