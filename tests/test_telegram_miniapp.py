"""
The Mini App: only Telegram's signed initData signs anyone in, only for a
linked account, and a device file leaves by a short signed link only.
"""
import hashlib
import hmac
import json
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

import config
from api import config as config_api
from api import telegram as bot
from db.models import Config, User

TOKEN = "123456:TEST-token"
NOW = datetime.now(timezone.utc)


def init_data(user_id=42, age=0, token=TOKEN, tamper=False):
    fields = {"auth_date": str(int(time.time()) - age), "query_id": "q1",
              "user": json.dumps({"id": user_id, "first_name": "A"})}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if tamper:
        fields["user"] = json.dumps({"id": 7, "first_name": "B"})
    return urllib.parse.urlencode(fields)


class _Req:
    client = None
    headers = {}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(config, "TG_BOT_TOKEN", TOKEN)
    from services import ratelimit
    for lim in ratelimit.ALL:
        lim.reset()
    monkeypatch.setattr(bot, "_user_by_chat", bot._user_by_chat)
    import services.net as net
    monkeypatch.setattr(net, "resolve_source_ip", lambda r: "1.2.3.4")


def _user(db, name="alice", chat=None):
    u = User(id=str(uuid.uuid4()), username=name, email=f"{name}@x.test", password_hash="x",
             is_subscribed=True, plan="basic-1m", subscribed_until=NOW + timedelta(days=10), telegram_id=chat)
    db.add(u)
    db.run(db.commit())
    return u


def test_a_valid_signature_names_the_user():
    assert bot.verify_init_data(init_data(), TOKEN)["id"] == 42


@pytest.mark.parametrize("data", [init_data(tamper=True), init_data(token="other:token"),
                                  init_data(age=2 * 86400), "garbage", ""])
def test_anything_else_is_refused(data):
    assert bot.verify_init_data(data, TOKEN) is None


def test_a_linked_account_is_signed_in(db, on):
    _user(db, chat=42)
    r = db.run(bot.tg_login(bot.InitData(init_data=init_data()), _Req(), db=db))
    assert r["username"] == "alice" and r["access_token"]


def test_an_unlinked_one_is_told_to_sign_in_once(db, on):
    _user(db)
    with pytest.raises(HTTPException) as e:
        db.run(bot.tg_login(bot.InitData(init_data=init_data()), _Req(), db=db))
    assert e.value.status_code == 404 and e.value.detail == "not_linked"


def test_a_forged_one_gets_nothing(db, on):
    _user(db, chat=7)
    with pytest.raises(HTTPException) as e:
        db.run(bot.tg_login(bot.InitData(init_data=init_data(tamper=True)), _Req(), db=db))
    assert e.value.status_code == 401


def test_password_sign_in_inside_telegram_links_it(db, on):
    u = _user(db)
    db.run(bot.tg_link_webapp(bot.InitData(init_data=init_data(user_id=55)), db=db, payload={"sub": "alice"}))
    db.run(db.refresh(u))
    assert u.telegram_id == 55


def _config(db, user):
    c = Config(id=str(uuid.uuid4()), user_id=user.id, name="phone", peer_ip="10.88.88.70", public_key="k",
               private_key="enc", preshared_key="enc", is_active=True, location="de")
    db.add(c)
    db.run(db.commit())
    return c


def test_a_download_link_works_for_two_minutes_only(db, monkeypatch):
    monkeypatch.setattr(config_api, "render_config", lambda c: "[Interface]\nPrivateKey = X\n")
    u = _user(db)
    c = _config(db, u)
    link = db.run(config_api.config_download_link(c.id, db=db, payload={"sub": "alice"}))
    assert link["file_name"] == "phone.conf"
    token = link["path"].split("/")[4]
    resp = db.run(config_api.config_download(token, "phone.conf", db=db))
    assert b"PrivateKey" in resp.body and resp.headers["cache-control"] == "no-store"

    cid, exp, sig = token.split(".")
    for bad in (f"{cid}.{int(exp) + 1}.{sig}", f"{cid}.{exp}.{'0' * 32}", "nonsense"):
        with pytest.raises(HTTPException):
            db.run(config_api.config_download(bad, "phone.conf", db=db))
    old = int(time.time()) - 1
    with pytest.raises(HTTPException):
        db.run(config_api.config_download(f"{cid}.{old}.{config_api._dl_sig(cid, old)}", "x", db=db))


def test_someone_elses_device_gets_no_link(db):
    _user(db, "alice")
    bob = _user(db, "bob")
    c = _config(db, bob)
    with pytest.raises(HTTPException) as e:
        db.run(config_api.config_download_link(c.id, db=db, payload={"sub": "alice"}))
    assert e.value.status_code == 404


def test_the_page_knows_the_mini_app():
    html = (Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html").read_text(encoding="utf-8")
    for needed in ("telegram-web-app.js", "/api/auth/telegram", "link-webapp", "download-link", "openExternal(d.url)"):
        assert needed in html, needed


def test_inside_telegram_a_stored_session_is_never_reused():
    """One phone, two Telegram accounts, one storage: the second must not open the first's account."""
    html = (Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html").read_text(encoding="utf-8")
    init = html[html.index("(function init() {"):]
    assert init.index("if (IS_TG) {") < init.index("if (token) {")
    # the day's token, the name and the long session (refresh token) all go
    assert "['sov_token', 'sov_user', 'sov_refresh'].forEach(k => localStorage.removeItem(k))" in init[:900]
    boot = html[html.index("async function tgBoot()"):html.index("async function tgLinkAfterLogin()")]
    assert "if (token) return;" not in boot
