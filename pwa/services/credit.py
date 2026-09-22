"""
services/credit.py — account credit, and the codes that earn it.

Credit is a promise to accept 1 ₽ less on a future order. It is not money: it
cannot be withdrawn, transferred, or refunded in cash. Everything here is
shaped by that — it is a liability, and a liability that cannot be explained
is worse than one that can.

The balance is the sum of a customer's vested, unexpired entries, computed
from the ledger every time. There is deliberately no balance column: a stored
number drifts from the events behind it, and when a customer asks why they
have 350 rather than 525 there is nothing to answer with.

Four things the scheme has to survive, and where each is handled:

  A reward followed by a refund — `REWARD_VESTING_DAYS` below. The credit is
  written at once but is unspendable until it vests, and a refunded purchase
  never vests. That prevents the loss rather than chasing an account that may
  already have spent it.

  Self-referral — a code is refused against its owner's own purchase, and the
  economics do the rest: the smallest qualifying order is 900 ₽ against a
  175-point reward. Email registration cannot keep sockpuppets out; making
  them unprofitable works without anyone watching.

  A code and credit stacked on one order — `MAX_CREDIT_SHARE`.

  Credit earned on credit — `reward_for_payment` reads the cash actually
  received, not the order's face value, so credit cannot breed.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import plan_info
from db.models import CreditEntry, Payment, PromoCode, User

logger = logging.getLogger(__name__)

# A point is one ruble off a future order.
REFERRAL_REWARD = 175

# Only a purchase longer than a month earns one.
MIN_REWARD_DAYS = 31

# Written immediately, spendable after this. The window is what a refund has
# to happen inside for the reward never to materialise.
REWARD_VESTING_DAYS = 14

# Measured from vesting, not from earning: credit nobody could spend yet
# should not be burning down.
CREDIT_LIFETIME_DAYS = 182

# Credit may cover at most half an order. Every purchase stays a real
# transaction — months of zero revenue against live server costs is not
# something this service can absorb.
MAX_CREDIT_SHARE = 0.5

DEFAULT_DISCOUNT_PERCENT = 10

# Unambiguous when read aloud or copied from a screenshot: no O/0, no I/1.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8


def _aware(dt: datetime | None) -> datetime | None:
    """
    A stored datetime, guaranteed comparable.

    Postgres `timestamptz` hands back the offset; SQLite, which the tests run
    on, hands back a naive value and comparing it raises. Everything written
    here is UTC, so assuming UTC on a naive value is safe and keeps the
    comparisons backend-independent.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ── balance ─────────────────────────────────────────────────────────────────

async def balance(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """
    Spendable credit: vested, not expired, summed from the ledger.

    Expiry is a condition here rather than a job that writes cancelling
    entries. The first draft did both, and double-counted: the sum already
    excluded the expired entry, so the offsetting one drove the balance
    negative.

    Keeping only the filter is also the safer half. It is correct the moment
    an entry expires, with nothing scheduled to run and nothing to fall
    behind — where a sweep that failed quietly would leave expired credit
    spendable. The ledger still explains itself: the entry carries the date it
    expired on, which is what the customer needs to see.
    """
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditEntry.delta), 0)).where(
            CreditEntry.user_id == user.id,
            (CreditEntry.vests_at.is_(None)) | (CreditEntry.vests_at <= now),
            (CreditEntry.expires_at.is_(None)) | (CreditEntry.expires_at > now),
        )
    )
    return int(result.scalar_one())


async def pending_balance(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """
    Credit earned but not yet spendable.

    Shown separately in the portal on purpose: a reward that appeared and then
    silently failed to vest, with no sign it ever existed, is how a customer
    concludes the service ate their points.
    """
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(func.coalesce(func.sum(CreditEntry.delta), 0)).where(
            CreditEntry.user_id == user.id,
            CreditEntry.delta > 0,
            CreditEntry.vests_at.is_not(None),
            CreditEntry.vests_at > now,
        )
    )
    return int(result.scalar_one())


