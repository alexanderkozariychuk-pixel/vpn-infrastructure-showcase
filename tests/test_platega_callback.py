"""
The Platega callback — the part that turns money into access, so the part an
attacker aims at.

Against a real in-memory database (the `db` fixture), the way the rest of the
payment tests run. Two things are stubbed: `issue_config`, which talks to a
node over SSH, and `platega.fetch_status`, which talks to Platega. Everything
between — matching the callback to a payment, refusing to trust its body,
activating exactly once — is exercised for real.

The load-bearing test is `test_a_forged_confirmed_callback_grants_nothing`:
the callback body says CONFIRMED, Platega says PENDING, and no subscription is
granted. That is the whole reason the callback re-asks the gateway.
"""

import os
import uuid

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")
os.environ.setdefault("PLATEGA_MERCHANT_ID", "MID-1")
os.environ.setdefault("PLATEGA_SECRET", "the-secret")

from db.models import Config, Payment, User  # noqa: E402
from services import platega, provisioner  # noqa: E402
from api import payment as payment_api  # noqa: E402


@pytest.fixture(autouse=True)
def _platega_creds(monkeypatch):
    """
    platega.py reads its credentials at import time; pin this file's secret on
    the module per-test so the callback's constant-time check sees "the-secret"
    regardless of which test module imported services.platega first. Without
    this the secret is whatever won the import race — often "" — and every
    callback is refused with 403 in the full-suite run.
    """
    monkeypatch.setattr(platega, "MERCHANT_ID", "MID-1")
    monkeypatch.setattr(platega, "SECRET", "the-secret")


class FakeRequest:
    """Only what the handler touches: lowercase headers, client, json()."""

    def __init__(self, secret="the-secret", body=None, ip="203.0.113.7"):
        self.headers = {}
        if secret is not None:
            self.headers["x-secret"] = secret
        self.headers["x-real-ip"] = ip
        self._body = body or {}

    @property
    def client(self):
        return None

    async def json(self):
        return self._body


@pytest.fixture
def seeded(db, monkeypatch):
    """A user with a pending Platega order for 100, and issue_config stubbed."""
    async def _fake_issue(user, session, name="device-1"):
        c = Config(
            id=str(uuid.uuid4()), user_id=user.id, name=name, peer_ip="10.88.88.77",
            private_key="x", public_key="y", preshared_key="z", is_active=True,
        )
        session.add(c)
        await session.flush()
        return c

    monkeypatch.setattr(provisioner, "issue_config", _fake_issue)

    user = User(id=str(uuid.uuid4()), username="test1", email="t@x.test", password_hash="h")
    payment = Payment(
        id=str(uuid.uuid4()), user_id=user.id, plan="basic-1m", amount=100,
        currency="RUB", status="pending", provider="platega", provider_ref="TXN-1",
    )
    db.add(user)
    db.add(payment)
    db.run(db.commit())
    return db, user, payment


def _call(db, req):
    return db.run(payment_api.platega_callback(req, db))


def test_a_confirmed_payment_verified_at_the_gateway_grants_the_subscription(seeded, monkeypatch):
    db, user, payment = seeded

    async def _status(txn, client=None):
        assert txn == "TXN-1"
        return {"status": "CONFIRMED", "paymentDetails": {"amount": 100, "currency": "RUB"}}
    monkeypatch.setattr(platega, "fetch_status", _status)

    _call(db, FakeRequest(body={"id": "TXN-1", "amount": 100, "currency": "RUB", "status": "CONFIRMED"}))

    db.run(db.refresh(payment))
    db.run(db.refresh(user))
    assert payment.status == "paid"
    assert user.is_subscribed is True


def test_a_forged_confirmed_callback_grants_nothing(seeded, monkeypatch):
    db, user, payment = seeded

    # The body claims CONFIRMED; the gateway, asked directly, says PENDING.
    async def _status(txn, client=None):
        return {"status": "PENDING", "paymentDetails": {"amount": 100}}
    monkeypatch.setattr(platega, "fetch_status", _status)

    _call(db, FakeRequest(body={"id": "TXN-1", "amount": 100, "status": "CONFIRMED"}))

    db.run(db.refresh(payment))
    db.run(db.refresh(user))
    assert payment.status == "pending"
    assert user.is_subscribed is False


def test_a_bad_secret_is_refused_before_anything_is_read(seeded, monkeypatch):
    db, user, payment = seeded

    def _boom(*a, **k):
        raise AssertionError("must not reach the gateway")
    monkeypatch.setattr(platega, "fetch_status", _boom)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _call(db, FakeRequest(secret="wrong", body={"id": "TXN-1", "status": "CONFIRMED"}))
    assert e.value.status_code == 403


def test_confirmed_but_for_the_wrong_amount_does_not_activate(seeded, monkeypatch):
    db, user, payment = seeded

    async def _status(txn, client=None):
        return {"status": "CONFIRMED", "paymentDetails": {"amount": 1}}  # not 100
    monkeypatch.setattr(platega, "fetch_status", _status)

    _call(db, FakeRequest(body={"id": "TXN-1", "amount": 1, "status": "CONFIRMED"}))

    db.run(db.refresh(payment))
    assert payment.status == "pending"


def test_a_second_notification_does_not_activate_twice(seeded, monkeypatch):
    db, user, payment = seeded
    calls = {"n": 0}

    async def _status(txn, client=None):
        calls["n"] += 1
        return {"status": "CONFIRMED", "paymentDetails": {"amount": 100}}
    monkeypatch.setattr(platega, "fetch_status", _status)

    body = {"id": "TXN-1", "amount": 100, "status": "CONFIRMED"}
    _call(db, FakeRequest(body=body))
    db.run(db.refresh(user))
    until_after_first = user.subscribed_until

    _call(db, FakeRequest(body=body))  # the retry
    db.run(db.refresh(user))

    assert user.subscribed_until == until_after_first  # not extended again
    assert calls["n"] == 1  # the second call short-circuited on status == paid


def test_a_chargeback_is_recorded_and_does_not_touch_access(seeded, monkeypatch):
    db, user, payment = seeded

    async def _status(txn, client=None):
        return {"status": "CHARGEBACKED", "paymentDetails": {"amount": 100}}
    monkeypatch.setattr(platega, "fetch_status", _status)

    _call(db, FakeRequest(body={"id": "TXN-1", "amount": 100, "status": "CHARGEBACKED"}))

    db.run(db.refresh(payment))
    db.run(db.refresh(user))
    assert payment.status == "chargebacked"
    assert user.is_subscribed is False


def test_a_callback_for_an_unknown_transaction_is_acked_not_an_error(seeded, monkeypatch):
    db, user, payment = seeded

    def _boom(*a, **k):
        raise AssertionError("must not reach the gateway for an unknown id")
    monkeypatch.setattr(platega, "fetch_status", _boom)

    out = _call(db, FakeRequest(body={"id": "SOMEONE-ELSES", "status": "CONFIRMED"}))
    assert out == {"ok": True}


def test_the_gateway_being_unreachable_is_not_acked(seeded, monkeypatch):
    db, user, payment = seeded

    async def _down(txn, client=None):
        raise RuntimeError("gateway down")
    monkeypatch.setattr(platega, "fetch_status", _down)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        _call(db, FakeRequest(body={"id": "TXN-1", "status": "CONFIRMED"}))
    assert e.value.status_code == 502
    db.run(db.refresh(payment))
    assert payment.status == "pending"  # left for the retry
