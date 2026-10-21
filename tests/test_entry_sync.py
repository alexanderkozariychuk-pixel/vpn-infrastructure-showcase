"""
The standby entry (B) gets every portal peer change A gets — additions and
removals — through jobs written in the same transaction, run from cron.

What is relied on:
  * with ENTRY_B_IP unset nothing is written and nothing runs: the portal is
    what it was before stage 4;
  * A is still written in the request and still decides: a refusal from A
    means no device and no job, a removal A did not confirm leaves no job;
  * every change committed on A has its job; the jobs reach B in order, and
    a lost answer retried is not an error;
  * an address B still holds is not handed out again;
  * a backlog older than an hour is one letter, and one all-clear.
"""

import os
import shlex
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import config as config_api, trial as trial_api  # noqa: E402
from config import plan_info  # noqa: E402
from db.models import Config, EntrySync, MonitorEvent, Payment, User  # noqa: E402
from services import entry_sync, mailer, provisioner, ratelimit, subscriptions  # noqa: E402

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("ENTRY_B_IP", raising=False)
    monkeypatch.setenv("TRIAL_ENABLED", "1")
    for lim in ratelimit.ALL:
        lim.reset()
    yield
    for lim in ratelimit.ALL:
        lim.reset()


@pytest.fixture
def a(monkeypatch):
    """Entry A, faked as in tests/test_trial.py: peers by key; .ok = False refuses."""
    st = SimpleNamespace(peers={}, ok=True)
    counter = iter(range(1, 10_000))

    def add(pub, psk, ip, name):
        if not st.ok:
            return False, "node unreachable"
        st.peers[pub] = ip
        return True, "ok"

    def remove(pub):
        if not st.ok or pub not in st.peers:
            return False, "node unreachable"
        del st.peers[pub]
        return True, "ok"

    monkeypatch.setattr(provisioner, "_bridge_used_ips", lambda: set(st.peers.values()))
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", add)
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", remove)
    monkeypatch.setattr(subscriptions, "_remove_peer_from_bridge", remove)
    monkeypatch.setattr(config_api, "_remove_peer_from_bridge", remove)
    monkeypatch.setattr(provisioner, "_awg_genkey", lambda: f"PRIV{next(counter):040d}")
    monkeypatch.setattr(provisioner, "_awg_pubkey", lambda priv: "PUB" + priv[4:])
    monkeypatch.setattr(provisioner, "_awg_genpsk", lambda: "PSK-SECRET")
    return st


@pytest.fixture
def b(monkeypatch):
    """
    Entry B behind `ssh`, answering like the real wrappers do.
    mode: "up"; "down" (ssh fails); "refuse" (wrapper says no);
    "lose" (does the work, then the connection drops).
    """
    st = SimpleNamespace(peers={}, mode="up", calls=[])

    def ssh(host, cmd, timeout=15):
        st.calls.append((host, cmd))
        if st.mode == "down":
            raise entry_sync.Unreachable("Connection timed out")
        if st.mode == "refuse":
            return "", "error: refusing for the test"
        argv = shlex.split(cmd)
        assert argv[0] == "sudo"
        if argv[1] == "pwa-add-peer":
            pub, psk, ip, name = argv[2:]
            if pub in st.peers:
                return "", "peer exists (key)"
            if any(p["ip"] == ip for p in st.peers.values()):
                return "", f"ip in use: {ip}"
            st.peers[pub] = {"ip": ip, "psk": psk, "name": name}
            out = f"ok: added {name} ({ip})"
        elif argv[1] == "pwa-del-peer":
            pub = argv[2]
            if pub not in st.peers:
                return "", "error: peer not found in runtime or config"
            del st.peers[pub]
            out = "ok: removed"
        else:
            raise AssertionError(cmd)
        if st.mode == "lose":
            raise entry_sync.Unreachable("Connection reset")
        return out, ""

    monkeypatch.setattr(entry_sync, "_ssh", ssh)
    return st


def _on(monkeypatch):
    monkeypatch.setenv("ENTRY_B_IP", "192.0.2.20")


def _user(db, name="ivan_1", **kw):
    base = dict(id=str(uuid.uuid4()), username=name, email=f"{name}@example.com",
                password_hash="x", email_verified_at=NOW, plan="basic-1m",
                is_subscribed=True, subscribed_until=NOW + timedelta(days=30))
    base.update(kw)
    u = User(**base)
    db.add(u)
    db.run(db.commit())
    return u


def _add(db, user, name="phone"):
    return db.run(config_api.add_config(config_api.NewConfigRequest(name=name), db,
                                        {"sub": user.username}))["config"]


