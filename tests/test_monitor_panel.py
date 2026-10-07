"""
The admin panel's "Состояние" card: the monitor's report is accepted only with
MONITOR_TOKEN, problems open and close in the history, and the numbers come
out as words (api/monitor.py, services/monitor_view.py).

The probe values below are the ones the four servers printed on 2026-10-07.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import monitor  # noqa: E402
from db.models import MonitorEvent  # noqa: E402
from services import monitor_view as view  # noqa: E402

NOW = datetime.now(timezone.utc)
TOKEN = "test-monitor-token"
ADMIN = {"sub": "admin", "role": "admin"}

PORTAL = {"host": "saabmxpftl", "load1": 0.16, "ncpu": 2, "mem_avail_pct": 67, "disk_root_pct": 26,
          "uptime_s": 479522, "failed_units": 0, "backup_age": 12307, "expiry_age": 2562,
          "expiry_failures": 0, "containers_expected": 2, "containers_up": 2}
ENTRY = {"host": "xrdfzwvigy", "load1": 0.36, "ncpu": 2, "mem_avail_pct": 77, "disk_root_pct": 34,
         "uptime_s": 5902771, "failed_units": 1, "failed_unit_names": "openipmi.service",
         "awg.awg0.peers": 52, "awg.awg0.active": 14, "awg.awg0.fresh": 3,
         "awg.awg1.peers": 1, "awg.awg1.active": 1, "awg.awg1.fresh": 34}
EXIT = {"host": "833352", "load1": 0.37, "ncpu": 1, "mem_avail_pct": 82, "disk_root_pct": 30,
        "uptime_s": 8576456, "failed_units": 0, "awg.awg-de.peers": 1, "awg.awg-de.fresh": 8116864,
        "awg.awg0.peers": 1, "awg.awg0.fresh": 37}
AM1 = {"host": "am1", "load1": 0.0, "ncpu": 1, "mem_avail_pct": 72, "disk_root_pct": 32,
       "uptime_s": 274509, "failed_units": 0, "pulled_backup_age": 12324}


def _report(problems=(), notices=(), **hosts):
    base = {"portal": PORTAL, "entry": ENTRY, "exit": EXIT, "am1": AM1}
    base.update(hosts)
    return monitor.Report(
        sent_at=NOW.timestamp(), hosts=base,
        errors={k: "Connection timed out" for k, v in base.items() if v is None},
        links={"entry": ["awg1"], "exit": ["awg0"]}, clients={"entry": ["awg0"]},
        web={"urls": {"https://sov3r3ign.com/": ""}, "certs": {"sov3r3ign.com": 71.4}},
        problems=list(problems), notices=list(notices))


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("MONITOR_TOKEN", TOKEN)


def _send(db, report, token=TOKEN):
    return db.run(monitor.receive(report, db, f"Bearer {token}"))


def _state(db):
    return db.run(monitor.state(db, ADMIN))


def _card(st, cid):
    return next(c for c in st["cards"] if c["id"] == cid)


# ── who may post ────────────────────────────────────────────────────────

def test_without_a_configured_token_nothing_is_accepted(db, monkeypatch):
    monkeypatch.delenv("MONITOR_TOKEN")
    with pytest.raises(HTTPException) as e:
        _send(db, _report(), token="")
    assert e.value.status_code == 503


@pytest.mark.parametrize("token", ["", "wrong", TOKEN + "x", TOKEN[:-1]])
def test_a_wrong_token_is_refused(db, token):
    with pytest.raises(HTTPException) as e:
        _send(db, _report(), token=token)
    assert e.value.status_code == 401
    assert _state(db)["cards"] == []


# ── what the admin sees ─────────────────────────────────────────────────

def test_before_any_report_it_says_so(db):
    st = _state(db)
    assert st["status"] == "unknown" and "ещё не присылал" in st["summary"]


def test_the_servers_in_words(db):
    _send(db, _report())
    st = _state(db)
    assert [c["id"] for c in st["cards"]] == ["site", "links", "portal", "entry", "exit", "am1"]
    portal = _card(st, "portal")
    assert portal["status"] == "ok" and portal["title"] == "Портал"
    text = " | ".join(portal["lines"])
    assert "Бэкап базы: сегодня в" in text or "Бэкап базы: вчера в" in text
    assert "(3 ч 25 мин назад)" in text
    assert "Подписки проверены 42 мин назад" in text
    assert "Контейнеры: работают 2 из 2" in text
    assert "Диск занят на 26% · свободно памяти 67% · нагрузка низкая" in text
    entry = " | ".join(_card(st, "entry")["lines"])
    assert "Устройств на сервере: 52, активны сейчас: 14" in entry
    assert "Упавшие службы: openipmi.service" in entry
    links = _card(st, "links")
    assert links["lines"] == ["Вход (entry), awg1: обмен ключами 34 с назад",
                              "Выход (exit), awg0: обмен ключами 37 с назад"]
    assert _card(st, "site")["lines"] == ["https://sov3r3ign.com/ — открывается",
                                          "Сертификат sov3r3ign.com: ещё 71 дн"]
    assert "Копия бэкапа здесь" in " ".join(_card(st, "am1")["lines"])
    assert st["summary"] == "Всё работает" and st["stale"] is False


def test_problems_colour_their_card_and_the_whole(db):
    _send(db, _report(problems=[
        monitor.Problem(key="entry:units", text="entry: упали сервисы: openipmi.service", level="warn",
                        since=NOW.timestamp() - 600),
        monitor.Problem(key="exit:link:awg0", text="exit: связка awg0 молчит", level="bad",
                        since=NOW.timestamp() - 300)]))
    st = _state(db)
    assert _card(st, "entry")["status"] == "warn"
    assert _card(st, "entry")["problems"] == ["entry: упали сервисы: openipmi.service"]
    # A link problem belongs to the link card, not the server's.
    assert _card(st, "links")["status"] == "bad" and _card(st, "exit")["status"] == "ok"
    assert st["status"] == "bad" and st["summary"] == "Сломано: 1, требует внимания: 1"


def test_a_server_that_does_not_answer(db):
    _send(db, _report(exit=None, problems=[
        monitor.Problem(key="exit:down", text="exit: не отвечает", level="bad", since=NOW.timestamp())]))
    st = _state(db)
    ex = _card(st, "exit")
    assert ex["status"] == "bad" and ex["lines"] == ["Не отвечает: Connection timed out"]
    assert "Выход (exit), awg0: сервер не отвечает, не проверить" in _card(st, "links")["lines"]


def test_a_silent_monitor_is_not_mistaken_for_a_quiet_one():
    payload = _report().model_dump()
    st = view.build(payload, NOW - timedelta(minutes=25), NOW)
    assert st["stale"] and st["status"] == "unknown" and "Мониторинг молчит" in st["summary"]


# ── history ─────────────────────────────────────────────────────────────

def _events(db):
    return db.run(db.execute(select(MonitorEvent).order_by(MonitorEvent.id))).scalars().all()


P = monitor.Problem(key="exit:down", text="exit: не отвечает", level="bad", since=NOW.timestamp() - 240)


def test_a_problem_opens_once_and_closes_when_it_is_gone(db):
    _send(db, _report(problems=[P], exit=None))
    _send(db, _report(problems=[P], exit=None))
    ev = _events(db)
    assert len(ev) == 1 and ev[0].ended_at is None
    hist = _state(db)["history"]
    assert hist[0]["open"] and hist[0]["duration"] == "4 мин"
    _send(db, _report())
    ev = _events(db)
    assert len(ev) == 1 and ev[0].ended_at is not None
    assert not _state(db)["history"][0]["open"]


def test_a_reboot_notice_is_kept_once(db):
    n = monitor.Notice(key="entry:reboot", text="entry: перезагрузился", at=NOW.timestamp() - 120)
    _send(db, _report(notices=[n]))
    _send(db, _report(notices=[n]))
    ev = _events(db)
    assert len(ev) == 1 and ev[0].level == "info" and ev[0].ended_at is not None
    assert _state(db)["history"][0]["duration"] == ""


def test_a_clock_ahead_on_the_backup_host_does_not_put_events_in_the_future(db):
    p = monitor.Problem(key="am1:disk", text="am1: диск", level="warn", since=NOW.timestamp() + 3600)
    _send(db, _report(problems=[p]))
    assert view.aware(_events(db)[0].started_at) <= datetime.now(timezone.utc)


# ── words ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s,out", [(5, "5 с назад"), (125, "2 мин назад"), (2 * 3600 + 300, "2 ч 5 мин назад"),
                                   (7 * 3600, "7 ч назад"), (3 * 86400, "3 дн назад")])
def test_ago(s, out):
    assert view.ago(s) == out


def test_the_panel_draws_the_words_escaped():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "pwa" / "static" / "index.html").read_text()
    assert "/api/admin/monitor" in html and 'id="mon-card"' in html
    assert "${escHtml(c.title)}" in html and "${escHtml(p)}" in html and "escHtml(l)" in html
