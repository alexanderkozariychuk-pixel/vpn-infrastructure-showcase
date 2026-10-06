"""
The bell: what goes into a customer's feed, when, and which of it also goes
by email (services/notify.py, api/notifications.py).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import notifications as api  # noqa: E402
from config import plan_info  # noqa: E402
from db.models import Config, Notification, Payment, User  # noqa: E402
from services import mailer, notify, provisioner, ratelimit, subscriptions  # noqa: E402

from tests.test_trial import _start, node  # noqa: E402,F401  (fixture)

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TRIAL_ENABLED", "1")
    for lim in ratelimit.ALL:
        lim.reset()
    yield
    for lim in ratelimit.ALL:
        lim.reset()


@pytest.fixture
def letters(monkeypatch):
    sent = []

    async def fake_send(to, subject, html, text=""):
        sent.append((to, subject))
        return True
    monkeypatch.setattr(mailer, "send_email", fake_send)
    return sent


def _user(db, name="ivan_1", **kw):
    kw.setdefault("email_verified_at", NOW)
    u = User(id=str(uuid.uuid4()), username=name, email=f"{name}@example.com", password_hash="x", **kw)
    db.add(u)
    db.run(db.commit())
    return u


def _feed(db, user):
    return db.run(api.list_notifications(db, {"sub": user.username}))


def _kinds(db, user):
    return [i["kind"] for i in _feed(db, user)["items"]]


def _remind(db, now=NOW):
    out = db.run(notify.remind_due(db, now))
    db.run(mailer.drain())
    return out


# ── reminders ────────────────────────────────────────────────────────────

def test_three_days_before_the_end_a_message_and_a_letter(db, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW + timedelta(days=2, hours=12))
    assert _remind(db)["reminders"] == 1
    assert _kinds(db, u) == ["sub_ends_3d"]
    assert letters == [("ivan_1@example.com", "Подписка заканчивается через 3 дня — Sovereign")]


def test_the_hourly_job_repeating_gives_one_message(db, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW + timedelta(days=2))
    _remind(db)
    _remind(db, NOW + timedelta(hours=1))
    _remind(db, NOW + timedelta(hours=2))
    assert _kinds(db, u) == ["sub_ends_3d"]
    assert len(letters) == 1


def test_one_day_before_a_second_message_but_no_second_letter(db, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW + timedelta(days=2, hours=12))
    _remind(db)
    _remind(db, NOW + timedelta(days=1, hours=13))
    assert sorted(_kinds(db, u)) == ["sub_ends_1d", "sub_ends_3d"]
    assert len(letters) == 1


def test_nothing_while_more_than_three_days_are_left(db, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW + timedelta(days=3, hours=1))
    assert _remind(db)["reminders"] == 0
    assert _kinds(db, u) == [] and letters == []


def test_a_renewed_period_gets_its_own_reminders(db, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW + timedelta(days=2))
    _remind(db)
    u.subscribed_until = NOW + timedelta(days=32)
    db.run(db.commit())
    _remind(db, NOW + timedelta(days=30))
    assert _kinds(db, u) == ["sub_ends_3d", "sub_ends_3d"]
    assert len(letters) == 2


def test_a_trial_with_under_a_day_left_gets_a_message_and_a_letter(db, letters):
    u = _user(db, trial_until=NOW + timedelta(hours=20))
    _remind(db)
    assert _kinds(db, u) == ["trial_ends_1d"]
    assert letters == [("ivan_1@example.com", "Пробный период заканчивается — Sovereign")]


def test_no_trial_reminder_for_someone_who_has_already_paid(db, letters):
    u = _user(db, trial_until=NOW + timedelta(hours=20),
              is_subscribed=True, subscribed_until=NOW + timedelta(days=30))
    _remind(db)
    assert _kinds(db, u) == [] and letters == []


def test_reminders_are_in_the_account_language(db, letters):
    u = _user(db, lang="en", is_subscribed=True, subscribed_until=NOW + timedelta(days=2))
    _remind(db)
    item = _feed(db, u)["items"][0]
    assert item["title"] == "Your subscription ends in 3 days"
    assert letters[0][1] == "Your subscription ends in 3 days — Sovereign"


# ── ends ─────────────────────────────────────────────────────────────────

def test_an_ended_subscription_is_in_the_bell_and_in_the_mail(db, node, letters):
    u = _user(db, is_subscribed=True, subscribed_until=NOW - timedelta(minutes=5))
    db.run(subscriptions.expire_due_subscriptions(db))
    db.run(mailer.drain())
    assert _kinds(db, u) == ["sub_ended"]
    assert letters == [("ivan_1@example.com", "Подписка закончилась — Sovereign")]
    db.run(subscriptions.expire_due_subscriptions(db))
    assert _kinds(db, u) == ["sub_ended"]


def test_an_ended_trial_is_in_the_bell_only(db, node, letters):
    u = _user(db)
    _start(db, u)
    u.trial_until = NOW - timedelta(minutes=1)
    db.run(db.commit())
    db.run(subscriptions.expire_due_trials(db))
    db.run(mailer.drain())
    assert _kinds(db, u) == ["trial_ended", "trial_started"]
    assert letters == []


def test_a_trial_cut_short_by_a_purchase_does_not_say_it_ended(db, node, letters, monkeypatch):
    u = _user(db)
    _start(db, u)
    # The node refuses at purchase time; the sweep removes the peer later.
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", lambda pub: (False, "down"))
    pay = Payment(id=str(uuid.uuid4()), user_id=u.id, plan="basic-1m",
                  amount=int(plan_info("basic-1m")["amount"]), currency="RUB", status="pending")
    db.add(pay)
    db.run(db.commit())
    assert db.run(provisioner.activate_payment(u, pay, db)) is True
    db.run(subscriptions.expire_due_trials(db))
    db.run(mailer.drain())
    assert "trial_ended" not in _kinds(db, u)
    assert "paid" in _kinds(db, u)


# ── events ───────────────────────────────────────────────────────────────

def test_a_payment_puts_a_message_in_the_bell(db, node, letters):
    u = _user(db)
    pay = Payment(id=str(uuid.uuid4()), user_id=u.id, plan="basic-1m",
                  amount=int(plan_info("basic-1m")["amount"]), currency="RUB", status="pending")
    db.add(pay)
    db.run(db.commit())
    db.run(provisioner.activate_payment(u, pay, db))
    db.run(mailer.drain())
    item = _feed(db, u)["items"][0]
    assert item["kind"] == "paid" and item["link"] == "config" and not item["read"]


def test_starting_a_trial_puts_a_message_in_the_bell(db, node):
    u = _user(db)
    _start(db, u)
    item = _feed(db, u)["items"][0]
    assert item["kind"] == "trial_started" and " в " in item["body"]


# ── the feed ─────────────────────────────────────────────────────────────

def _add(db, user, n=1):
    for i in range(n):
        db.add(Notification(user_id=user.id, kind="service", title=f"t{i}", body="b",
                            created_at=NOW + timedelta(seconds=i)))
    db.run(db.commit())


def test_each_customer_sees_only_their_own_feed(db):
    a, b = _user(db, "ivan_1"), _user(db, "petr_2")
    _add(db, a, 2)
    assert _feed(db, b) == {"items": [], "unread": 0}
    assert _feed(db, a)["unread"] == 2


def test_newest_first_and_capped(db):
    u = _user(db)
    _add(db, u, api.FEED_SIZE + 5)
    feed = _feed(db, u)
    assert len(feed["items"]) == api.FEED_SIZE
    assert feed["items"][0]["title"] == f"t{api.FEED_SIZE + 4}"
    assert feed["unread"] == api.FEED_SIZE + 5


def test_mark_all_read(db):
    u = _user(db)
    _add(db, u, 3)
    out = db.run(api.mark_read(api.ReadRequest(), db, {"sub": u.username}))
    assert out["marked"] == 3 and _feed(db, u)["unread"] == 0


def test_mark_some_read(db):
    u = _user(db)
    _add(db, u, 3)
    first = _feed(db, u)["items"][0]["id"]
    db.run(api.mark_read(api.ReadRequest(ids=[first]), db, {"sub": u.username}))
    assert _feed(db, u)["unread"] == 2


def test_one_customer_cannot_mark_anothers_messages(db):
    a, b = _user(db, "ivan_1"), _user(db, "petr_2")
    _add(db, a, 1)
    nid = _feed(db, a)["items"][0]["id"]
    out = db.run(api.mark_read(api.ReadRequest(ids=[nid]), db, {"sub": b.username}))
    assert out["marked"] == 0 and _feed(db, a)["unread"] == 1


def test_a_broadcast_reaches_every_active_account(db):
    a, b = _user(db, "ivan_1"), _user(db, "petr_2")
    _user(db, "gone_3", is_active=False)
    out = db.run(api.broadcast(api.BroadcastRequest(title="Работы", body="Сегодня ночью"), db, {}))
    assert out == {"sent": 2}
    assert _feed(db, a)["items"][0]["title"] == "Работы" and _feed(db, b)["unread"] == 1


def test_a_deleted_accounts_feed_goes_with_it():
    # The test database is SQLite without foreign keys; the cascade is
    # Postgres's job, so check it is asked for, in the model and the migration.
    from pathlib import Path
    fk = next(iter(Notification.__table__.c.user_id.foreign_keys))
    assert fk.ondelete == "CASCADE"
    mig = Path(__file__).parent.parent / "pwa" / "alembic" / "versions" / "a7d2e5c94f18_add_notifications.py"
    assert "ondelete='CASCADE'" in mig.read_text()


# ── the portal ───────────────────────────────────────────────────────────

def test_in_the_account_the_corner_is_the_bell_and_elsewhere_the_gear():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "pwa" / "static" / "index.html").read_text()
    assert 'body[data-view="dashboard"] #settings-btn { display: none; }' in html
    assert 'body:not([data-view="dashboard"]) .notif-btn' in html
    assert "document.body.dataset.view = view;" in html
    # Messages are drawn escaped: a broadcast is operator text, but still text.
    assert "${escHtml(n.title)}" in html and "${escHtml(n.body)}" in html
