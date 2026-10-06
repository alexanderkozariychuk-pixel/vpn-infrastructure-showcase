"""
Referral links (/?ref=CODE): the code is recorded at registration and applied
by itself to the first purchase only. Codes are still issued to paying
customers only (tests/test_credit.py).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import register  # noqa: E402
from config import plan_info  # noqa: E402
from db.models import Payment, PromoCode, User  # noqa: E402
from services import credit, mailer, ratelimit  # noqa: E402

NOW = datetime.now(timezone.utc)
STATIC = Path(__file__).parent.parent / "pwa" / "static"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    for lim in ratelimit.ALL:
        lim.reset()

    async def fake_send(*a, **k):
        return True
    monkeypatch.setattr(register, "send_email", fake_send)
    yield
    for lim in ratelimit.ALL:
        lim.reset()


def _owner(db, code="TONI2345"):
    u = User(id=str(uuid.uuid4()), username="toni", email="toni@example.com", password_hash="x",
             is_subscribed=True, subscribed_until=NOW + timedelta(days=30))
    db.add(u)
    db.add(PromoCode(code=code, owner_user_id=u.id, discount_percent=10))
    db.run(db.commit())
    return u


def _register(db, ref, username="cooper"):
    req = register.RegisterRequest(username=username, email=f"{username}@example.com",
                                   password="long-enough", ref=ref)
    db.run(register.register(req, SimpleNamespace(headers={"x-real-ip": "198.51.100.9"}, client=None), db))
    return db.run(db.execute(select(User).where(User.username == username))).scalar_one()


def _paid(db, user, plan="basic-3m", provider="platega", code=None):
    db.add(Payment(user_id=user.id, plan=plan, amount=int(plan_info(plan)["amount"]), currency="RUB",
                   status="paid", provider=provider, promo_code=code))
    db.run(db.commit())


def _quote(db, user, code=None, plan="basic-3m"):
    return db.run(credit.price_order(db, user, plan, code=code))


def test_registration_records_the_code_from_the_link(db):
    _owner(db)
    assert _register(db, "toni2345").referred_code == "TONI2345"


@pytest.mark.parametrize("ref", ["NOPE1234", "", None])
def test_a_code_that_does_not_resolve_is_dropped_silently(db, ref):
    _owner(db)
    assert _register(db, ref).referred_code is None


def test_an_inactive_code_is_not_recorded(db):
    _owner(db)
    promo = db.run(db.execute(select(PromoCode))).scalar_one()
    promo.is_active = False
    db.run(db.commit())
    assert _register(db, "TONI2345").referred_code is None


def test_the_first_purchase_gets_the_code_by_itself(db):
    _owner(db)
    u = _register(db, "TONI2345")
    q = _quote(db, u)
    assert q["promo_code"] == "TONI2345" and q["promo_auto"] is True
    assert q["discount"] == 90 and q["amount"] == 810


def test_the_second_purchase_does_not(db):
    _owner(db)
    u = _register(db, "TONI2345")
    _paid(db, u, code="TONI2345")
    q = _quote(db, u)
    assert q["promo_code"] is None and q["discount"] == 0


def test_a_gift_from_the_admin_does_not_use_up_the_first_purchase(db):
    _owner(db)
    u = _register(db, "TONI2345")
    _paid(db, u, plan="ext-6m", provider="manual")
    assert _quote(db, u)["promo_auto"] is True


def test_a_code_typed_at_checkout_wins(db):
    _owner(db)
    db.add(PromoCode(code="BLOG2026", discount_percent=20))
    db.run(db.commit())
    u = _register(db, "TONI2345")
    q = _quote(db, u, code="BLOG2026")
    assert q["promo_code"] == "BLOG2026" and q["promo_auto"] is False


def test_a_link_code_that_has_since_expired_is_quietly_not_applied(db):
    _owner(db)
    u = _register(db, "TONI2345")
    promo = db.run(db.execute(select(PromoCode))).scalar_one()
    promo.expires_at = NOW - timedelta(days=1)
    db.run(db.commit())
    q = _quote(db, u)
    assert q["promo_code"] is None and q["promo_refused"] is None and q["amount"] == 900


def test_the_inviter_is_rewarded_through_the_auto_applied_code(db):
    owner = _owner(db)
    u = _register(db, "TONI2345")
    q = _quote(db, u)
    pay = Payment(user_id=u.id, plan="basic-3m", amount=q["amount"], currency="RUB",
                  status="paid", provider="platega", promo_code=q["promo_code"])
    db.add(pay)
    db.run(db.commit())
    assert db.run(credit.reward_for_payment(db, pay)) == credit.REFERRAL_REWARD


def test_both_pages_remember_the_link_and_the_portal_sends_it():
    for page in ("landing.html", "index.html"):
        html = (STATIC / page).read_text()
        assert "localStorage.setItem('sov_ref'" in html, page
    index = (STATIC / "index.html").read_text()
    assert "ref: referralCode()" in index
    assert "localStorage.removeItem('sov_ref')" in index
