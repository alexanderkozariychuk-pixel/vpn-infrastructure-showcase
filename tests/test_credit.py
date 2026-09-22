"""
Account credit: the ledger, the codes, and the four ways it loses money.

Credit is a promise to accept rubles less on a future order, so every test
here is about a way the service could end up owing more than it meant to.
They run against a real in-memory database rather than mocks, because the
guarantees that matter — a reward landing exactly once, a balance that
ignores unvested entries — are partly the database's.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.models import CreditEntry, Payment, PromoCode, User  # noqa: E402
from services import credit  # noqa: E402
from services.credit import (  # noqa: E402
    MAX_CREDIT_SHARE,
    REFERRAL_REWARD,
    balance,
    cancel_reward_for_payment,
    history,
    issue_code,
    pending_balance,
    price_order,
    resolve_code,
    reward_for_payment,
    spend_on_payment,
)

NOW = datetime.now(timezone.utc)


def _user(db, name):
    u = User(
        id=str(uuid.uuid4()), username=name, email=f"{name}@example.test",
        password_hash="x",
    )
    db.add(u)
    return u


def _payment(db, user, plan="basic-3m", amount=900, code=None, credit_spent=0, status="pending"):
    p = Payment(
        id=str(uuid.uuid4()), user_id=user.id, plan=plan, amount=amount,
        status=status, promo_code=code, credit_spent=credit_spent,
    )
    db.add(p)
    return p


def _entry(db, user, delta, *, vests=None, expires=None, reason="referral_reward", source=None):
    e = CreditEntry(
        id=str(uuid.uuid4()), user_id=user.id, delta=delta, reason=reason,
        vests_at=vests, expires_at=expires, source_payment_id=source,
    )
    db.add(e)
    return e


# ── the balance ─────────────────────────────────────────────────────────────

def test_vested_credit_counts(db):
    u = _user(db, "alice")
    _entry(db, u, 175, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())
    assert db.run(balance(db, u, now=NOW)) == 175


def test_unvested_credit_does_not_count(db):
    """The whole defence against refund-after-reward: earned is not spendable."""
    u = _user(db, "alice")
    _entry(db, u, 175, vests=NOW + timedelta(days=13), expires=NOW + timedelta(days=200))
    db.run(db.commit())

    assert db.run(balance(db, u, now=NOW)) == 0
    assert db.run(pending_balance(db, u, now=NOW)) == 175


def test_expired_credit_does_not_count(db):
    u = _user(db, "alice")
    _entry(db, u, 175, vests=NOW - timedelta(days=200), expires=NOW - timedelta(days=1))
    db.run(db.commit())
    assert db.run(balance(db, u, now=NOW)) == 0


def test_spends_reduce_the_balance(db):
    u = _user(db, "alice")
    _entry(db, u, 350, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    _entry(db, u, -175, reason="spend")
    db.run(db.commit())
    assert db.run(balance(db, u, now=NOW)) == 175


# ── codes ───────────────────────────────────────────────────────────────────

def test_a_customer_gets_one_code_not_many(db):
    u = _user(db, "alice")
    db.run(db.commit())

    first = db.run(issue_code(db, u))
    db.run(db.commit())
    second = db.run(issue_code(db, u))
    db.run(db.commit())

    assert first.code == second.code
    codes = db.run(db.execute(select(PromoCode).where(PromoCode.owner_user_id == u.id)))
    assert len(list(codes.scalars().all())) == 1


def test_own_code_is_refused(db):
    """Nobody refers themselves."""
    u = _user(db, "alice")
    db.run(db.commit())
    code = db.run(issue_code(db, u))
    db.run(db.commit())

    promo, refusal = db.run(resolve_code(db, code.code, u))
    assert promo is None
    assert "own" in refusal.lower()


def test_someone_else_may_use_it(db):
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    code = db.run(issue_code(db, owner))
    db.run(db.commit())

    promo, refusal = db.run(resolve_code(db, code.code, buyer))
    assert refusal is None
    assert promo.code == code.code


def test_codes_are_case_insensitive_and_trimmed(db):
    """A code arrives from a chat message or a screenshot, not from a form."""
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    code = db.run(issue_code(db, owner))
    db.run(db.commit())

    promo, refusal = db.run(resolve_code(db, f"  {code.code.lower()} ", buyer))
    assert refusal is None
    assert promo.code == code.code


def test_unknown_expired_and_exhausted_codes_are_refused(db):
    buyer = _user(db, "bob")
    owner = _user(db, "alice")
    db.add(PromoCode(id=str(uuid.uuid4()), code="EXPIRED1", owner_user_id=owner.id,
                     discount_percent=10, expires_at=NOW - timedelta(days=1)))
    db.add(PromoCode(id=str(uuid.uuid4()), code="USEDUP12", owner_user_id=owner.id,
                     discount_percent=10, max_uses=1, uses=1))
    db.add(PromoCode(id=str(uuid.uuid4()), code="INACTIVE", owner_user_id=owner.id,
                     discount_percent=10, is_active=False))
    db.run(db.commit())

    for code in ("NOSUCH12", "EXPIRED1", "USEDUP12", "INACTIVE"):
        promo, refusal = db.run(resolve_code(db, code, buyer))
        assert promo is None, code
        assert refusal, code


# ── pricing ─────────────────────────────────────────────────────────────────

def test_a_code_takes_ten_percent_off(db):
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    code = db.run(issue_code(db, owner))
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "basic-3m", code=code.code))
    assert order["base_price"] == 900
    assert order["discount"] == 90
    assert order["amount"] == 810


def test_credit_cannot_cover_more_than_half(db):
    """Every purchase stays a real transaction."""
    buyer = _user(db, "bob")
    _entry(db, buyer, 5000, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "basic-3m", use_credit=5000))
    assert order["credit_spent"] == int(900 * MAX_CREDIT_SHARE)
    assert order["amount"] == 900 - int(900 * MAX_CREDIT_SHARE)


def test_credit_is_clamped_to_what_the_customer_has(db):
    """Asking to spend more than you hold is a slider at its maximum, not an error."""
    buyer = _user(db, "bob")
    _entry(db, buyer, 100, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "basic-3m", use_credit=9999))
    assert order["credit_spent"] == 100
    assert order["amount"] == 800


def test_unvested_credit_cannot_be_spent(db):
    buyer = _user(db, "bob")
    _entry(db, buyer, 175, vests=NOW + timedelta(days=10), expires=NOW + timedelta(days=200))
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "basic-3m", use_credit=175))
    assert order["credit_spent"] == 0
    assert order["amount"] == 900


def test_a_refused_code_does_not_silently_charge_full_price(db):
    """The customer is told, rather than quietly billed the undiscounted amount."""
    buyer = _user(db, "bob")
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "basic-3m", code="NOSUCH12"))
    assert order["promo_code"] is None
    assert order["promo_refused"]
    assert order["amount"] == 900


def test_a_code_and_credit_together_never_go_below_half(db):
    buyer = _user(db, "bob")
    owner = _user(db, "alice")
    db.run(db.commit())
    code = db.run(issue_code(db, owner))
    _entry(db, buyer, 5000, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())

    order = db.run(price_order(db, buyer, "ext-6m", code=code.code, use_credit=5000))
    after_discount = 3200 - 320
    assert order["credit_spent"] == int(after_discount * MAX_CREDIT_SHARE)
    assert order["amount"] == after_discount - order["credit_spent"]
    assert order["amount"] >= after_discount * MAX_CREDIT_SHARE - 1


# ── rewards ─────────────────────────────────────────────────────────────────

def _referred(db, owner, buyer, plan="basic-3m", amount=810):
    code = db.run(issue_code(db, owner))
    db.run(db.commit())
    return _payment(db, buyer, plan=plan, amount=amount, code=code.code)


def test_a_qualifying_referral_pays_the_owner(db):
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == REFERRAL_REWARD
    db.run(db.commit())

    # Earned, but not yet spendable.
    assert db.run(balance(db, owner, now=NOW)) == 0
    assert db.run(pending_balance(db, owner, now=NOW)) == REFERRAL_REWARD
    assert db.run(balance(db, owner, now=NOW + timedelta(days=15))) == REFERRAL_REWARD


def test_a_one_month_purchase_earns_nothing(db):
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer, plan="basic-1m", amount=315)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == 0


def test_an_order_paid_entirely_in_credit_earns_nothing(db):
    """
    Rewards are paid on cash received. Otherwise two accounts pass credit back
    and forth and grow it on every lap.
    """
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer, amount=0)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == 0


def test_a_purchase_with_no_code_earns_nothing(db):
    buyer = _user(db, "bob")
    db.run(db.commit())
    payment = _payment(db, buyer)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == 0


def test_buying_with_your_own_code_earns_nothing(db):
    """resolve_code refuses it at checkout; this is the second line."""
    owner = _user(db, "alice")
    db.run(db.commit())
    code = db.run(issue_code(db, owner))
    db.run(db.commit())
    payment = _payment(db, owner, code=code.code)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == 0


def test_a_reward_lands_exactly_once(db):
    """Gateways retry. A second notification must not pay twice."""
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer)
    db.run(db.commit())

    assert db.run(reward_for_payment(db, payment, now=NOW)) == REFERRAL_REWARD
    db.run(db.commit())
    assert db.run(reward_for_payment(db, payment, now=NOW)) == 0
    db.run(db.commit())

    assert db.run(balance(db, owner, now=NOW + timedelta(days=30))) == REFERRAL_REWARD


def test_a_refund_inside_the_window_cancels_the_reward(db):
    """The reason the vesting window exists."""
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer)
    db.run(db.commit())
    db.run(reward_for_payment(db, payment, now=NOW))
    db.run(db.commit())

    assert db.run(cancel_reward_for_payment(db, payment)) == REFERRAL_REWARD
    db.run(db.commit())

    assert db.run(pending_balance(db, owner, now=NOW)) == 0
    assert db.run(balance(db, owner, now=NOW + timedelta(days=30))) == 0


def test_a_refund_after_vesting_leaves_the_credit_alone(db):
    """
    Clawing back vested credit would leave a negative balance on an account
    that did nothing wrong. The window is the protection; past it, the loss is
    accepted rather than passed to the referrer.
    """
    owner, buyer = _user(db, "alice"), _user(db, "bob")
    db.run(db.commit())
    payment = _referred(db, owner, buyer)
    db.run(db.commit())
    db.run(reward_for_payment(db, payment, now=NOW - timedelta(days=30)))
    db.run(db.commit())

    assert db.run(cancel_reward_for_payment(db, payment)) == 0
    db.run(db.commit())
    assert db.run(balance(db, owner, now=NOW)) == REFERRAL_REWARD


# ── spending and expiry ─────────────────────────────────────────────────────

def test_spending_is_recorded_once(db):
    buyer = _user(db, "bob")
    _entry(db, buyer, 500, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())
    payment = _payment(db, buyer, amount=650, credit_spent=250)
    db.run(db.commit())

    assert db.run(spend_on_payment(db, payment)) == 250
    db.run(db.commit())
    assert db.run(spend_on_payment(db, payment)) == 0
    db.run(db.commit())

    assert db.run(balance(db, buyer, now=NOW)) == 250


def test_an_unpaid_order_spends_nothing(db):
    """Credit is consumed on confirmation, never at checkout."""
    buyer = _user(db, "bob")
    _entry(db, buyer, 500, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())
    _payment(db, buyer, amount=650, credit_spent=250, status="pending")
    db.run(db.commit())

    assert db.run(balance(db, buyer, now=NOW)) == 500


def test_expired_credit_leaves_the_balance_but_not_the_ledger(db):
    """
    Expiry is a condition on the sum, not a sweep that rewrites history.

    Nothing has to run for this to be right, so there is no job that can fall
    behind and leave expired credit spendable. The entry stays in the ledger
    carrying the date it expired on — a balance that silently changed with no
    trace is how a customer concludes the service took their points.
    """
    buyer = _user(db, "bob")
    _entry(db, buyer, 175, vests=NOW - timedelta(days=200), expires=NOW - timedelta(days=1))
    db.run(db.commit())

    assert db.run(balance(db, buyer, now=NOW)) == 0

    entries = db.run(history(db, buyer))
    assert len(entries) == 1
    assert entries[0].delta == 175
    assert entries[0].expires_at is not None


def test_an_expired_entry_does_not_drag_down_live_credit(db):
    """
    The bug this replaces: an expiry sweep wrote an offsetting −175 while the
    sum already excluded the expired entry, and the balance went negative.
    """
    buyer = _user(db, "bob")
    _entry(db, buyer, 175, vests=NOW - timedelta(days=200), expires=NOW - timedelta(days=1))
    _entry(db, buyer, 175, vests=NOW - timedelta(days=1), expires=NOW + timedelta(days=100))
    db.run(db.commit())

    assert db.run(balance(db, buyer, now=NOW)) == 175


# ── the numbers themselves ──────────────────────────────────────────────────

def test_a_fake_account_is_unprofitable():
    """
    The real defence against self-referral. Email registration cannot keep
    sockpuppets out; costing more than they earn keeps working unattended.
    """
    from config import PLANS

    qualifying = [int(p["amount"]) for k, p in PLANS.items() if p["days"] > 31]
    assert REFERRAL_REWARD < min(qualifying) * 0.5, (
        "the reward is close enough to the cheapest qualifying purchase that "
        "farming it could pay"
    )


def test_credit_expires_after_vesting_not_before():
    assert credit.CREDIT_LIFETIME_DAYS >= 180
    assert 0 < credit.REWARD_VESTING_DAYS < 30
