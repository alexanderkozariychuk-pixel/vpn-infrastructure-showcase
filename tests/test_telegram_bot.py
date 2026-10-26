"""
The customers' Telegram bot: linking by a one-time link, what each button
answers, support there and back, and that only Telegram may call the webhook.
Bot API calls are recorded, never sent.
"""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

import config
from api import telegram as bot
from db.models import Config, TelegramSupport, User
from services import notify, telegram

ADMIN = 999
NOW = datetime.now(timezone.utc)


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(config, "TG_BOT_TOKEN", "t")
    monkeypatch.setattr(config, "TG_BOT_USERNAME", "sov3r3ign_bot")
    monkeypatch.setattr(config, "TG_ADMIN_CHAT_ID", ADMIN)
    monkeypatch.setattr(config, "TG_WEBHOOK_SECRET", "s3cret")

    async def fake_send(chat_id, text, buttons=None, keyboard=None):
        out.append({"chat": chat_id, "text": text, "buttons": buttons, "keyboard": keyboard})
        return 1000 + len(out)

    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "send_later", lambda chat, text, buttons=None: out.append(
        {"chat": chat, "text": text, "buttons": buttons, "later": True}))
    bot._support_seen.clear()
    return out


def _user(db, name="alice", subscribed=True):
    u = User(id=str(uuid.uuid4()), username=name, email=f"{name}@example.test", password_hash="x",
             is_subscribed=subscribed, plan="basic-1m" if subscribed else None,
             subscribed_until=NOW + timedelta(days=20) if subscribed else None)
    db.add(u)
    db.run(db.commit())
    return u


def _msg(chat, text, **kw):
    return {"message": {"chat": {"id": chat, "type": "private"}, "from": {"username": "u"}, "text": text, **kw}}


def _token_for(db, user):
    url = db.run(bot.tg_link(db=db, payload={"sub": user.username}))["url"]
    assert url.startswith("https://t.me/sov3r3ign_bot?start=")
    return url.split("start=", 1)[1]


def test_a_one_time_link_ties_the_chat_to_the_account(db, sent):
    u = _user(db)
    tok = _token_for(db, u)
    assert len(tok) <= 64
    db.run(bot.handle(db, _msg(42, f"/start {tok}")))
    db.run(db.refresh(u))
    assert u.telegram_id == 42 and u.telegram_link_hash is None
    assert "подключён к аккаунту alice" in sent[-1]["text"] and sent[-1]["keyboard"]

    # The same link a second time does nothing.
    db.run(bot.handle(db, _msg(43, f"/start {tok}")))
    assert "устарела" in sent[-1]["text"]


def test_an_expired_link_is_refused(db, sent):
    u = _user(db)
    tok = _token_for(db, u)
    u.telegram_link_expires = NOW - timedelta(minutes=1)
    db.run(db.commit())
    db.run(bot.handle(db, _msg(42, f"/start {tok}")))
    db.run(db.refresh(u))
    assert u.telegram_id is None and "устарела" in sent[-1]["text"]


def test_one_chat_one_account(db, sent):
    a, b = _user(db, "alice"), _user(db, "bob")
    db.run(bot.handle(db, _msg(42, f"/start {_token_for(db, a)}")))
    db.run(bot.handle(db, _msg(42, f"/start {_token_for(db, b)}")))
    db.run(db.refresh(a))
    db.run(db.refresh(b))
    assert a.telegram_id is None and b.telegram_id == 42


def test_the_subscription_button(db, sent):
    u = _user(db)
    u.telegram_id = 42
    db.add(Config(id=str(uuid.uuid4()), user_id=u.id, name="phone", peer_ip="10.88.88.70", public_key="k1", private_key="enc", preshared_key="enc",
                  is_active=True, location="nl"))
    db.run(db.commit())
    db.run(bot.handle(db, _msg(42, bot.B_SUB)))
    t = sent[-1]["text"]
    assert "Действует до" in t and "Нидерланды — 1" in t
    db.run(bot.handle(db, _msg(7, bot.B_SUB)))
    assert "не знает ваш аккаунт" in sent[-1]["text"]


def test_renew_sends_to_the_site_not_a_payment_in_the_bot(db, sent):
    db.run(bot.handle(db, _msg(42, bot.B_RENEW)))
    assert sent[-1]["buttons"][0][0]["web_app"]["url"].endswith("/app?tg=1#payment")


