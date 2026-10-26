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

  A reward followed by a refund — `REWARD_VESTING_DAYS` below. The reward is
  written at once but lands only when it vests, and a refunded purchase never
  vests. That prevents the loss rather than chasing an account that may
  already have used it.

  Self-referral — a code is refused against its owner's own purchase, and the
  economics do the rest: the cheapest referred order costs real money (one
  month less the friend's discount) and earns a month the service barely pays
  for, so a fake account buys exactly what it earns. Email registration cannot
  keep sockpuppets out; making them pointless works without anyone watching.

Since 2026-10-26 the referral reward is days, not points: every paid purchase
through someone's code adds `REFERRAL_REWARD_DAYS` to their subscription
(`ReferralReward`). The old rule paid 175 points for purchases over a month
only, so the usual first purchase — one month to try — earned nothing.
Points already earned stay in the ledger and keep working.

  A code and credit stacked on one order — `MAX_CREDIT_SHARE`.

  Credit earned on credit — `reward_for_payment` reads the cash actually
  received, not the order's face value, so credit cannot breed.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import plan_info
from db.models import CreditEntry, Payment, PromoCode, ReferralReward, User

logger = logging.getLogger(__name__)

# What a referrer gets for each paid purchase through their code: a month.
REFERRAL_REWARD_DAYS = 30

# Written immediately, applied (or, for old points, spendable) after this. The window is what a refund has
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


async def unused_code(db: AsyncSession) -> str:
    """
    A generated code that is not already taken.

    Collisions are vanishingly unlikely at this alphabet and length — 32^8 is
    about 1.1 trillion — and the entropy is not there to stop guessing:
    guessing someone's referral code gives the guesser a discount and its
    owner the reward, which is nobody's idea of an attack. It is there so two
    customers are never handed the same code. A duplicate would surface as a
    unique-constraint failure inside a payment flow, which is the worst
    possible moment to learn about it, so it is checked here instead.
    """
    for _ in range(10):
        code = _generate_code()
        clash = await db.execute(select(PromoCode).where(PromoCode.code == code))
        if clash.scalars().first() is None:
            return code
    raise RuntimeError("could not generate an unused promo code")


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

    code = await unused_code(db)
    promo = PromoCode(
        code=code,
        owner_user_id=user.id,
        discount_percent=DEFAULT_DISCOUNT_PERCENT,
    )
    db.add(promo)
    logger.info("Issued referral code %s to %s", code, user.username)
    return promo


async def uses_of(db: AsyncSession, code: str) -> int:
    """
    How many times a code has actually been used: paid orders that carried it.

    Counted, not stored. The first version kept a `uses` column and
    incremented it inside `reward_for_payment` — which returns early for a
    code with no owner, so a campaign code's counter never moved and its
    `max_uses` limit could never bite. A one-month purchase through a referral
    code went uncounted for the same reason.

    Deriving it removes the class of bug rather than that instance: there is
    no second place that has to remember to increment, retried webhooks cannot
    double-count, and the number is right even for rows written by hand.

    A code at its limit can still be slightly over-subscribed — two customers
    holding an unpaid order can both pay. Locking a marketing code against
    that costs more than the extra use is worth.
    """
    result = await db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.promo_code == code,
            Payment.status == "paid",
        )
    )
    return int(result.scalar_one())


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

    The reason is a short machine token, not a sentence. The portal is
    Russian by default and the API cannot know which language a caller is
    showing, so the wording belongs on that side; `REFUSAL_TEXT` below carries
    an English fallback for logs and for anything reading the API directly.
    """
    if not code:
        return None, None

    now = now or datetime.now(timezone.utc)
    result = await db.execute(select(PromoCode).where(PromoCode.code == code.strip().upper()))
    promo = result.scalars().first()

    if promo is None:
        return None, "unknown"
    if not promo.is_active:
        return None, "inactive"
    if _aware(promo.expires_at) is not None and _aware(promo.expires_at) <= now:
        return None, "expired"
    if promo.max_uses is not None and await uses_of(db, promo.code) >= promo.max_uses:
        return None, "used_up"
    if promo.owner_user_id == buyer.id:
        # Nobody refers themselves. Cheap to check and it removes the most
        # obvious way to try.
        return None, "own_code"
    if promo.owner_user_id is not None and not await is_first_purchase(db, buyer):
        # A friend's code is an invitation: it discounts the first purchase
        # and rewards the friend once. Typed again at every renewal it would
        # be a permanent discount and a month for the friend each time.
        return None, "not_first"

    return promo, None


REFUSAL_TEXT = {
    "unknown":  "Unknown code",
    "inactive": "This code is no longer active",
    "expired":  "This code has expired",
    "used_up":  "This code has been used up",
    "own_code": "You cannot use your own referral code",
    "not_first": "A friend's code applies to the first purchase only",
}


# ── pricing an order ────────────────────────────────────────────────────────

async def is_first_purchase(db: AsyncSession, user: User) -> bool:
    """No paid order yet. Access opened from the admin panel (provider
    "manual") is not a purchase and does not use up the first one."""
    paid = await db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.user_id == user.id,
            Payment.status.in_(("paid", "paid_over")),
            or_(Payment.provider.is_(None), Payment.provider != "manual"),
        )
    )
    return int(paid.scalar_one()) == 0


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

    # A customer who came by a referral link gets that code on their first
    # purchase without typing it. A code typed at the checkout wins; a link
    # code that no longer resolves is simply not applied — the customer never
    # typed it, so there is nothing to tell them was refused.
    auto = False
    if not code and user.referred_code and await is_first_purchase(db, user):
        promo, _ = await resolve_code(db, user.referred_code, user, now=now)
        auto = promo is not None

    base = int(plan_info(plan_key)["amount"])
    after_discount = discounted_price(plan_key, promo)

    available = await balance(db, user, now=now)
    credit = max(0, min(use_credit, available, max_credit_for(after_discount)))

    return {
        "plan": plan_key,
        "base_price": base,
        "discount": base - after_discount,
        "promo_code": promo.code if promo else None,
        "promo_auto": auto,
        # The token is what the portal translates; the text is the fallback.
        "promo_refused": refusal,
        "promo_refused_text": REFUSAL_TEXT.get(refusal) if refusal else None,
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
    Reward the referrer, if this purchase earned anything.

    Any paid plan earns `REFERRAL_REWARD_DAYS` — including a single month,
    which is how most people start. Nothing is earned when the order carried
    no code, when the code has no owner (a campaign code), when the buyer is
    the owner, or when the buyer paid no cash (an admin grant, an order covered
    by old points).

    The reward is recorded now and lands when it vests; see
    `apply_due_rewards`. Returns the days recorded, or 0.
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

    if not plan_info(payment.plan):
        return 0

    if payment.amount <= 0:
        logger.info("No reward for %s: nothing was paid in cash", payment.id)
        return 0

    # The unique constraint on source_payment_id is the real guarantee; this
    # check just avoids a pointless integrity error on the common retry.
    already = await db.execute(
        select(ReferralReward).where(ReferralReward.source_payment_id == payment.id)
    )
    if already.scalars().first() is not None:
        return 0

    vests_at = now + timedelta(days=REWARD_VESTING_DAYS)
    db.add(ReferralReward(
        referrer_user_id=promo.owner_user_id,
        source_payment_id=payment.id,
        days=REFERRAL_REWARD_DAYS,
        vests_at=vests_at,
        note=f"referral: {payment.plan}",
    ))
    logger.info(
        "Referral reward of %d days for %s on payment %s, vesting %s",
        REFERRAL_REWARD_DAYS, promo.owner_user_id, payment.id, vests_at.date(),
    )
    return REFERRAL_REWARD_DAYS


async def cancel_reward_for_payment(db: AsyncSession, payment: Payment) -> int:
    """
    Undo a reward whose purchase was refunded.

    Only reaches a reward that has not been applied: once the days are on the
    referrer's subscription, taking them back would cut short an account that
    did nothing wrong. Inside the vesting window a refund simply removes the
    record, which is the whole point of the window. Points earned under the
    old rule are handled the same way.
    """
    result = await db.execute(
        select(ReferralReward).where(ReferralReward.source_payment_id == payment.id)
    )
    reward = result.scalars().first()
    if reward is not None:
        if reward.applied_at is not None:
            logger.warning(
                "Reward on refunded payment %s was already applied — leaving it alone",
                payment.id,
            )
            return 0
        await db.delete(reward)
        logger.info("Cancelled unapplied reward for refunded payment %s", payment.id)
        return reward.days

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


def _subscribed(user: User, now: datetime) -> bool:
    until = _aware(user.subscribed_until)
    return bool(user.is_subscribed) and until is not None and until > now


async def apply_rewards_for(db: AsyncSession, user: User, now: datetime | None = None) -> int:
    """
    Add this referrer's vested, unapplied rewards to their subscription.

    Only to a live subscription: days added to an ended one would reopen it
    with no devices on the node. A referrer whose subscription has lapsed
    keeps the reward, and their next purchase calls this after extending.

    Returns the days added. Does not commit.
    """
    now = now or datetime.now(timezone.utc)
    if not _subscribed(user, now):
        return 0
    due = (await db.execute(
        select(ReferralReward).where(
            ReferralReward.referrer_user_id == user.id,
            ReferralReward.applied_at.is_(None),
            ReferralReward.vests_at <= now,
        )
    )).scalars().all()
    if not due:
        return 0

    from services import notify  # notify imports mailer; keep it off the import path of pricing

    added = 0
    for reward in due:
        user.subscribed_until = _aware(user.subscribed_until) + timedelta(days=reward.days)
        reward.applied_at = now
        added += reward.days
        await notify.notify(
            db, user, "referral_bonus", dedupe=f"referral:{reward.id}",
            days=reward.days,
            date=_aware(user.subscribed_until).astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y"),
        )
    logger.info("Added %d referral days to %s, now until %s",
                added, user.username, _aware(user.subscribed_until).date())
    return added


async def apply_due_rewards(db: AsyncSession, now: datetime | None = None) -> dict:
    """
    The hourly part (expire_subscriptions.py): every vested reward whose
    referrer has a live subscription. Runs before the expiry sweep, so a
    month that has landed is on the subscription before anyone checks
    whether it ended. Commits.
    """
    now = now or datetime.now(timezone.utc)
    owners = (await db.execute(
        select(ReferralReward.referrer_user_id).where(
            ReferralReward.applied_at.is_(None),
            ReferralReward.vests_at <= now,
        ).distinct()
    )).scalars().all()

    stats = {"referrers_rewarded": 0, "referral_days_added": 0}
    for uid in owners:
        user = await db.get(User, uid)
        if user is None:
            continue
        days = await apply_rewards_for(db, user, now=now)
        if days:
            stats["referrers_rewarded"] += 1
            stats["referral_days_added"] += days
    await db.commit()
    return stats


async def rewards_of(db: AsyncSession, user: User) -> list[ReferralReward]:
    """This customer's rewards, newest first, for the portal."""
    result = await db.execute(
        select(ReferralReward)
        .where(ReferralReward.referrer_user_id == user.id)
        .order_by(ReferralReward.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())
