"""
Campaign codes: the ones that belong to nobody.

A referral code is minted by a customer and pays them when a friend buys.
A campaign code goes to a blogger or into a mailing, costs money, and pays
nobody. The schema always allowed both — `owner_user_id` is nullable — but
nothing could create the second kind until now.

The interesting tests here are the ones about the seam between the two, since
that is where a campaign could quietly start behaving like a referral, and the
ones about `max_uses`, which is the only thing standing between a code posted
publicly and an unbounded discount.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from api.admin_promo import (  # noqa: E402
    MAX_DISCOUNT_PERCENT, CreatePromoRequest, create_promo_code,
    deactivate_promo_code, list_promo_codes,
)
from api.payment import CreatePaymentRequest, _open_order  # noqa: E402
from db.models import Config, Payment, PromoCode, User  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from services import credit, provisioner  # noqa: E402
from services.provisioner import activate_payment  # noqa: E402

NOW = datetime.now(timezone.utc)
ADMIN = {"sub": "admin", "role": "admin"}


def _user(db, name):
    u = User(id=str(uuid.uuid4()), username=name, email=f"{name}@example.test",
             password_hash="x")
    db.add(u)
    return u


@pytest.fixture
def issued(monkeypatch):
    async def _fake(user, db, name="device"):
        config = Config(id=str(uuid.uuid4()), user_id=user.id, name=name,
                        peer_ip="10.88.88.50", private_key="enc",
                        public_key="PUB", preshared_key="enc", is_active=True)
        db.add(config)
        return config

    monkeypatch.setattr(provisioner, "issue_config", _fake)


# ── creating one ────────────────────────────────────────────────────────────

def test_a_campaign_code_has_no_owner(db):
    """
    What makes it a campaign rather than a referral, and the reason nobody
    earns points from it.
    """
    made = db.run(create_promo_code(
        CreatePromoRequest(code="sept15", discount_percent=15, max_uses=50,
                           note="blogger A, September"),
        db, ADMIN,
    ))
    assert made["code"] == "SEPT15"       # stored upper-case, typed either way
    assert made["kind"] == "campaign"
    assert made["uses"] == 0

    row = db.run(db.execute(
        provisioner.select(PromoCode).where(PromoCode.code == "SEPT15")
    )).scalars().one()
    assert row.owner_user_id is None


def test_a_code_is_generated_when_none_is_given(db):
    made = db.run(create_promo_code(CreatePromoRequest(discount_percent=20), db, ADMIN))
    assert len(made["code"]) == 8
    assert made["code"].isupper()


def test_a_free_subscription_cannot_be_created_by_typo(db):
    """
    A code that takes 100% off is not a discount, it is a subscription
    generator. The cap is well below that so a slipped digit is refused
    rather than honoured.
    """
    for bad in (0, -10, 100, MAX_DISCOUNT_PERCENT + 1):
        with pytest.raises(ValidationError):
            CreatePromoRequest(discount_percent=bad)


def test_a_malformed_code_is_refused(db):
    for bad in ("ab", "with space", "пробел", "-LEADING"):
        with pytest.raises(HTTPException) as exc:
            db.run(create_promo_code(CreatePromoRequest(code=bad), db, ADMIN))
        assert exc.value.status_code == 400, bad


def test_a_duplicate_code_is_refused(db):
    db.run(create_promo_code(CreatePromoRequest(code="AUTUMN"), db, ADMIN))
    with pytest.raises(HTTPException) as exc:
        db.run(create_promo_code(CreatePromoRequest(code="autumn"), db, ADMIN))
    assert exc.value.status_code == 409


def test_an_expiry_in_the_past_is_refused(db):
    """A code that is born expired is a support ticket, not a campaign."""
    with pytest.raises(HTTPException) as exc:
        db.run(create_promo_code(
            CreatePromoRequest(code="LATE10", expires_at=NOW - timedelta(days=1)),
            db, ADMIN,
        ))
    assert exc.value.status_code == 400


# ── how it behaves at the checkout ──────────────────────────────────────────

def test_a_campaign_code_discounts_at_its_own_rate(db):
    db.run(create_promo_code(
        CreatePromoRequest(code="SEPT25", discount_percent=25), db, ADMIN))
    buyer = _user(db, "bob")
    db.run(db.commit())

    payment, quote = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-3m", code="SEPT25")))
    assert quote["discount"] == 225
    assert payment.amount == 675


def test_a_campaign_code_pays_nobody(db, issued):
    """
    `reward_for_payment` returns early for a code with no owner. Without that,
    every campaign purchase would credit points to nobody — or worse, to
    whoever the row happened to point at.
    """
    db.run(create_promo_code(CreatePromoRequest(code="SEPT10"), db, ADMIN))
    buyer = _user(db, "bob")
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-6m", code="SEPT10")))
    db.run(activate_payment(buyer, payment, db))

    entries = db.run(credit.history(db, buyer))
    assert entries == []


def test_a_customer_may_use_a_campaign_code_on_their_own_purchase(db):
    """
    The own-code refusal is about referrals. A campaign code has no owner, so
    there is nobody to refuse it against — and refusing it would mean the
    blogger who posted it cannot use it themselves, which nobody expects.
    """
    db.run(create_promo_code(CreatePromoRequest(code="SEPT10"), db, ADMIN))
    buyer = _user(db, "bob")
    db.run(db.commit())

    promo, refusal = db.run(credit.resolve_code(db, "SEPT10", buyer))
    assert refusal is None
    assert promo.code == "SEPT10"


# ── the use limit ───────────────────────────────────────────────────────────

def test_uses_are_counted_from_paid_orders(db, issued):
    """
    The bug this replaces: uses were incremented inside the referral reward,
    which returns early for a code with no owner — so a campaign code's
    counter never moved and `max_uses` could never take effect. A public code
    with a limit of 50 would have discounted forever.
    """
    db.run(create_promo_code(CreatePromoRequest(code="LIMIT1", max_uses=1), db, ADMIN))
    first = _user(db, "bob")
    second = _user(db, "carol")
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, first, CreatePaymentRequest(plan="basic-3m", code="LIMIT1")))
    db.run(activate_payment(first, payment, db))
    assert db.run(credit.uses_of(db, "LIMIT1")) == 1

    with pytest.raises(HTTPException) as exc:
        db.run(_open_order(db, second, CreatePaymentRequest(plan="basic-3m", code="LIMIT1")))
    assert exc.value.status_code == 400


def test_an_unpaid_order_does_not_consume_a_use(db):
    """
    Opening a checkout is not using a code. Counting those would let anyone
    exhaust a campaign by clicking through it, without paying a ruble.
    """
    db.run(create_promo_code(CreatePromoRequest(code="LIMIT1", max_uses=1), db, ADMIN))
    buyer = _user(db, "bob")
    other = _user(db, "carol")
    db.run(db.commit())

    db.run(_open_order(db, buyer, CreatePaymentRequest(plan="basic-3m", code="LIMIT1")))
    assert db.run(credit.uses_of(db, "LIMIT1")) == 0

    promo, refusal = db.run(credit.resolve_code(db, "LIMIT1", other))
    assert refusal is None


def test_a_one_month_referral_purchase_still_counts_as_a_use(db, issued):
    """
    It earns the referrer nothing — that is deliberate — but it is still a
    purchase made with the code, and the old counter missed it for the same
    reason it missed campaigns entirely.
    """
    owner = _user(db, "alice")
    buyer = _user(db, "bob")
    db.run(db.commit())
    promo = db.run(credit.issue_code(db, owner))
    db.run(db.commit())

    payment, _ = db.run(_open_order(
        db, buyer, CreatePaymentRequest(plan="basic-1m", code=promo.code)))
    db.run(activate_payment(buyer, payment, db))

    assert db.run(credit.pending_balance(db, owner, now=NOW)) == 0
    assert db.run(credit.uses_of(db, promo.code)) == 1


# ── switching one off ───────────────────────────────────────────────────────

def test_deactivating_keeps_the_row(db):
    """
    Payments point at the code they were bought with. Deleting the row throws
    away the only record of what a campaign actually cost.
    """
    db.run(create_promo_code(CreatePromoRequest(code="SEPT10"), db, ADMIN))
    buyer = _user(db, "bob")
    db.run(db.commit())
    db.add(Payment(id=str(uuid.uuid4()), user_id=buyer.id, plan="basic-3m",
                   amount=810, status="paid", promo_code="SEPT10"))
    db.run(db.commit())

    off = db.run(deactivate_promo_code("sept10", db, ADMIN))
    assert off["is_active"] is False
    assert off["uses"] == 1

    promo, refusal = db.run(credit.resolve_code(db, "SEPT10", buyer))
    assert promo is None
    assert refusal == "inactive"


def test_deactivating_an_unknown_code_is_a_404(db):
    with pytest.raises(HTTPException) as exc:
        db.run(deactivate_promo_code("NOSUCH", db, ADMIN))
    assert exc.value.status_code == 404


def test_the_listing_shows_both_kinds(db):
    owner = _user(db, "alice")
    db.run(db.commit())
    db.run(credit.issue_code(db, owner))
    db.run(create_promo_code(CreatePromoRequest(code="SEPT10"), db, ADMIN))
    db.run(db.commit())

    listing = db.run(list_promo_codes(db, ADMIN))
    kinds = sorted(c["kind"] for c in listing["codes"])
    assert kinds == ["campaign", "referral"]
