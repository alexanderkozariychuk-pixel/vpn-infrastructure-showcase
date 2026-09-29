"""
/api/client/me — what the portal's "current plan" block is built from.

It showed "no subscription" to every customer, paying or not: the page read
`plan` from a response that never carried it. And its status line trusted
the raw `is_subscribed` flag, which the expiry sweep clears only some time
after the paid period ends. Both are pinned here, server side and page side.
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api import register
from db.models import User

INDEX = Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html"


def _user(db, **kw):
    u = User(id=str(uuid.uuid4()), username=kw.pop("username", "test1"),
             email=f"{uuid.uuid4().hex[:6]}@x.test", password_hash="h", **kw)
    db.add(u)
    db.run(db.commit())
    return u


def _me(db, user):
    return db.run(register.get_me(db, {"sub": user.username}))


def test_a_paying_customer_gets_their_plan_and_an_active_status(db):
    u = _user(db, plan="basic-1m", is_subscribed=True,
              subscribed_until=datetime.now(timezone.utc) + timedelta(days=20))
    d = _me(db, u)
    assert d["plan"] == "basic-1m"
    assert d["active"] is True


def test_a_period_that_has_ended_is_not_active_even_while_the_flag_is_still_set(db):
    """The sweep has not run yet: flag true, date in the past."""
    u = _user(db, plan="ext-3m", is_subscribed=True,
              subscribed_until=datetime.now(timezone.utc) - timedelta(hours=2))
    d = _me(db, u)
    assert d["is_subscribed"] is True   # the raw flag, kept for older clients
    assert d["active"] is False


def test_a_missing_end_date_is_not_active(db):
    u = _user(db, plan="basic-1m", is_subscribed=True, subscribed_until=None)
    assert _me(db, u)["active"] is False


def test_a_customer_who_never_paid_is_not_active(db):
    u = _user(db, username="fresh")
    d = _me(db, u)
    assert d["active"] is False and d["plan"] is None


# ── the page ─────────────────────────────────────────────────────────────────

def _render_me() -> str:
    html = INDEX.read_text(encoding="utf-8")
    body = html[html.index("function renderMe("):]
    return body[:body.index("\n}\n")]


def test_the_page_judges_the_status_by_the_servers_gate_not_the_raw_flag():
    body = _render_me()
    assert "d.active" in body
    assert "d.is_subscribed ? t('sub-active')" not in body


def test_the_page_names_the_plan_instead_of_printing_its_key():
    html = INDEX.read_text(encoding="utf-8")
    assert "planLabel(d.plan)" in _render_me()
    # Every plan the server sells has a period the page can name.
    from config import PLANS
    for key in PLANS:
        per = key.split("-", 1)[1]
        assert re.search(rf"'period-{per}':", html), f"no label for period {per}"


def test_switching_language_redraws_the_plan_block():
    html = INDEX.read_text(encoding="utf-8")
    body = html[html.index("function toggleLang("):]
    body = body[:body.index("\n}\n")]
    assert "renderMe(_lastMe)" in body
