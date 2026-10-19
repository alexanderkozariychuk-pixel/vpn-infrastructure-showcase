"""
An order for a plan that allows fewer devices than the account holds is
refused until the extra devices are deleted (api/payment.py, _open_order).

activate_payment never takes devices away, and the device limit was checked
only when adding one: an early renewal from Extended (5) to Basic (2) kept all
five on the Basic price, every period after.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from api import payment
from db.models import Config, Payment, User


def _user(db, plan="ext-1m", until_days=10):
    user = User(
        id=str(uuid.uuid4()), username=f"u{uuid.uuid4().hex[:6]}", email="u@example.com",
        password_hash="h", plan=plan, is_subscribed=True,
        subscribed_until=datetime.now(timezone.utc) + timedelta(days=until_days),
        email_verified_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.run(db.commit())
    return user


def _devices(db, user, n, kind="paid", active=True):
    for i in range(n):
        db.add(Config(id=str(uuid.uuid4()), user_id=user.id, name=f"d{i}",
                      peer_ip=f"10.88.88.{60 + i}", private_key="x",
                      public_key=str(uuid.uuid4()), preshared_key="z",
                      is_active=active, kind=kind))
    db.run(db.commit())


def _order(db, user, plan):
    return db.run(payment._open_order(db, user, payment.CreatePaymentRequest(plan=plan)))


def _orders(db, user):
    return db.run(db.execute(select(Payment).where(Payment.user_id == user.id))).scalars().all()


def test_extended_with_five_devices_cannot_buy_basic(db):
    user = _user(db)
    _devices(db, user, 5)
    with pytest.raises(HTTPException) as e:
        _order(db, user, "basic-1m")
    assert e.value.status_code == 409
    assert e.value.detail == {"code": "too_many_devices", "held": 5, "limit": 2}
    assert _orders(db, user) == [], "a refused order must leave no pending payment behind"


def test_after_deleting_the_extra_ones_basic_can_be_bought(db):
    user = _user(db)
    _devices(db, user, 2)
    _devices(db, user, 3, active=False)   # deleted: rows stay, inactive
    pay, _ = _order(db, user, "basic-1m")
    assert pay.status == "pending" and pay.plan == "basic-1m"


def test_extended_can_be_renewed_with_five(db):
    user = _user(db)
    _devices(db, user, 5)
    pay, _ = _order(db, user, "ext-1m")
    assert pay.plan == "ext-1m"


def test_a_trial_device_does_not_count(db):
    """It sits in the trial subnet and ends with the purchase (activate_payment)."""
    user = _user(db, plan=None)
    _devices(db, user, 2)
    _devices(db, user, 1, kind="trial")
    pay, _ = _order(db, user, "basic-1m")
    assert pay.plan == "basic-1m"


def test_an_ended_subscription_whose_devices_are_not_swept_yet_is_still_checked(db):
    """Between the end of a period and the hourly sweep the devices are
    active, and a payment then is a renewal: it would keep all of them."""
    user = _user(db, until_days=-1)
    _devices(db, user, 4)
    with pytest.raises(HTTPException) as e:
        _order(db, user, "basic-3m")
    assert e.value.detail["held"] == 4


def test_the_checkout_says_why_and_leads_to_the_devices():
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html").read_text(encoding="utf-8")
    pay = html[html.index("async function startPayment("):]
    pay = pay[:pay.index("\n}\n")]
    assert "d.detail.code === 'too_many_devices'" in pay
    assert "showPage('client', 'config')" in pay, "no way from the refusal to the devices"
    for lang in ("en", "ru"):
        start = html.index(f"\n  {lang}: {{\n")
        table = html[start:html.index("\n  },", start)]
        assert "'pay-too-many':" in table and "'pay-too-many-go':" in table, lang
        text = table[table.index("'pay-too-many':"):].split("\n")[0]
        assert "{held}" in text and "{limit}" in text, lang
