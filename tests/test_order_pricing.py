"""
What an order costs, and what confirming it moves in the ledger.

The previous file tested the credit rules in isolation. This one tests the
seam they are wired into — the place where a customer's request turns into an
amount a gateway will be told to collect, and where a confirmed payment turns
into ledger entries.

Two things are being defended:

  The price is decided on this side. A request carries a plan, a code and a
  number of points, and never an amount. If that ever stops being true, the
  discount becomes a field an attacker fills in.

  Credit moves exactly once. Gateways retry, and both of ours can deliver the
  same notification twice.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from api.payment import CreatePaymentRequest, _open_order  # noqa: E402
from config import PLANS  # noqa: E402
from db.models import Config, CreditEntry, PromoCode, User  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402
from services import credit, provisioner  # noqa: E402
from services.credit import balance, issue_code  # noqa: E402
from services.provisioner import activate_payment  # noqa: E402

NOW = datetime.now(timezone.utc)


def _user(db, name):
    u = User(
        id=str(uuid.uuid4()), username=name, email=f"{name}@example.test",
        password_hash="x",
    )
    db.add(u)
    return u


def _credit(db, user, amount, *, vested=True):
    db.add(CreditEntry(
        id=str(uuid.uuid4()), user_id=user.id, delta=amount, reason="referral_reward",
        vests_at=NOW - timedelta(days=1) if vested else NOW + timedelta(days=7),
        expires_at=NOW + timedelta(days=150),
    ))


@pytest.fixture
def issued(monkeypatch):
    """Stub the SSH path — the same seam the activation tests use."""
    async def _fake(user, db, name="device"):
        config = Config(
            id=str(uuid.uuid4()), user_id=user.id, name=name, peer_ip="10.88.88.50",
            private_key="enc", public_key="PUB", preshared_key="enc", is_active=True,
        )
        db.add(config)
        return config

    monkeypatch.setattr(provisioner, "issue_config", _fake)


# ── the request cannot name a price ─────────────────────────────────────────

def test_the_request_model_has_no_amount_field():
    """
    The guarantee stated plainly. Everything else here rests on it: if an
    amount ever arrives from the client, a discount stops being something the
    server grants and becomes something the client claims.
    """
    assert set(CreatePaymentRequest.model_fields) == {"plan", "code", "use_credit"}


def test_an_amount_in_the_request_is_ignored(db):
    buyer = _user(db, "bob")
    db.run(db.commit())

    req = CreatePaymentRequest.model_validate(
        {"plan": "basic-1m", "amount": 1, "credit_spent": 999}
    )
    payment, quote = db.run(_open_order(db, buyer, req))

    assert payment.amount == int(PLANS["basic-1m"]["amount"])
    assert payment.credit_spent == 0
    assert quote["amount"] == payment.amount


# ── pricing ─────────────────────────────────────────────────────────────────

def test_a_plain_order_is_the_plan_price(db):
    buyer = _user(db, "bob")
    db.run(db.commit())

    payment, _ = db.run(_open_order(db, buyer, CreatePaymentRequest(plan="basic-3m")))
    assert payment.amount == 900
    assert payment.promo_code is None
    assert payment.credit_spent == 0


def test_a_code_and_credit_both_come_off_the_order(db):
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    promo = db.run(issue_code(db, owner))
    _credit(db, buyer, 500)
    db.run(db.commit())

    payment, quote = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", code=promo.code, use_credit=500)
    ))

    # 900 less 10%, then credit capped at half of what is left.
    assert quote["discount"] == 90
    assert payment.credit_spent == 405
    assert payment.amount == 810 - 405
    assert payment.promo_code == promo.code


def test_the_order_records_credit_without_deducting_it(db):
    """
    An order is an intention. Nothing leaves the ledger until it is paid —
    otherwise a customer who closes the payment page loses points for a
    subscription they never got.
    """
    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 500)
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", use_credit=400)
    ))

    assert payment.credit_spent == 400
    assert db.run(balance(db, buyer, now=NOW)) == 500


def test_unvested_credit_cannot_be_spent(db):
    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 500, vested=False)
    db.run(db.commit())

    payment, quote = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", use_credit=500)
    ))
    assert payment.credit_spent == 0
    assert payment.amount == 900
    assert quote["credit_available"] == 0


def test_a_refused_code_stops_the_order(db):
    """
    Not a silent full-price invoice. Someone who typed a code is waiting for a
    discount, and charging them the full amount without a word is how they
    conclude they were overcharged.
    """
    buyer = _user(db, "bob")
    db.run(db.commit())

    with pytest.raises(HTTPException) as exc:
        db.run(_open_order(db, buyer, CreatePaymentRequest(plan="basic-3m", code="NOPE1234")))
    assert exc.value.status_code == 400
    assert "Unknown" in exc.value.detail


def test_your_own_code_is_refused_at_checkout(db):
    owner = _user(db, "alice")
    db.run(db.commit())
    promo = db.run(issue_code(db, owner))
    db.run(db.commit())

    with pytest.raises(HTTPException) as exc:
        db.run(_open_order(db, owner, CreatePaymentRequest(plan="basic-3m", code=promo.code)))
    assert exc.value.status_code == 400


def test_no_order_can_be_reduced_to_nothing(db):
    """
    Live servers cost money every month. Every purchase stays a real one.
    """
    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 100_000)
    db.run(db.commit())

    for plan in PLANS:
        payment, _ = db.run(_open_order(
            db, buyer, CreatePaymentRequest(plan=plan, use_credit=100_000)
        ))
        assert payment.amount > 0, plan
        assert payment.amount >= int(PLANS[plan]["amount"]) * 0.4, plan


# ── confirming an order moves the ledger ────────────────────────────────────

def test_activation_spends_the_credit_the_order_held(db, issued):
    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 500)
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", use_credit=400)
    ))
    assert db.run(activate_payment(buyer, payment, db)) is True

    assert db.run(balance(db, buyer, now=NOW)) == 100
    assert payment.status == "paid"


def test_a_repeated_notification_spends_the_credit_once(db, issued):
    """Both gateways can deliver the same notification twice."""
    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 500)
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", use_credit=400)
    ))
    db.run(activate_payment(buyer, payment, db))
    db.run(activate_payment(buyer, payment, db))

    assert db.run(balance(db, buyer, now=NOW)) == 100


def test_activation_pays_the_referrer(db, issued):
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    promo = db.run(issue_code(db, owner))
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", code=promo.code)
    ))
    db.run(activate_payment(buyer, payment, db))

    # Earned, but not yet spendable — the vesting window is what a refund has
    # to happen inside.
    assert db.run(balance(db, owner, now=NOW)) == 0
    assert db.run(credit.pending_balance(db, owner, now=NOW)) == credit.REFERRAL_REWARD


def test_a_repeated_notification_pays_the_referrer_once(db, issued):
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    promo = db.run(issue_code(db, owner))
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", code=promo.code)
    ))
    db.run(activate_payment(buyer, payment, db))
    db.run(activate_payment(buyer, payment, db))

    assert db.run(credit.pending_balance(db, owner, now=NOW)) == credit.REFERRAL_REWARD
    refreshed = db.run(db.execute(
        select(PromoCode).where(PromoCode.id == promo.id)
    )).scalars().one()
    assert refreshed.uses == 1


def test_a_monthly_plan_earns_the_referrer_nothing(db, issued):
    """
    The reward is 175 against a 350-rouble month. Paying it out on the
    shortest plan makes a chain of one-month sockpuppets profitable.
    """
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    promo = db.run(issue_code(db, owner))
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-1m", code=promo.code)
    ))
    db.run(activate_payment(buyer, payment, db))

    assert db.run(credit.pending_balance(db, owner, now=NOW)) == 0


def test_a_failed_activation_spends_nothing(db, monkeypatch):
    """
    The payment stays pending for deliberate recovery, so the credit must
    still be there when that recovery happens.
    """
    async def _fail(user, db, name="device"):
        return None

    monkeypatch.setattr(provisioner, "issue_config", _fail)

    buyer = _user(db, "bob")
    db.run(db.commit())
    _credit(db, buyer, 500)
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", use_credit=400)
    ))
    assert db.run(activate_payment(buyer, payment, db)) is False

    assert db.run(balance(db, buyer, now=NOW)) == 500
    assert payment.status == "pending"
