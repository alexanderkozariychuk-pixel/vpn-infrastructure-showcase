"""
Payment endpoints — Heleket integration.
Flow:
  client selects plan
    -> POST /api/payment/create  (auth)  -> creates Payment(pending), calls
       Heleket create_invoice, returns {url} to redirect the user
  user pays on Heleket
    -> POST /api/payment/webhook (public) -> verify signature, on 'paid'/'paid_over'
       calls activate_payment -> subscription extended, and on a first purchase
       an AWG peer is added to the Bridge and its Config saved.
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
from config import PLANS, card_allowed
from fastapi.responses import PlainTextResponse
from services import freekassa

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

@router.post("/api/payment/freekassa/create")
async def create_payment_freekassa(
    req: CreatePaymentRequest,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    """Create a pending payment and hand back the FreeKassa form URL."""
    plan = req.plan
    if plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")

    # Enforced here, not only in the interface. The portal hides the card
    # option for these plans, but the endpoint is what a request actually
    # reaches, and the rule it carries — six months of obligation must not
    # rest on the rail that can disappear — is not a presentation detail.
    if not card_allowed(plan):
        raise HTTPException(
            status_code=409,
            detail="This period is available with cryptocurrency only",
        )

    user = await _current_user(db, payload)
    info = PLANS[plan]
    payment, quote = await _open_order(db, user, req)

    url = freekassa.build_payment_url(
        order_id=payment.id,
        amount=str(quote["amount"]),
        currency=info["currency"],
        email=user.email,
    )
    return {"ok": True, "url": url, "payment_id": payment.id, "quote": quote}


@router.get("/api/payment/freekassa/webhook", response_class=PlainTextResponse)
async def freekassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Payment notification from FreeKassa.

    Method is GET, so parameters arrive in the query string. The response body
    must be exactly "YES" as plain text — anything else, including JSON, is not
    accepted. Note that retries are only enabled after asking their support,
    so a dropped notification is lost by default; idempotency here guards
    against duplicates, not against loss.
    """
    params = dict(request.query_params)

    src_ip = freekassa.resolve_source_ip(request)
    if not freekassa.ip_allowed(src_ip):
        logger.warning("FreeKassa webhook from unexpected IP %s", src_ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    if not freekassa.verify_notification(params):
        logger.warning("FreeKassa webhook with bad signature, order %s",
                       params.get("MERCHANT_ORDER_ID"))
        raise HTTPException(status_code=400, detail="Invalid signature")

    order_id = params.get("MERCHANT_ORDER_ID")
    if not order_id:
        return "YES"

    result = await db.execute(select(Payment).where(Payment.id == order_id))
    payment = result.scalar_one_or_none()
    if not payment:
        logger.warning("FreeKassa webhook for unknown order %s", order_id)
        return "YES"

    # Idempotent: a duplicate notification must not provision twice.
    if payment.status == "paid":
        return "YES"

    # The expected amount is the one stored on this order, not the plan price.
    #
    # Both are server-computed and neither comes from the request, so the
    # guarantee is unchanged — but once an order can carry a discount or spend
    # credit, the plan price stops being what was asked for, and checking
    # against it would reject every discounted payment as a mismatch.
    try:
        paid = float(params.get("AMOUNT", "0"))
    except ValueError:
        paid = 0.0
    expected = float(payment.amount)
    if paid + 0.01 < expected:
        logger.error("FreeKassa amount mismatch on order %s: got %s, expected %s",
                     order_id, paid, expected)
        payment.status = "amount_mismatch"
        await db.commit()
        return "YES"

    result = await db.execute(select(User).where(User.id == payment.user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("FreeKassa webhook: user missing for order %s", order_id)
        return "YES"

    # Same activation path as Heleket — blocking SSH goes to the executor
    # inside issue_config, database work stays in this loop.
    ok = await activate_payment(user, payment, db)
    if not ok:
        logger.error("Activation failed for user %s (FreeKassa order %s)",
                     user.username, order_id)
        # Still acknowledge — manual recovery, no retry storm.

    return "YES"
