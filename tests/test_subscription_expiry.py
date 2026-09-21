"""
Subscriptions that end.

`subscribed_until` was written at payment time and never read. Access was gated
on a boolean that nothing ever set back to False, and no code anywhere removed
a peer from a node — so one payment bought permanent access and the difference
between a one-month and a six-month plan was decorative.

Two invariants matter here and both are tested against the real thing rather
than a mock:

  * the gate fails closed — expired, and missing end date, are both refusals;
  * the sweep only records a revocation the node actually confirmed. Marking a
    row revoked while the peer still carries traffic produces exactly the kind
    of state nobody thinks to look for.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from db.models import Config, User  # noqa: E402
from services import subscriptions  # noqa: E402
from services.subscriptions import expire_due_subscriptions, has_active_subscription  # noqa: E402


# Frozen on purpose, and correct here: everything under test takes `now` as an
# argument, so no system clock is involved and the result is the same on any
# day. Where a function reads the clock itself — activate_payment does — the
# anchor has to be the real clock instead, or the expected values drift by a
# day for every day that passes.
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


# ── the gate ────────────────────────────────────────────────────────────────

def _user(**kw) -> User:
    base = dict(username="customer", email="c@example.test", password_hash="x")
    base.update(kw)
    return User(**base)


def test_active_subscription_passes():
    u = _user(is_subscribed=True, subscribed_until=NOW + timedelta(days=1))
    assert has_active_subscription(u, now=NOW) is True


def test_expired_subscription_is_refused():
    """The whole bug: the flag is still True, the paid period is over."""
    u = _user(is_subscribed=True, subscribed_until=NOW - timedelta(seconds=1))
    assert has_active_subscription(u, now=NOW) is False


def test_missing_end_date_is_refused():
    """
    'No end date recorded' must not read as 'no end date exists'. Rows reach
    this state through the admin path, and reading it as permanent access is
    how a free subscription gets granted by accident.
    """
    u = _user(is_subscribed=True, subscribed_until=None)
    assert has_active_subscription(u, now=NOW) is False


def test_flag_cleared_is_refused_even_with_a_future_date():
    u = _user(is_subscribed=False, subscribed_until=NOW + timedelta(days=30))
    assert has_active_subscription(u, now=NOW) is False


# ── the sweep ───────────────────────────────────────────────────────────────

def _seed(db, username, until, n_configs=1):
    # The id default fires at flush, so it is set here: the Config rows need
    # to reference it before anything reaches the database.
    user = User(
        id=str(uuid.uuid4()),
        username=username, email=f"{username}@example.test", password_hash="x",
        is_subscribed=True, subscribed_until=until,
    )
    db.add(user)
    configs = [
        Config(
            user_id=user.id, name="Basic", peer_ip=f"10.88.88.{40 + i}",
            private_key="enc", public_key=f"PUB{username}{i}", preshared_key="enc",
            is_active=True,
        )
        for i in range(n_configs)
    ]
    for c in configs:
        db.add(c)
    return user, configs


def test_expired_user_is_revoked_and_peers_removed(db, monkeypatch):
    removed = []
    monkeypatch.setattr(
        subscriptions, "_remove_peer_from_bridge",
        lambda pub: (removed.append(pub), (True, "ok"))[1],
    )

    user, _ = _seed(db, "expired", NOW - timedelta(days=1), n_configs=2)
    db.run(db.commit())

    stats = db.run(expire_due_subscriptions(db, now=NOW))

    assert stats["users_revoked"] == 1
    assert stats["peers_removed"] == 2
    assert len(removed) == 2
    assert user.is_subscribed is False


def test_still_paid_user_is_left_alone(db, monkeypatch):
    monkeypatch.setattr(
        subscriptions, "_remove_peer_from_bridge",
        lambda pub: pytest.fail(f"revoked a paying customer's peer: {pub}"),
    )

    user, _ = _seed(db, "paying", NOW + timedelta(days=5))
    db.run(db.commit())

    stats = db.run(expire_due_subscriptions(db, now=NOW))

    assert stats["users_due"] == 0
    assert user.is_subscribed is True


def test_failed_removal_leaves_the_row_active_for_the_next_run(db, monkeypatch):
    """
    The important one. If the node refuses or is unreachable, the peer is still
    carrying traffic — so the row must stay active and the user stay subscribed,
    and the next hourly run tries again. Recording a revocation that did not
    happen is worse than not revoking.
    """
    monkeypatch.setattr(
        subscriptions, "_remove_peer_from_bridge",
        lambda pub: (False, "error: peer not found in runtime or config"),
    )

    user, configs = _seed(db, "stuck", NOW - timedelta(days=1))
    db.run(db.commit())

    stats = db.run(expire_due_subscriptions(db, now=NOW))

    assert stats["failures"] == 1
    assert stats["users_revoked"] == 0
    assert stats["peers_removed"] == 0
    assert user.is_subscribed is True
    assert configs[0].is_active is True


def test_partial_failure_does_not_half_revoke_the_user(db, monkeypatch):
    """
    Two peers, one removal fails. The peer that did come off is recorded as
    inactive — it is genuinely gone — but the account stays subscribed, because
    one of its tunnels still works.
    """
    calls = {"n": 0}

    def _flaky(pub):
        calls["n"] += 1
        return (True, "ok") if calls["n"] == 1 else (False, "error: unreachable")

    monkeypatch.setattr(subscriptions, "_remove_peer_from_bridge", _flaky)

    user, configs = _seed(db, "partial", NOW - timedelta(days=2), n_configs=2)
    db.run(db.commit())

    stats = db.run(expire_due_subscriptions(db, now=NOW))

    assert stats["peers_removed"] == 1
    assert stats["failures"] == 1
    assert stats["users_revoked"] == 0
    assert user.is_subscribed is True
    assert sorted(c.is_active for c in configs) == [False, True]


def test_undated_subscribers_are_reported_not_revoked(db, monkeypatch):
    """An active flag with no end date is a data problem, not an expiry."""
    monkeypatch.setattr(
        subscriptions, "_remove_peer_from_bridge",
        lambda pub: pytest.fail("touched an undated subscriber"),
    )

    user, _ = _seed(db, "undated", None)
    db.run(db.commit())

    stats = db.run(expire_due_subscriptions(db, now=NOW))

    assert stats["users_due"] == 0
    assert stats["undated"] == ["undated"]
    assert user.is_subscribed is True
