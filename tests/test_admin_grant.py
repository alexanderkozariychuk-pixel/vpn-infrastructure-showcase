"""
Opening access from the admin panel (api/admin_grant.py): the same activation
as a purchase, recorded as a zero-amount "manual" payment, never as revenue.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import admin_grant, config as config_api, register  # noqa: E402
from db.models import Config, Notification, Payment, PromoCode, User  # noqa: E402
from services import credit, mailer, provisioner  # noqa: E402

from tests.test_trial import _start, node  # noqa: E402,F401  (fixture)

NOW = datetime.now(timezone.utc)
ADMIN = {"sub": "admin", "role": "admin"}


@pytest.fixture
def letters(monkeypatch):
    sent = []

    async def fake_send(to, subject, html, text=""):
        sent.append((to, subject, html))
        return True
    monkeypatch.setattr(mailer, "send_email", fake_send)
    return sent


def _user(db, name="friend_1", **kw):
    kw.setdefault("email_verified_at", NOW)
    u = User(id=str(uuid.uuid4()), username=name, email=f"{name}@example.com", password_hash="x", **kw)
    db.add(u)
    db.run(db.commit())
    return u


def _grant(db, username="friend_1", plan="ext-6m"):
    out = db.run(admin_grant.grant(admin_grant.GrantRequest(username=username, plan=plan), db, ADMIN))
    db.run(mailer.drain())
    return out


def test_a_grant_opens_the_plan_with_its_device_limit_and_a_first_device(db, node, letters):
    u = _user(db)
    out = _grant(db)
    assert out["plan"] == "ext-6m" and out["devices"] == 5
    db.run(db.refresh(u))
    days = (provisioner._aware(u.subscribed_until) - NOW).total_seconds() / 86400
    assert 179.9 < days <= 180.1 and u.is_subscribed
    configs = db.run(db.execute(select(Config).where(Config.user_id == u.id))).scalars().all()
    assert [c.kind for c in configs] == ["paid"] and configs[0].peer_ip.startswith("10.88.88.")
    listed = db.run(config_api.list_configs(db, {"sub": u.username}))
    assert listed["limit"] == 5


def test_a_grant_is_recorded_as_zero_and_manual(db, node, letters):
    u = _user(db)
    _grant(db)
    pay = db.run(db.execute(select(Payment).where(Payment.user_id == u.id))).scalar_one()
    assert (pay.amount, pay.provider, pay.status) == (0, "manual", "paid")
    hist = db.run(register.my_payments(db, {"sub": u.username}))["payments"]
    assert hist[0]["granted"] is True


def test_the_customer_gets_an_access_letter_not_a_receipt(db, node, letters):
    _user(db)
    _grant(db)
    assert [s for _, s, _ in letters] == ["Доступ открыт — Sovereign"]
    assert "Оплачено" not in letters[0][2]


def test_the_bell_says_access_is_open(db, node, letters):
    u = _user(db)
    _grant(db)
    n = db.run(db.execute(select(Notification).where(Notification.user_id == u.id))).scalar_one()
    assert n.kind == "granted" and n.title == "Доступ открыт" and n.link == "config"


def test_a_grant_on_top_of_paid_days_keeps_them(db, node, letters):
    u = _user(db, is_subscribed=True, plan="basic-1m", subscribed_until=NOW + timedelta(days=10))
    _grant(db, plan="ext-1m")
    db.run(db.refresh(u))
    days = (provisioner._aware(u.subscribed_until) - NOW).total_seconds() / 86400
    assert 39.9 < days <= 40.1


def test_a_grant_ends_a_running_trial(db, node, letters, monkeypatch):
    monkeypatch.setenv("TRIAL_ENABLED", "1")
    u = _user(db)
    trial_ip = _start(db, u)["config"]["peer_ip"]
    _grant(db)
    assert trial_ip not in node.peers.values()


def test_a_grant_earns_no_referral_reward(db, node, letters):
    referrer = _user(db, "ref_1")
    db.add(PromoCode(code="REF1", owner_user_id=referrer.id))
    u = _user(db)
    db.run(db.commit())
    _grant(db)
    # Even if the row carried a code, a zero-cash payment rewards nothing.
    pay = db.run(db.execute(select(Payment).where(Payment.user_id == u.id))).scalar_one()
    pay.promo_code = "REF1"
    assert db.run(credit.reward_for_payment(db, pay)) == 0


@pytest.mark.parametrize("plan", ["ext-7m", "", "pro"])
def test_only_current_plans(db, plan):
    _user(db)
    with pytest.raises(HTTPException) as e:
        _grant(db, plan=plan)
    assert e.value.status_code == 422


def test_unknown_user(db):
    with pytest.raises(HTTPException) as e:
        _grant(db, username="nobody")
    assert e.value.status_code == 404


def test_disabled_account(db):
    _user(db, is_active=False)
    with pytest.raises(HTTPException) as e:
        _grant(db)
    assert e.value.status_code == 409


def test_if_no_device_can_be_issued_nothing_is_granted(db, node, letters, monkeypatch):
    u = _user(db)
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", lambda *a: (False, "node down"))
    with pytest.raises(HTTPException) as e:
        _grant(db)
    assert e.value.status_code == 502
    db.run(db.refresh(u))
    assert not u.is_subscribed and u.subscribed_until is None
    assert db.run(db.execute(select(Payment))).scalars().all() == []
    assert letters == []


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_the_access_letter_follows_the_letter_rules(lang):
    subject, html, text = mailer.granted_email("<b>x</b>", "ext", 180, NOW, True, lang)
    assert subject.endswith("— Sovereign")
    assert html.count(f"{mailer.SITE_URL}/app") >= 2 and f"{mailer.SITE_URL}/app" in text
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<" not in mailer.granted_email("friend_1", "ext", 180, NOW, True, lang)[2]
    assert ("You received this" if lang == "en" else "Вы получили это письмо") in html
