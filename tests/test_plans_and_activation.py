"""
Plans with periods, and what a payment does to a subscription.

Three bugs lived here and each one cost money in a different direction:

  * `days` was hardcoded to 30, so a six-month plan would have granted a month;
  * the end date was overwritten rather than extended, so renewing early threw
    away the days that were left;
  * every payment ran the provisioning path, so a renewal handed out a second
    peer and left it behind.

The tests are written against a real in-memory database. `issue_config` is the
only thing stubbed — it is the part that talks to a node over SSH.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from config import PLANS, config_limit, plan_info  # noqa: E402
from db.models import Config, Payment, User  # noqa: E402
from services import provisioner  # noqa: E402
from services.provisioner import activate_payment  # noqa: E402


NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


# ── the plan table ──────────────────────────────────────────────────────────

def test_every_plan_has_the_fields_activation_reads():
    for key, info in PLANS.items():
        assert set(info) >= {"tier", "configs", "days", "amount", "currency"}, key
        assert info["days"] in (30, 90, 180), key
        assert int(info["amount"]) > 0, key


def test_longer_periods_cost_less_per_month():
    """The discount is the reason the longer plans exist. Guard it."""
    for tier in ("basic", "ext"):
        monthly = int(PLANS[f"{tier}-1m"]["amount"]) / 30
        quarter = int(PLANS[f"{tier}-3m"]["amount"]) / 90
        half = int(PLANS[f"{tier}-6m"]["amount"]) / 180
        assert quarter < monthly, tier
        assert half < quarter, tier


def test_legacy_plan_names_still_resolve():
    """
    Payments created before periods existed can still be pending at a gateway,
    and users.plan holds the old name too. A KeyError inside a webhook would
    take a real payment with it.
    """
    assert plan_info("Basic")["days"] == 30
    assert plan_info("Family")["tier"] == "ext"


def test_unknown_plan_resolves_to_nothing():
    assert plan_info("nonsense") is None
    assert plan_info(None) is None


def test_config_limit_per_tier():
    assert config_limit("basic-6m") == 2
    assert config_limit("ext-1m") == 5


def test_unknown_plan_keeps_one_device_rather_than_none():
    """A customer whose plan name vanished should keep the device they have."""
    assert config_limit("nonsense") == 1
    assert config_limit(None) == 1


# ── activation ──────────────────────────────────────────────────────────────

@pytest.fixture
def issued(monkeypatch):
    """Stub the SSH path; record how many devices were handed out."""
    calls = []

    async def _fake(user, db, name="device"):
        calls.append(name)
        config = Config(
            id=str(uuid.uuid4()), user_id=user.id, name=name,
            peer_ip=f"10.88.88.{50 + len(calls)}",
            private_key="enc", public_key=f"PUB{len(calls)}", preshared_key="enc",
            is_active=True,
        )
        db.add(config)
        return config

    monkeypatch.setattr(provisioner, "issue_config", _fake)
    return calls


def _seed(db, plan, until=None, with_config=False):
    user = User(
        id=str(uuid.uuid4()), username="customer", email="c@example.test",
        password_hash="x", subscribed_until=until,
        is_subscribed=until is not None,
    )
    payment = Payment(
        id=str(uuid.uuid4()), user_id=user.id, plan=plan,
        amount=int(plan_info(plan)["amount"]) if plan_info(plan) else 0,
        status="pending",
    )
    db.add(user)
    db.add(payment)
    if with_config:
        db.add(Config(
            id=str(uuid.uuid4()), user_id=user.id, name="device-1",
            peer_ip="10.88.88.42", private_key="enc", public_key="PUBOLD",
            preshared_key="enc", is_active=True,
        ))
    db.run(db.commit())
    return user, payment


def test_six_month_plan_grants_six_months(db, issued):
    """The hardcoded 30 days is the bug this guards."""
    user, payment = _seed(db, "basic-6m")

    assert db.run(activate_payment(user, payment, db)) is True
    granted = (user.subscribed_until - NOW).days
    assert 179 <= granted <= 180
    assert payment.status == "paid"


def test_first_purchase_issues_exactly_one_device(db, issued):
    """Not the plan's whole limit — the rest are requested from the portal."""
    user, payment = _seed(db, "ext-6m")  # allows 5

    db.run(activate_payment(user, payment, db))
    assert issued == ["device-1"]


def test_renewal_extends_and_does_not_issue_another_peer(db, issued):
    """
    The two bugs together. Renewing 10 days before expiry must keep those 10
    days, and must not leave a second tunnel behind.
    """
    ends = NOW + timedelta(days=10)
    user, payment = _seed(db, "basic-1m", until=ends, with_config=True)

    db.run(activate_payment(user, payment, db))

    assert issued == [], "a renewal handed out another peer"
    assert (user.subscribed_until - ends).days == 30


def test_renewal_after_a_lapse_starts_from_now(db, issued):
    """Expired for a month: the new period runs from today, not from the past."""
    user, payment = _seed(db, "basic-1m", until=NOW - timedelta(days=30), with_config=True)

    db.run(activate_payment(user, payment, db))

    assert user.subscribed_until > NOW
    assert (user.subscribed_until - datetime.now(timezone.utc)).days >= 29


def test_upgrading_tier_raises_the_device_limit(db, issued):
    user, payment = _seed(db, "ext-3m", until=NOW + timedelta(days=5), with_config=True)

    db.run(activate_payment(user, payment, db))

    assert user.plan == "ext-3m"
    assert config_limit(user.plan) == 5
    assert issued == []


def test_unknown_plan_does_not_activate_anything(db, issued):
    """A plan name that no longer exists must not quietly grant a subscription."""
    user, payment = _seed(db, "nonsense")

    assert db.run(activate_payment(user, payment, db)) is False
    assert user.is_subscribed is False
    assert payment.status == "pending"
    assert issued == []


def test_failed_provisioning_leaves_the_payment_pending(db, monkeypatch):
    """
    The peer could not be created. Marking the payment paid here would produce
    a customer who owes nothing and has nothing, with no trace of why.
    """
    async def _fail(user, db, name="device"):
        return None

    monkeypatch.setattr(provisioner, "issue_config", _fail)
    user, payment = _seed(db, "basic-1m")

    assert db.run(activate_payment(user, payment, db)) is False
    assert payment.status == "pending"
    assert user.is_subscribed is False
