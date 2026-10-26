"""
A Telegram account stands in for a confirmed mailbox: a cold visitor opens
the bot, taps "try for free", picks a name in the Mini App and gets the
trial — no email. One trial per Telegram, as there is one per mailbox.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import payment, register  # noqa: E402
from api import telegram as bot  # noqa: E402
from db.models import Payment, TrialGrant, User  # noqa: E402
from services import mailer  # noqa: E402

from test_telegram_miniapp import _Req, init_data, on  # noqa: E402,F401
from test_trial import _env, _refused, _start, node  # noqa: E402,F401

NOW = datetime.now(timezone.utc)


def _reg(db, name="cold_1", tg=42):
    body = bot.TgRegister(init_data=init_data(user_id=tg), username=name)
    return db.run(bot.tg_register(body, _Req(), db=db))


def _get(db, name):
    return db.run(db.execute(select(User).where(User.username == name))).scalar_one()


def test_registration_from_telegram_needs_no_email(db, on):
    r = _reg(db)
    assert r["access_token"] and r["username"] == "cold_1"
    u = _get(db, "cold_1")
    assert u.email is None and u.telegram_id == 42 and u.email_verified_at is None
    me = db.run(register.get_me(db, {"sub": "cold_1"}))
    assert me["telegram_linked"] is True and me["trial"]["state"] == "available"


def test_a_telegram_with_an_account_signs_in_instead(db, on):
    _reg(db)
    with pytest.raises(HTTPException) as e:
        _reg(db, "cold_2")
    assert e.value.status_code == 409 and e.value.detail == "already_linked"


def test_a_taken_or_bad_name_is_refused(db, on):
    _reg(db, "Cold_1")
    for name, code in (("cold_1", "username_taken"), ("bad name!", "bad_username")):
        with pytest.raises(HTTPException) as e:
            _reg(db, name, tg=99)
        assert e.value.detail == code


def test_a_forged_init_data_creates_nothing(db, on):
    body = bot.TgRegister(init_data=init_data(tamper=True), username="cold_9")
    with pytest.raises(HTTPException) as e:
        db.run(bot.tg_register(body, _Req(), db=db))
    assert e.value.status_code == 401
    assert db.run(db.execute(select(User))).scalars().all() == []


def test_the_trial_starts_for_a_telegram_account(db, on, node):
    _reg(db)
    out = _start(db, _get(db, "cold_1"))
    assert out["config"]["kind"] == "trial"
    grant = db.run(db.execute(select(TrialGrant))).scalar_one()
    assert grant.telegram_id == 42 and grant.email_norm is None


def test_one_trial_per_telegram(db, on, node):
    """Unlink, make a second account on the same Telegram: no second trial."""
    _reg(db)
    first = _get(db, "cold_1")
    _start(db, first)
    first.telegram_id = None
    db.run(db.commit())
    _reg(db, "cold_2")
    assert _refused(db, _get(db, "cold_2"), ip="203.0.113.50")[0] in (403, 409)


def test_a_telegram_account_may_buy(db, on):
    _reg(db)
    u = _get(db, "cold_1")
    pay, _ = db.run(payment._open_order(db, u, payment.CreatePaymentRequest(plan="basic-1m")))
    assert pay.status == "pending"


def test_without_email_or_telegram_buying_is_still_refused(db):
    u = User(id=str(uuid.uuid4()), username="plain_1", email="p@x.test", password_hash="x")
    db.add(u)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        db.run(payment._open_order(db, u, payment.CreatePaymentRequest(plan="basic-1m")))
    assert e.value.detail == "email_not_verified"
    assert db.run(db.execute(select(Payment))).scalars().all() == []


def test_no_mailbox_no_letter():
    mailer.send_later(None, "s", "<p>x</p>")  # no running loop needed: returns first


def test_the_bot_offers_the_trial_and_the_page_knows_it():
    src = (Path(bot.__file__)).read_text()
    assert "trial=1" in src and "login=1" in src
    page = (Path(bot.__file__).parent.parent / "static" / "index.html").read_text()
    assert "view-tgreg" in page and "/api/auth/telegram/register" in page
    assert "!d.telegram_linked" in page


def test_the_migration_drops_not_null_and_adds_the_column():
    mig = next((Path(bot.__file__).parent.parent / "alembic" / "versions").glob("d2f7a6b04c19_*.py")).read_text()
    assert "trial_grants" in mig and "telegram_id" in mig and "nullable=True" in mig
    assert "c8e4d1a92b37" in mig.split("down_revision")[1].splitlines()[0]


def test_inside_telegram_the_email_form_never_opens_for_the_trial():
    page = (Path(bot.__file__).parent.parent / "static" / "index.html").read_text()
    assert "if (!token && trialIntent && !IS_TG)" in page
    assert "if (TG_TRIAL || q.get('trial') === '1') startTrial();" in page


def test_inside_telegram_create_account_is_the_username_only_form():
    page = (Path(bot.__file__).parent.parent / "static" / "index.html").read_text()
    assert "if (view === 'register' && IS_TG)" in page


def test_the_config_page_opens_on_three_first_steps():
    page = (Path(bot.__file__).parent.parent / "static" / "index.html").read_text()
    assert 'id="qs-card"' in page and "renderQuickStart();" in page
    assert "apps.apple.com/app/amneziawg/id6478942365" in page
    assert "play.google.com/store/apps/details?id=org.amnezia.awg" in page
    # dismissed per account: one storage is shared by every Telegram account on a phone
    assert "'sov_qs_done:' + (localStorage.getItem('sov_user')" in page