def test_invite_gives_the_referral_link_to_a_paying_customer_only(db, sent):
    u = _user(db)
    u.telegram_id = 42
    db.run(db.commit())
    db.run(bot.handle(db, _msg(42, bot.B_INVITE)))
    assert "/?ref=" in sent[-1]["text"] and "t.me/share/url?" in sent[-1]["buttons"][0][0]["url"]
    v = _user(db, "bob", subscribed=False)
    v.telegram_id = 43
    db.run(db.commit())
    db.run(bot.handle(db, _msg(43, bot.B_INVITE)))
    assert "при действующей подписке" in sent[-1]["text"]


def test_support_goes_to_the_operator_and_the_reply_comes_back(db, sent):
    u = _user(db)
    u.telegram_id = 42
    db.run(db.commit())
    db.run(bot.handle(db, _msg(42, "Не подключается на айфоне, МТС")))
    to_admin = next(m for m in sent if m["chat"] == ADMIN)
    assert "alice" in to_admin["text"] and "айфоне" in to_admin["text"]
    assert sent[-1]["chat"] == 42 and "ответим здесь" in sent[-1]["text"]
    row = db.run(db.execute(__import__("sqlalchemy").select(TelegramSupport))).scalar_one()

    db.run(bot.handle(db, _msg(ADMIN, "Попробуйте Нидерланды", reply_to_message={"message_id": row.admin_message_id})))
    back = [m for m in sent if m["chat"] == 42][-1]
    assert "Попробуйте Нидерланды" in back["text"]
    assert sent[-1]["chat"] == ADMIN and "Отправлено" in sent[-1]["text"]


def test_a_device_file_is_not_forwarded(db, sent):
    db.run(bot.handle(db, _msg(42, "[Interface]\nPrivateKey = abc")))
    assert not any(m["chat"] == ADMIN for m in sent)
    assert "ключ" in sent[-1]["text"]


def test_support_is_limited_per_chat(db, sent):
    for i in range(bot._SUPPORT_LIMIT):
        db.run(bot.handle(db, _msg(42, f"вопрос {i}")))
    db.run(bot.handle(db, _msg(42, "ещё")))
    assert "Слишком много" in sent[-1]["text"]


def test_groups_are_ignored(db, sent):
    db.run(bot.handle(db, {"message": {"chat": {"id": -5, "type": "group"}, "text": "/start"}}))
    assert sent == []


def test_bell_messages_go_to_the_chat_too(db, sent):
    u = _user(db)
    u.telegram_id = 42
    db.run(db.commit())
    db.run(notify.notify(db, u, "referral_bonus", days=30, date="01.12.2026"))
    later = [m for m in sent if m.get("later")]
    assert later and later[0]["chat"] == 42 and "+30" in later[0]["text"]
    assert later[0]["buttons"][0][0]["web_app"]["url"].endswith("/app?tg=1#invite")


def test_no_chat_no_message(db, sent):
    u = _user(db)
    db.run(notify.notify(db, u, "paid", plan="x", date="d"))
    assert not [m for m in sent if m.get("later")]


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


def test_only_telegram_may_call_the_webhook(db, sent):
    with pytest.raises(HTTPException) as e:
        db.run(bot.webhook(_Req({}), db=db, x_telegram_bot_api_secret_token="wrong"))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        db.run(bot.webhook(_Req({}), db=db, x_telegram_bot_api_secret_token=None))
    assert db.run(bot.webhook(_Req(_msg(42, "/id")), db=db, x_telegram_bot_api_secret_token="s3cret")) == {"ok": True}
    assert sent[-1]["text"] == "chat id: 42"


def test_without_a_token_the_account_hides_the_card(db, monkeypatch):
    monkeypatch.setattr(config, "TG_BOT_TOKEN", None)
    u = _user(db)
    assert db.run(bot.tg_state(db=db, payload={"sub": u.username}))["enabled"] is False
    with pytest.raises(HTTPException):
        db.run(bot.tg_link(db=db, payload={"sub": u.username}))


def test_the_portal_wires_the_bot():
    pwa = Path(__file__).resolve().parents[1] / "pwa"
    assert "app.include_router(telegram_router)" in (pwa / "main.py").read_text()
    html = (pwa / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="set-tg"' in html and "/api/client/telegram/link" in html
    assert "Telegram" in (pwa / "static" / "privacy.html").read_text(encoding="utf-8")
