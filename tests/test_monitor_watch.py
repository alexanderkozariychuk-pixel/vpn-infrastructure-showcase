"""
The dead man's switch for sov-monitor (services/monitor_watch.py): a letter
when the reports stop, one letter — not one per run — while they stay
stopped, an all-clear when they are back, and a failed letter retried rather
than forgotten. The monitor's own reports must not close the portal's event
before the all-clear went out (api/monitor.py).
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import monitor  # noqa: E402
from db.models import MonitorEvent, MonitorReport  # noqa: E402
from services import mailer, monitor_watch  # noqa: E402

T0 = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
TOKEN = "test-monitor-token"


class _Letters(list):
    """Letters sent so far; .state["ok"] = False makes the next sends fail."""
    state: dict


@pytest.fixture
def letters(monkeypatch):
    sent, state = _Letters(), {"ok": True}

    async def fake_send(to, subject, html, text=""):
        if state["ok"]:
            sent.append((to, subject, text))
        return state["ok"]

    monkeypatch.setattr(mailer, "send_email", fake_send)
    monkeypatch.setenv("MONITOR_ALERT_EMAIL", "ops@example.org")
    monkeypatch.setenv("MONITOR_TOKEN", TOKEN)
    sent.state = state
    return sent


def _report_at(db, at):
    row = db.run(db.get(MonitorReport, 1))
    if row is None:
        db.add(MonitorReport(id=1, received_at=at, payload="{}"))
    else:
        row.received_at = at
    db.run(db.commit())


def _watch(db, at):
    return db.run(monitor_watch.watch(db, at))


def _silent_events(db):
    return db.run(db.execute(select(MonitorEvent).where(
        MonitorEvent.key == monitor_watch.SILENT_KEY))).scalars().all()


def test_before_any_report_nothing_is_said(db, letters):
    assert _watch(db, T0) == "no-reports"
    assert letters == []


def test_a_fresh_report_is_quiet(db, letters):
    _report_at(db, T0)
    assert _watch(db, T0 + timedelta(minutes=9)) == "quiet"
    assert letters == [] and _silent_events(db) == []


def test_silence_is_told_once_and_its_end_once(db, letters):
    _report_at(db, T0)
    assert _watch(db, T0 + timedelta(minutes=11)) == "alerted"
    assert [(to, subj) for to, subj, _ in letters] == [("ops@example.org", "Sovereign: мониторинг молчит")]
    assert "11 мин назад" in letters[0][2]

    # Still silent an hour later: no second letter.
    assert _watch(db, T0 + timedelta(minutes=70)) == "silent"
    assert len(letters) == 1
    (event,) = _silent_events(db)
    assert event.ended_at is None and event.level == "bad"
    # The history counts the silence from the last report.
    assert event.started_at.replace(tzinfo=timezone.utc) == T0

    _report_at(db, T0 + timedelta(minutes=80))
    assert _watch(db, T0 + timedelta(minutes=81)) == "recovered"
    assert letters[1][1] == "Sovereign: мониторинг снова на связи"
    assert "Перерыв длился около 1 ч 20 мин" in letters[1][2]
    (event,) = _silent_events(db)
    assert event.ended_at is not None

    assert _watch(db, T0 + timedelta(minutes=86)) == "quiet"
    assert len(letters) == 2


def test_a_letter_that_failed_is_sent_on_the_next_run(db, letters):
    _report_at(db, T0)
    letters.state["ok"] = False
    assert _watch(db, T0 + timedelta(minutes=11)) == "alert-failed"
    assert _silent_events(db) == []
    letters.state["ok"] = True
    assert _watch(db, T0 + timedelta(minutes=16)) == "alerted"

    _report_at(db, T0 + timedelta(minutes=30))
    letters.state["ok"] = False
    assert _watch(db, T0 + timedelta(minutes=31)) == "recovery-failed"
    assert _silent_events(db)[0].ended_at is None
    letters.state["ok"] = True
    assert _watch(db, T0 + timedelta(minutes=36)) == "recovered"
    assert len(letters) == 2


def test_the_monitors_report_does_not_close_the_portals_event(db, letters):
    """The first report after the silence arrives before the watch runs: it
    must leave the silence open, or the all-clear would never be sent."""
    _report_at(db, T0)
    assert _watch(db, T0 + timedelta(minutes=11)) == "alerted"
    report = monitor.Report(sent_at=datetime.now(timezone.utc).timestamp(), hosts={})
    db.run(monitor.receive(report, db, f"Bearer {TOKEN}"))
    (event,) = _silent_events(db)
    assert event.ended_at is None
    assert _watch(db, datetime.now(timezone.utc)) == "recovered"


def test_without_an_address_it_goes_to_the_support_inbox(db, letters, monkeypatch):
    monkeypatch.delenv("MONITOR_ALERT_EMAIL")
    _report_at(db, T0)
    _watch(db, T0 + timedelta(minutes=11))
    assert letters[0][0] == mailer.SUPPORT_INBOX
