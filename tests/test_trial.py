"""
The free trial: who gets one, what it is, how it ends.

One device for TRIAL_DAYS in the trial subnet, once per mailbox, for
confirmed addresses only, never after a purchase. The node side (subnet,
ceiling, kill switch) is tested in tests/infrastructure.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import config as config_api, register, trial as trial_api  # noqa: E402
from config import plan_info  # noqa: E402
from db.models import Config, Payment, TrialGrant, User  # noqa: E402
from services import mailer, provisioner, ratelimit, subscriptions  # noqa: E402
from services import trial as trial_svc  # noqa: E402

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
def node(monkeypatch):
    """The entry node, faked: peers by public key, and what was asked of it."""
    peers = {}
    calls = {"add": [], "remove": []}
    counter = iter(range(1, 10_000))

    def add(pub, psk, ip, name):
        calls["add"].append((ip, name))
        peers[pub] = ip
        return True, "ok"

    def remove(pub):
        calls["remove"].append(pub)
        if pub in peers:
            del peers[pub]
            return True, "ok"
        return False, "no such peer"

    monkeypatch.setattr(provisioner, "_bridge_used_ips", lambda: set(peers.values()))
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", add)
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", remove)
    monkeypatch.setattr(subscriptions, "_remove_peer_from_bridge", remove)
    monkeypatch.setattr(provisioner, "_awg_genkey", lambda: f"PRIV{next(counter)}")
    monkeypatch.setattr(provisioner, "_awg_pubkey", lambda priv: "PUB" + priv[4:])
    monkeypatch.setattr(provisioner, "_awg_genpsk", lambda: "PSK")
    return SimpleNamespace(peers=peers, calls=calls)


def _req(ip="198.51.100.7"):
    return SimpleNamespace(headers={"x-real-ip": ip}, client=None)


def _user(db, name="ivan_1", email=None, verified=True, **kw):
    u = User(id=str(uuid.uuid4()), username=name, email=email or f"{name}@example.com",
             password_hash="x", email_verified_at=NOW if verified else None, **kw)
    db.add(u)
    db.run(db.commit())
    return u


def _start(db, user, ip="198.51.100.7"):
    return db.run(trial_api.start_trial(_req(ip), db, {"sub": user.username}))


def _refused(db, user, ip="198.51.100.7"):
    with pytest.raises(HTTPException) as e:
        _start(db, user, ip)
    return e.value.status_code, e.value.detail


# ── what a trial is ──────────────────────────────────────────────────────

def test_a_trial_is_one_device_in_the_trial_subnet_for_the_trial_period(db, node):
    user = _user(db)
    out = _start(db, user)
    assert out["config"]["peer_ip"].startswith("10.88.89.")
    assert out["config"]["kind"] == "trial"
    assert node.calls["add"] == [(out["config"]["peer_ip"], "trial-ivan_1")]
    db.run(db.refresh(user))
    days = (trial_svc._aware(user.trial_until) - NOW).total_seconds() / 86400
    assert trial_svc.TRIAL_DAYS - 0.01 < days <= trial_svc.TRIAL_DAYS + 0.01


def test_a_paid_device_never_comes_from_the_trial_subnet(db, node):
    user = _user(db)
    cfg = db.run(provisioner.issue_config(user, db, name="p1"))
    assert cfg.peer_ip.startswith("10.88.88.") and cfg.kind == "paid"


def test_the_trial_device_can_be_downloaded(db, node):
    user = _user(db)
    cid = _start(db, user)["config"]["id"]
    text = db.run(config_api.config_raw(cid, db, {"sub": user.username})).body.decode()
    assert "Address = 10.88.89." in text


def test_a_trial_alone_cannot_add_devices(db, node):
    user = _user(db)
    _start(db, user)
    with pytest.raises(HTTPException) as e:
        db.run(config_api.add_config(config_api.NewConfigRequest(name="pc"), db, {"sub": user.username}))
    assert e.value.status_code == 402


def test_the_trial_device_cannot_be_deleted(db, node):
    user = _user(db)
    cid = _start(db, user)["config"]["id"]
    with pytest.raises(HTTPException) as e:
        db.run(config_api.delete_config(cid, db, {"sub": user.username}))
    assert e.value.status_code == 409


def test_the_device_list_during_a_trial_shows_one_slot(db, node):
    user = _user(db)
    _start(db, user)
    out = db.run(config_api.list_configs(db, {"sub": user.username}))
    assert out["limit"] == 1 and out["used"] == 1
    assert out["configs"][0]["kind"] == "trial"


# ── who may have one ─────────────────────────────────────────────────────

def test_an_unconfirmed_address_gets_no_trial(db, node):
    assert _refused(db, _user(db, verified=False)) == (403, "email_not_verified")
    assert node.calls["add"] == []


def test_trials_can_be_switched_off(db, node, monkeypatch):
    monkeypatch.setenv("TRIAL_ENABLED", "0")
    assert _refused(db, _user(db)) == (403, "trial_off")


def test_one_trial_per_account(db, node):
    user = _user(db)
    _start(db, user)
    assert _refused(db, user) == (409, "trial_active")
    user.trial_until = NOW - timedelta(hours=1)
    db.run(db.commit())
    assert _refused(db, user) == (409, "trial_used")


@pytest.mark.parametrize("second", [
    "IvanPetrov@gmail.com",        # case and a dot Gmail ignores
    "ivanpetrov+vpn@googlemail.com",  # tag and Gmail's other domain
])
def test_one_trial_per_mailbox_across_accounts(db, node, second):
    _start(db, _user(db, "first", email="ivan.petrov@gmail.com"))
    assert _refused(db, _user(db, "second", email=second.lower())) == (409, "trial_used")


def test_deleting_the_account_does_not_free_the_mailbox_for_another_trial(db, node):
    first = _user(db, "first", email="ivan@example.com")
    _start(db, first)
    for c in db.run(db.execute(select(Config))).scalars().all():
        db.run(db.delete(c))
    db.run(db.delete(first))
    db.run(db.commit())
    again = _user(db, "again", email="ivan@example.com")
    assert _refused(db, again) == (409, "trial_used")


def test_dots_are_kept_where_the_provider_does_not_ignore_them():
    assert trial_svc.normalise_email("i.van@yandex.ru") != trial_svc.normalise_email("iv.an@yandex.ru")
    assert trial_svc.normalise_email("ivan+x@ya.ru") == "ivan@yandex.ru"


def test_no_trial_after_paying(db, node):
    user = _user(db, subscribed_until=NOW - timedelta(days=3))
    assert _refused(db, user) == (409, "trial_used")


def test_throwaway_mailboxes_get_no_trial(db, node):
    assert _refused(db, _user(db, email="x@mailinator.com")) == (403, "trial_unavailable")
    assert _refused(db, _user(db, "y_1", email="x@eu.yopmail.com")) == (403, "trial_unavailable")


def test_trials_from_one_address_are_limited(db, node):
    for i in range(ratelimit.TRIAL_PER_IP.limit):
        _start(db, _user(db, f"u_{i}"), ip="203.0.113.5")
    status, _ = _refused(db, _user(db, "u_late"), ip="203.0.113.5")
    assert status == 429


def test_the_daily_ceiling_holds(db, node, monkeypatch):
    monkeypatch.setattr(trial_api, "TRIAL_DAILY_CAP", 2)
    _start(db, _user(db, "a_1"), ip="203.0.113.1")
    _start(db, _user(db, "a_2"), ip="203.0.113.2")
    assert _refused(db, _user(db, "a_3"), ip="203.0.113.3") == (503, "trial_busy")


def test_a_node_failure_does_not_spend_the_trial(db, node, monkeypatch):
    user = _user(db)
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", lambda *a: (False, "boom"))
    assert _refused(db, user) == (503, "trial_busy")
    db.run(db.refresh(user))
    assert user.trial_until is None
    assert db.run(db.execute(select(TrialGrant))).scalars().all() == []
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", lambda *a: (True, "ok"))
    assert _start(db, user)["ok"] is True


# ── what the portal is told ──────────────────────────────────────────────

def _state(db, user):
    return db.run(register.get_me(db, {"sub": user.username}))["trial"]["state"]


def test_the_profile_says_what_to_offer(db, node, monkeypatch):
    assert _state(db, _user(db, "n_1", verified=False)) == "needs_verify"
    fresh = _user(db, "n_2")
    assert _state(db, fresh) == "available"
    _start(db, fresh)
    assert _state(db, fresh) == "active"
    assert _state(db, _user(db, "n_3", subscribed_until=NOW)) == "used"
    monkeypatch.setenv("TRIAL_ENABLED", "0")
    assert _state(db, _user(db, "n_4")) == "off"


# ── how it ends ──────────────────────────────────────────────────────────

def test_the_sweep_takes_ended_trials_off_the_node(db, node):
    user = _user(db)
    _start(db, user)
    assert len(node.peers) == 1
    user.trial_until = NOW - timedelta(minutes=1)
    db.run(db.commit())
    stats = db.run(subscriptions.expire_due_trials(db))
    assert stats["trial_peers_removed"] == 1 and node.peers == {}
    cfg = db.run(db.execute(select(Config))).scalar_one()
    assert cfg.is_active is False
    with pytest.raises(HTTPException) as e:
        db.run(config_api.list_configs(db, {"sub": user.username}))
    assert e.value.status_code == 402


def test_the_sweep_leaves_running_trials_alone(db, node):
    _start(db, _user(db))
    assert db.run(subscriptions.expire_due_trials(db))["trials_due"] == 0
    assert len(node.peers) == 1


def test_a_purchase_during_a_trial_is_a_first_purchase_and_ends_the_trial(db, node, monkeypatch):
    sent = []

    async def fake_send(to, subject, html, text=""):
        sent.append(html)
        return True
    monkeypatch.setattr(mailer, "send_email", fake_send)

    user = _user(db)
    trial_cfg = _start(db, user)["config"]
    pay = Payment(id=str(uuid.uuid4()), user_id=user.id, plan="basic-1m",
                  amount=int(plan_info("basic-1m")["amount"]), currency="RUB", status="pending")
    db.add(pay)
    db.run(db.commit())

    assert db.run(provisioner.activate_payment(user, pay, db)) is True
    db.run(mailer.drain())

    configs = db.run(db.execute(select(Config).where(Config.is_active.is_(True)))).scalars().all()
    assert [c.kind for c in configs] == ["paid"]
    assert configs[0].peer_ip.startswith("10.88.88.")
    assert trial_cfg["peer_ip"] not in node.peers.values()
    db.run(db.refresh(user))
    assert not trial_svc.trial_active(user)
    assert any("Первое устройство уже создано" in h for h in sent)


def test_if_the_trial_peer_cannot_be_removed_at_purchase_the_sweep_finishes_it(db, node, monkeypatch):
    user = _user(db)
    _start(db, user)
    pay = Payment(id=str(uuid.uuid4()), user_id=user.id, plan="basic-1m",
                  amount=350, currency="RUB", status="pending")
    db.add(pay)
    db.run(db.commit())
    real_remove = provisioner._remove_peer_from_bridge
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", lambda pub: (False, "unreachable"))
    assert db.run(provisioner.activate_payment(user, pay, db)) is True
    db.run(mailer.drain())
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", real_remove)
    assert db.run(subscriptions.expire_due_trials(db))["trial_peers_removed"] == 1
    kinds = sorted(c.kind for c in db.run(db.execute(
        select(Config).where(Config.is_active.is_(True)))).scalars().all())
    assert kinds == ["paid"]