def _jobs(db, done=None):
    q = select(EntrySync).order_by(EntrySync.id)
    if done is False:
        q = q.where(EntrySync.done_at.is_(None))
    return db.run(db.execute(q)).scalars().all()


def _req(ip="198.51.100.7"):
    return SimpleNamespace(headers={"x-real-ip": ip}, client=None)


# ── without B: as before ─────────────────────────────────────────────────

def test_without_b_nothing_is_written_and_nothing_runs(db, a, b):
    user = _user(db)
    dev = _add(db, user)
    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    user.subscribed_until = NOW - timedelta(minutes=1)
    db.run(db.commit())
    db.run(subscriptions.expire_due_subscriptions(db))
    assert _jobs(db) == []
    assert db.run(entry_sync.run(db)) == {"done": 0, "skipped": 0, "failed": 0, "unreachable": []}
    assert db.run(entry_sync.watch(db)) == "off"
    assert b.calls == []


# ── jobs follow A's committed changes ────────────────────────────────────

def test_a_device_issued_on_a_is_owed_to_b(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    [job] = _jobs(db)
    assert (job.entry, job.action, job.config_id, job.peer_ip) == ("b", "add", dev["id"], dev["peer_ip"])
    assert job.public_key in a.peers and job.done_at is None
    assert b.calls == []        # nothing reaches B in the request


def test_a_refusal_from_a_means_no_device_and_no_job(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    a.ok = False
    with pytest.raises(HTTPException):
        _add(db, user)
    assert _jobs(db) == []


def test_removal_is_owed_to_b_only_once_a_confirmed_it(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    a.ok = False
    with pytest.raises(HTTPException):
        db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    assert [j.action for j in _jobs(db)] == ["add"]
    a.ok = True
    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    assert [j.action for j in _jobs(db)] == ["add", "remove"]


def test_the_end_of_a_paid_period_is_owed_to_b(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    _add(db, user)
    _add(db, user, "laptop")
    user.subscribed_until = NOW - timedelta(minutes=1)
    db.run(db.commit())
    db.run(subscriptions.expire_due_subscriptions(db))
    assert [j.action for j in _jobs(db)] == ["add", "add", "remove", "remove"]


def test_the_end_of_a_trial_and_a_trial_ended_by_purchase_are_owed_to_b(db, a, b, monkeypatch):
    _on(monkeypatch)
    sent = []

    async def fake_send(to, subject, html, text=""):
        sent.append(subject)
        return True
    monkeypatch.setattr(mailer, "send_email", fake_send)

    # Ended by time.
    one = _user(db, "trial_1", is_subscribed=False, subscribed_until=None, plan=None)
    db.run(trial_api.start_trial(_req(), db, {"sub": one.username}))
    one.trial_until = NOW - timedelta(minutes=1)
    db.run(db.commit())
    db.run(subscriptions.expire_due_trials(db))
    assert [j.action for j in _jobs(db)] == ["add", "remove"]

    # Ended by a purchase: the trial peer goes, the paid one comes.
    two = _user(db, "trial_2", is_subscribed=False, subscribed_until=None, plan=None)
    db.run(trial_api.start_trial(_req("198.51.100.8"), db, {"sub": two.username}))
    pay = Payment(id=str(uuid.uuid4()), user_id=two.id, plan="basic-1m",
                  amount=int(plan_info("basic-1m")["amount"]), currency="RUB", status="pending")
    db.add(pay)
    db.run(db.commit())
    assert db.run(provisioner.activate_payment(two, pay, db)) is True
    db.run(mailer.drain())
    mine = _jobs(db)[2:]
    trial_cfg = db.run(db.execute(select(Config).where(Config.user_id == two.id, Config.kind == "trial"))).scalar_one()
    paid_cfg = db.run(db.execute(select(Config).where(Config.user_id == two.id, Config.kind == "paid"))).scalar_one()
    assert [(j.action, j.config_id) for j in mine] == [
        ("add", trial_cfg.id), ("add", paid_cfg.id), ("remove", trial_cfg.id)]


# ── addresses ────────────────────────────────────────────────────────────

def test_an_address_b_still_holds_is_not_handed_out_again(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    first = _add(db, user)
    db.run(config_api.delete_config(first["id"], db, {"sub": user.username}))
    # A has let it go; B has not yet (the removal waits).
    assert first["peer_ip"] not in a.peers.values()
    second = _add(db, user, "laptop")
    assert second["peer_ip"] != first["peer_ip"]
    # Once B has caught up the address is free again.
    db.run(entry_sync.run(db))
    third = _add(db, user, "tablet")
    assert third["peer_ip"] == first["peer_ip"]


# ── running the jobs ─────────────────────────────────────────────────────

def test_jobs_reach_b_in_order_with_the_peers_own_psk_and_label(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    _add(db, user, "laptop")
    assert db.run(entry_sync.run(db))["done"] == 2
    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    assert db.run(entry_sync.run(db))["done"] == 1
    assert _jobs(db, done=False) == []
    assert set(b.peers) == set(a.peers)
    [peer] = b.peers.values()
    assert peer["psk"] == "PSK-SECRET" and peer["name"] == f"auto-{user.username}"
    assert all(host == "192.0.2.20" for host, _ in b.calls)
    actions = [shlex.split(cmd)[1] for _, cmd in b.calls]
    assert actions == ["pwa-add-peer", "pwa-add-peer", "pwa-del-peer"]


def test_b_down_keeps_the_jobs_and_the_next_run_finishes_them(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    _add(db, user)
    _add(db, user, "laptop")
    b.mode = "down"
    stats = db.run(entry_sync.run(db))
    assert stats["unreachable"] == ["b"] and stats["done"] == 0
    jobs = _jobs(db, done=False)
    # One try for the whole entry, not one timeout per job.
    assert [j.attempts for j in jobs] == [1, 0] and len(b.calls) == 1
    b.mode = "up"
    assert db.run(entry_sync.run(db))["done"] == 2
    assert set(b.peers) == set(a.peers)


def test_an_answer_lost_after_the_work_was_done_is_not_an_error(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    b.mode = "lose"
    db.run(entry_sync.run(db))
    assert len(b.peers) == 1 and len(_jobs(db, done=False)) == 1
    b.mode = "up"
    db.run(entry_sync.run(db))
    [job] = _jobs(db)
    assert job.done_at is not None and job.last_error == "already there"

    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    b.mode = "lose"
    db.run(entry_sync.run(db))
    b.mode = "up"
    db.run(entry_sync.run(db))
    assert b.peers == {} and _jobs(db, done=False) == []
    assert _jobs(db)[-1].last_error == "already gone"


def test_a_refused_job_stays_and_does_not_hold_back_the_next(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    _add(db, user)
    b.mode = "refuse"
    stats = db.run(entry_sync.run(db))
    assert stats["failed"] == 1
    [job] = _jobs(db, done=False)
    assert job.attempts == 1 and "refusing" in job.last_error
    b.mode = "up"
    _add(db, user, "laptop")
    assert db.run(entry_sync.run(db))["done"] == 2


def test_a_device_gone_before_b_heard_of_it_never_reaches_b(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    stats = db.run(entry_sync.run(db))
    assert stats["skipped"] == 2 and b.calls == [] and _jobs(db, done=False) == []


def test_a_device_gone_after_an_unanswered_add_is_still_removed_from_b(db, a, b, monkeypatch):
    """The add may have landed with its answer lost: the removal must run."""
    _on(monkeypatch)
    user = _user(db)
    dev = _add(db, user)
    b.mode = "lose"
    db.run(entry_sync.run(db))
    assert len(b.peers) == 1
    b.mode = "up"
    db.run(config_api.delete_config(dev["id"], db, {"sub": user.username}))
    db.run(entry_sync.run(db))
    assert b.peers == {} and _jobs(db, done=False) == []


# ── the backlog, for people ──────────────────────────────────────────────

def test_a_stale_backlog_is_one_letter_and_one_all_clear(db, a, b, monkeypatch):
    _on(monkeypatch)
    sent = []
    result = {"ok": True}

    async def fake_send(to, subject, html, text=""):
        sent.append(subject)
        return result["ok"]
    monkeypatch.setattr(mailer, "send_email", fake_send)

    user = _user(db)
    _add(db, user)
    b.mode = "down"
    db.run(entry_sync.run(db))
    assert db.run(entry_sync.watch(db)) == "quiet"      # not an hour yet

    later = datetime.now(timezone.utc) + timedelta(hours=1, minutes=1)
    result["ok"] = False
    assert db.run(entry_sync.watch(db, now=later)) == "alert-failed"
    result["ok"] = True
    assert db.run(entry_sync.watch(db, now=later)) == "alerted"
    assert db.run(entry_sync.watch(db, now=later)) == "stale"
    assert len(sent) == 2 and "отстаёт" in sent[-1]
    event = db.run(db.execute(select(MonitorEvent).where(MonitorEvent.key == entry_sync.STALE_KEY))).scalar_one()
    assert event.ended_at is None

    b.mode = "up"
    db.run(entry_sync.run(db))
    assert db.run(entry_sync.watch(db, now=later)) == "recovered"
    assert db.run(entry_sync.watch(db, now=later)) == "quiet"
    assert "догнал" in sent[-1] and len(sent) == 3


def test_the_backlog_view(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db)
    _add(db, user)
    b.mode = "refuse"
    db.run(entry_sync.run(db))
    view = db.run(entry_sync.backlog(db))
    assert view["b"]["pending"] == 1 and view["b"]["stale"] == 0
    assert "refusing" in view["b"]["last_error"]


# ── filling a new standby ────────────────────────────────────────────────

def test_filling_b_owes_it_only_what_it_lacks_and_removes_nothing(db, a, b, monkeypatch):
    _on(monkeypatch)
    user = _user(db, plan="ext-1m")
    there, missing, waiting, gone = (_add(db, user, n) for n in ("one", "two", "three", "four"))
    db.run(config_api.delete_config(gone["id"], db, {"sub": user.username}))
    # B already has `there`, and a hand-made test peer the database does not know.
    keys = {c.id: c.public_key for c in db.run(db.execute(select(Config))).scalars()}
    b.peers[keys[there["id"]]] = {"ip": there["peer_ip"]}
    b.peers["TESTPEER" + "x" * 35] = {"ip": "10.88.88.251"}
    # `waiting` has its add job pending already; the rest were done before.
    for j in _jobs(db, done=False):
        if j.config_id != waiting["id"]:
            j.done_at = NOW
    db.run(db.commit())

    monkeypatch.setattr(entry_sync, "peers_on",
                        lambda host: {k: p["ip"] for k, p in b.peers.items()})
    report = db.run(entry_sync.fill(db, "b", dry_run=True))
    assert [line.split()[0] for line in report["to_add"]] == [missing["peer_ip"]]
    assert report["already_pending"] == 1 and report["unknown_on_entry"] == ["10.88.88.251 TESTPEER"]
    assert [j.config_id for j in _jobs(db, done=False)] == [waiting["id"]]   # dry run wrote nothing

    db.run(entry_sync.fill(db, "b", dry_run=False))
    db.run(entry_sync.run(db))
    assert _jobs(db, done=False) == []
    assert set(a.peers) <= set(b.peers) and "TESTPEER" + "x" * 35 in b.peers


def test_filling_needs_a_configured_standby(db, a, b):
    with pytest.raises(ValueError):
        db.run(entry_sync.fill(db, "b"))


def test_the_entrys_peer_list_is_read_from_the_wrapper(monkeypatch):
    monkeypatch.setattr(entry_sync, "_ssh", lambda host, cmd: (
        "KEY1\t10.88.88.42/32\nKEY2\t10.88.89.10/32,fd00::2/128\nKEY3\t(none)\n", ""))
    assert entry_sync.peers_on("h") == {"KEY1": "10.88.88.42", "KEY2": "10.88.89.10", "KEY3": "(none)"}
    monkeypatch.setattr(entry_sync, "_ssh", lambda host, cmd: ("", "sudo: a password is required"))
    with pytest.raises(RuntimeError):
        entry_sync.peers_on("h")


# ── the admin panel ──────────────────────────────────────────────────────

def test_the_admin_panel_shows_the_queue_only_with_a_standby(db, a, b, monkeypatch):
    from api import monitor
    from db.models import MonitorReport
    import json
    db.add(MonitorReport(id=1, received_at=datetime.now(timezone.utc),
                         payload=json.dumps({"sent_at": datetime.now(timezone.utc).timestamp(), "hosts": {}})))
    db.run(db.commit())
    admin = {"sub": "admin", "role": "admin"}
    assert all(c["id"] != "entry-sync" for c in db.run(monitor.state(db, admin))["cards"])

    _on(monkeypatch)
    view = db.run(monitor.state(db, admin))
    [card] = [c for c in view["cards"] if c["id"] == "entry-sync"]
    assert card["status"] == "ok" and "все изменения пиров переданы" in card["lines"][0]

    user = _user(db)
    _add(db, user)
    b.mode = "refuse"
    db.run(entry_sync.run(db))
    job = _jobs(db)[0]
    job.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.run(db.commit())
    view = db.run(monitor.state(db, admin))
    [card] = [c for c in view["cards"] if c["id"] == "entry-sync"]
    assert card["status"] == "bad" and view["status"] == "bad"
    assert any("refusing" in line for line in card["lines"])


def test_the_monitors_report_does_not_close_the_standbys_event(db, monkeypatch):
    from api import monitor
    monkeypatch.setenv("MONITOR_TOKEN", "t")
    db.add(MonitorEvent(key=entry_sync.STALE_KEY, level="bad", text="x", started_at=NOW))
    db.run(db.commit())
    db.run(monitor.receive(monitor.Report(sent_at=NOW.timestamp(), hosts={}), db, "Bearer t"))
    event = db.run(db.execute(select(MonitorEvent))).scalar_one()
    assert event.ended_at is None