async def history(db: AsyncSession, user: User, limit: int = 50) -> list[CreditEntry]:
    result = await db.execute(
        select(CreditEntry)
        .where(CreditEntry.user_id == user.id)
        .order_by(CreditEntry.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


# ── promo codes ─────────────────────────────────────────────────────────────

def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


async def code_for(db: AsyncSession, user: User) -> PromoCode | None:
    """The customer's active referral code, if they have one."""
    result = await db.execute(
        select(PromoCode).where(
            PromoCode.owner_user_id == user.id,
            PromoCode.is_active.is_(True),
        )
    )
    return result.scalars().first()


async def issue_code(db: AsyncSession, user: User) -> PromoCode:
    """
    Give the customer a referral code, or return the one they already have.

    One active code per customer: regenerating would leave the old one working
    and turn a single relationship into an unbounded set of codes to reason
    about.
    """
    existing = await code_for(db, user)
    if existing:
        return existing

    # Collisions are vanishingly unlikely at this alphabet and length, but a
    # duplicate would fail a unique constraint inside a payment flow, which is
    # the worst possible moment to find out.
    for _ in range(10):
        code = _generate_code()
        clash = await db.execute(select(PromoCode).where(PromoCode.code == code))
        if clash.scalars().first() is None:
            break
    else:
        raise RuntimeError("could not generate an unused promo code")

    promo = PromoCode(
        code=code,
        owner_user_id=user.id,
        discount_percent=DEFAULT_DISCOUNT_PERCENT,
    )
    db.add(promo)
    logger.info("Issued referral code %s to %s", code, user.username)
    return promo


async def resolve_code(
    db: AsyncSession,
    code: str | None,
    buyer: User,
    now: datetime | None = None,
) -> tuple[PromoCode | None, str | None]:
    """
    Look up a code for this buyer.

    Returns (code, None) when usable, or (None, reason) when not. The reason is
    meant to reach the customer: "that code has expired" is a better checkout
    than a silent full-price order.
    """
    if not code:
        return None, None

    now = now or datetime.now(timezone.utc)
    result = await db.execute(select(PromoCode).where(PromoCode.code == code.strip().upper()))
    promo = result.scalars().first()

    if promo is None:
        return None, "Unknown code"
    if not promo.is_active:
        return None, "This code is no longer active"
    if _aware(promo.expires_at) is not None and _aware(promo.expires_at) <= now:
        return None, "This code has expired"
    if promo.max_uses is not None and promo.uses >= promo.max_uses:
        return None, "This code has been used up"
    if promo.owner_user_id == buyer.id:
        # Nobody refers themselves. Cheap to check and it removes the most
        # obvious way to try.
        return None, "You cannot use your own referral code"

    return promo, None


# ── pricing an order ────────────────────────────────────────────────────────

def discounted_price(plan_key: str, promo: PromoCode | None) -> int:
    """Plan price less any percentage discount, rounded to whole rubles."""
    info = plan_info(plan_key)
    if not info:
        raise ValueError(f"unknown plan: {plan_key}")
    price = int(info["amount"])
    if promo is None:
        return price
    return price - round(price * promo.discount_percent / 100)


def max_credit_for(amount: int) -> int:
    """The most credit an order of this size may consume."""
    return int(amount * MAX_CREDIT_SHARE)


async def price_order(
    db: AsyncSession,
    user: User,
    plan_key: str,
    code: str | None = None,
    use_credit: int = 0,
    now: datetime | None = None,
) -> dict:
    """
    What this order costs, and what it consumes.

    The single place an order's price is decided, so the checkout preview and
    the payment that follows cannot disagree. Everything is clamped rather
    than rejected — a customer asking to spend more credit than they have is
    not an error, it is a slider at its maximum.
    """
    promo, refusal = await resolve_code(db, code, user, now=now)

    base = int(plan_info(plan_key)["amount"])
    after_discount = discounted_price(plan_key, promo)

    available = await balance(db, user, now=now)
    credit = max(0, min(use_credit, available, max_credit_for(after_discount)))

    return {
        "plan": plan_key,
        "base_price": base,
        "discount": base - after_discount,
        "promo_code": promo.code if promo else None,
        "promo_refused": refusal,
        "credit_available": available,
        "credit_max": max_credit_for(after_discount),
        "credit_spent": credit,
        "amount": after_discount - credit,
    }


# ── ledger writes ───────────────────────────────────────────────────────────

async def spend_on_payment(db: AsyncSession, payment: Payment, now: datetime | None = None) -> int:
    """
    Consume the credit an order was priced with. Called once the payment is
    confirmed, never at checkout: an order that is never paid must not spend
    anything, and an entry written early would have to be chased back.

    Idempotent through the ledger — a second call finds the spend already
    recorded and does nothing, which matters because gateways retry.
    """
    if payment.credit_spent <= 0:
        return 0

    now = now or datetime.now(timezone.utc)
    already = await db.execute(
        select(CreditEntry).where(
            CreditEntry.reason == "spend",
            CreditEntry.payment_id == payment.id,
        )
    )
    if already.scalars().first() is not None:
        return 0

    db.add(CreditEntry(
        user_id=payment.user_id,
        delta=-payment.credit_spent,
        reason="spend",
        payment_id=payment.id,
        note=f"order {payment.plan}",
    ))
    logger.info("Spent %d credit on payment %s", payment.credit_spent, payment.id)
    return payment.credit_spent


async def reward_for_payment(db: AsyncSession, payment: Payment, now: datetime | None = None) -> int:
    """
    Pay the referrer, if this purchase earned anything.

    Nothing is earned when the order carried no code, when the code has no
    owner, when the plan is a single month, or when the buyer paid no cash —
    that last one is what stops credit from breeding, since a reward computed
    on face value would let two accounts pass points back and forth and grow
    them on every lap.

    Returns the points credited, or 0.
    """
    if not payment.promo_code:
        return 0

    now = now or datetime.now(timezone.utc)

    result = await db.execute(select(PromoCode).where(PromoCode.code == payment.promo_code))
    promo = result.scalars().first()
    if promo is None or promo.owner_user_id is None:
        return 0
    if promo.owner_user_id == payment.user_id:
        return 0

    info = plan_info(payment.plan)
    if not info or info["days"] <= MIN_REWARD_DAYS:
        return 0

    if payment.amount <= 0:
        logger.info("No reward for %s: nothing was paid in cash", payment.id)
        return 0

    # The unique constraint on (reason, source_payment_id) is the real
    # guarantee; this check just avoids a pointless integrity error on the
    # common retry.
    already = await db.execute(
        select(CreditEntry).where(
            CreditEntry.reason == "referral_reward",
            CreditEntry.source_payment_id == payment.id,
        )
    )
    if already.scalars().first() is not None:
        return 0

    vests_at = now + timedelta(days=REWARD_VESTING_DAYS)
    db.add(CreditEntry(
        user_id=promo.owner_user_id,
        delta=REFERRAL_REWARD,
        reason="referral_reward",
        source_payment_id=payment.id,
        vests_at=vests_at,
        expires_at=vests_at + timedelta(days=CREDIT_LIFETIME_DAYS),
        note=f"referral: {payment.plan}",
    ))
    promo.uses += 1

    logger.info(
        "Credited %d to %s for referred payment %s, vesting %s",
        REFERRAL_REWARD, promo.owner_user_id, payment.id, vests_at.date(),
    )
    return REFERRAL_REWARD


async def cancel_reward_for_payment(db: AsyncSession, payment: Payment) -> int:
    """
    Undo a reward whose purchase was refunded.

    Only reaches credit that has not vested: once vested it may already have
    been spent, and clawing it back would leave a negative balance on an
    account that did nothing wrong. Inside the vesting window a refund simply
    removes the entry, which is the whole point of the window.
    """
    result = await db.execute(
        select(CreditEntry).where(
            CreditEntry.reason == "referral_reward",
            CreditEntry.source_payment_id == payment.id,
        )
    )
    entry = result.scalars().first()
    if entry is None:
        return 0

    now = datetime.now(timezone.utc)
    vests_at = _aware(entry.vests_at)
    if vests_at is not None and vests_at <= now:
        logger.warning(
            "Reward on refunded payment %s has already vested — leaving it alone",
            payment.id,
        )
        return 0

    await db.delete(entry)
    logger.info("Cancelled unvested reward for refunded payment %s", payment.id)
    return entry.delta
