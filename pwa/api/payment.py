"""
Payment endpoints.

Platega is the gateway customers use: SBP, card and crypto on one page.
  POST /api/payment/platega/create    (auth)   -> pending Payment, redirect url
  POST /api/payment/platega/callback  (public) -> re-asks Platega, then activates

Heleket is kept on the server as a fallback and is not offered in the portal.
  POST /api/payment/create   (auth)   -> pending Payment, Heleket invoice url
  POST /api/payment/webhook  (public) -> signature check, then activates

FreeKassa was removed on 2026-09-29, once Platega had taken a live payment.

Every path ends in activate_payment: the subscription is extended, and on a
first purchase a peer is added on the node and its Config saved.
"""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.base import get_db
from db.models import User, Payment
from auth.jwt import require_auth
from services import heleket
from services import credit
from services.provisioner import activate_payment
from config import PLANS
from services import net, platega

logger = logging.getLogger(__name__)
router = APIRouter()

SITE_URL = os.getenv("SITE_URL", "https://sov3r3ign.com")

PAID_STATUSES = {"paid", "paid_over"}


class CreatePaymentRequest(BaseModel):
    plan: str
    # Both optional: an order without either is the ordinary full-price case.
    code: str | None = None
    use_credit: int = 0


async def _current_user(db: AsyncSession, payload: dict) -> User:
    result = await db.execute(select(User).where(User.username == payload.get("sub")))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _open_order(
    db: AsyncSession, user: User, req: CreatePaymentRequest
) -> tuple[Payment, dict]:
    """
    Price an order and record it as pending.

    The price comes from `credit.price_order` and nothing else, so the quote
    the customer saw and the invoice they are sent cannot disagree. Note that
    the request carries only what the customer *asked* for — a code and a
    number of points — never an amount: every ruble here is computed on this
    side.

    A refused code stops the order rather than quietly charging full price.
    Someone who typed a code is waiting for a discount, and an invoice that
    silently ignores it is how a customer decides they were overcharged.
    """
    quote = await credit.price_order(
        db, user, req.plan, code=req.code, use_credit=req.use_credit
    )
    if quote["promo_refused"]:
        raise HTTPException(status_code=400, detail=quote["promo_refused_text"])

    payment = Payment(
        user_id=user.id,
        plan=req.plan,
        amount=quote["amount"],
        currency=PLANS[req.plan]["currency"],
        status="pending",
        promo_code=quote["promo_code"],
        credit_spent=quote["credit_spent"],
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    return payment, quote


@router.post("/api/payment/quote")
async def quote_payment(
    req: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """
    What this order would cost. Read-only; nothing is recorded.

    The portal calls this as the customer types a code or moves the points
    slider. A refused code is returned as text rather than an error, because
    at this stage the customer is still editing.
    """
    if req.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    user = await _current_user(db, payload)
    return await credit.price_order(
        db, user, req.plan, code=req.code, use_credit=req.use_credit
    )


@router.post("/api/payment/create")
async def create_payment(
    req: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    plan = req.plan
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")

    user = await _current_user(db, payload)
    info = PLANS[plan]
    payment, quote = await _open_order(db, user, req)

    try:
        invoice = await heleket.create_invoice(
            amount=str(quote["amount"]),
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
    return {"ok": True, "url": invoice.get("url"), "payment_id": payment.id, "quote": quote}


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

        if user:
            # One path for every plan. Branching on the plan name is what left
            # anything that was not "Basic" activated with no config at all.
            ok = await activate_payment(user, payment, db)
            if not ok:
                logger.error("Activation failed for user %s on order %s", user.username, order_id)
                # still ack to Heleket — manual recovery, no retry storm
    else:
        payment.status = status or "unknown"
        await db.commit()

    return {"ok": True}

# ── Platega ───────────────────────────────────────────────────────────────
#
# One gateway for SBP, card and crypto: the customer picks on Platega's page
# (methodless /v2/transaction/process). The callback carries no signature over
# its body — only the shared X-Secret in a header — so it is treated as a
# nudge, and the real status is read back from Platega before anything is
# granted. A forged CONFIRMED callback then changes nothing.


@router.post("/api/payment/platega/create")
async def create_payment_platega(
    req: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    if req.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")

    user = await _current_user(db, payload)
    payment, quote = await _open_order(db, user, req)
    payment.provider = "platega"
    await db.commit()

    try:
        created = await platega.create_transaction(
            amount=quote["amount"],                 # whole rubles; 100 -> 100 ₽, verified live
            currency=PLANS[req.plan]["currency"],
            description=f"Sovereign — {req.plan}",
            return_url=f"{SITE_URL}/app?paid=1",
            failed_url=f"{SITE_URL}/app?paid=0",
            order_id=payment.id,
        )
    except Exception as e:
        payment.status = "error"
        await db.commit()
        logger.error("Platega create failed for %s on order %s: %s", user.username, payment.id, e)
        raise HTTPException(status_code=502, detail="Payment gateway error")

    txn = created.get("transactionId")
    url = created.get("url")
    if not txn or not url:
        payment.status = "error"
        await db.commit()
        logger.error("Platega create returned no txn/url for order %s: %s", payment.id, created)
        raise HTTPException(status_code=502, detail="Payment gateway error")

    payment.provider_ref = txn
    await db.commit()
    return {"ok": True, "url": url, "payment_id": payment.id, "quote": quote}


@router.post("/api/payment/platega/callback")
async def platega_callback(request: Request, db: AsyncSession = Depends(get_db)):
    # First gate: the shared secret Platega echoes in the header. Cheap, and it
    # turns away the internet at large — but the body has no signature, so it
    # is not proof. The real check is asking Platega, below.
    if not platega.secret_matches(request.headers.get("x-secret")):
        logger.warning("Platega callback with a bad secret from %s",
                       net.resolve_source_ip(request))
        raise HTTPException(status_code=403, detail="Forbidden")

    body = await request.json()
    txn = str(body.get("id") or "")
    if not txn:
        return {"ok": True}

    result = await db.execute(
        select(Payment).where(Payment.provider_ref == txn, Payment.provider == "platega")
    )
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("Platega callback for unknown transaction %s", txn)
        return {"ok": True}

    if payment.status == "paid":
        return {"ok": True}  # idempotent — a repeat notification changes nothing

    # The callback is only a nudge. Ask Platega for the real state over our own
    # authenticated request; a forged CONFIRMED body dies here.
    try:
        status = await platega.fetch_status(txn)
    except Exception as e:
        # Could not reach Platega — do not ack, let it retry.
        logger.error("Platega status check failed for %s: %s", txn, e)
        raise HTTPException(status_code=502, detail="Could not verify")

    if status is None:
        raise HTTPException(status_code=502, detail="Could not verify")

    real = status.get("status")

    if real == platega.CONFIRMED:
        paid = status.get("paymentDetails") or {}
        paid_amount = paid.get("amount")
        if paid_amount is None or int(paid_amount) != int(payment.amount):
            # Confirmed, but not for the amount we recorded. This needs a
            # human, not an activation and not a retry.
            logger.error("Platega amount mismatch on %s: gateway %r, order %s",
                         txn, paid_amount, payment.amount)
            return {"ok": True}
        result = await db.execute(select(User).where(User.id == payment.user_id))
        user = result.scalar_one_or_none()
        if user:
            ok = await activate_payment(user, payment, db)
            if not ok:
                logger.error("Platega activation failed for %s on %s", user.username, txn)
        return {"ok": True}

    if real == platega.CHARGEBACKED:
        # Money clawed back after the fact. Record it; revoking access is a
        # separate, deliberate decision, not a webhook's to make.
        logger.warning("Platega CHARGEBACKED on %s (order %s, user %s)",
                       txn, payment.id, payment.user_id)
        payment.status = "chargebacked"
        await db.commit()
        return {"ok": True}

    if real == platega.CANCELED:
        payment.status = "canceled"
        await db.commit()
    # PENDING and anything else: nothing to grant. A later CONFIRMED arrives
    # as its own callback.
    return {"ok": True}
