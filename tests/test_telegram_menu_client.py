"""
services/telegram.py's menu card against a fake Bot API: the animation's
file_id is reused, a refused animation falls back to text, and turning a
card that is gone sends a new one.
"""
import asyncio

import pytest

from services import telegram


@pytest.fixture
def api(monkeypatch):
    calls, replies = [], {}

    async def fake(method, **params):
        calls.append((method, params))
        r = replies.get(method)
        return r(params) if callable(r) else (r or {"ok": True, "result": {"message_id": 9}})

    monkeypatch.setattr(telegram, "call", fake)
    monkeypatch.setattr(telegram, "_banner_id", None)
    return calls, replies


def run(c):
    return asyncio.run(c)


def test_the_banner_goes_by_url_once_then_by_file_id(api):
    calls, replies = api
    replies["sendAnimation"] = {"ok": True, "result": {"message_id": 5, "animation": {"file_id": "FID"}}}
    assert run(telegram.send_menu(1, "hi", [[{"text": "a", "callback_data": "m:home"}]])) == 5
    assert calls[0][1]["animation"].endswith("/static/bot-banner.mp4")
    run(telegram.send_menu(1, "hi", []))
    assert calls[1][1]["animation"] == "FID"
    assert calls[0][1]["parse_mode"] == "HTML" and calls[0][1]["reply_markup"]["inline_keyboard"]


def test_a_refused_animation_falls_back_to_text_with_the_same_buttons(api):
    calls, replies = api
    replies["sendAnimation"] = {"ok": False, "description": "Bad Request: wrong file"}
    assert run(telegram.send_menu(1, "hi", [[{"text": "a", "url": "https://x"}]])) == 9
    assert calls[-1][0] == "sendMessage" and calls[-1][1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "a"


def test_turning_a_text_card_edits_its_text(api):
    calls, replies = api
    replies["editMessageCaption"] = {"ok": False, "description": "Bad Request: there is no caption in the message to edit"}
    run(telegram.edit_menu(1, 7, "x", []))
    assert [c[0] for c in calls] == ["editMessageCaption", "editMessageText"]


def test_same_screen_twice_is_not_an_error(api):
    calls, replies = api
    replies["editMessageCaption"] = {"ok": False, "description": "Bad Request: message is not modified"}
    run(telegram.edit_menu(1, 7, "x", []))
    assert [c[0] for c in calls] == ["editMessageCaption"]


def test_a_card_that_is_gone_is_sent_again(api):
    calls, replies = api
    replies["editMessageCaption"] = {"ok": False, "description": "Bad Request: message to edit not found"}
    run(telegram.edit_menu(1, 7, "x", []))
    assert calls[-1][0] == "sendAnimation"


def test_the_old_keyboard_is_removed_and_the_helper_message_deleted(api):
    calls, replies = api
    replies["sendMessage"] = {"ok": True, "result": {"message_id": 33}}
    run(telegram.drop_keyboard(1))
    assert calls[0][1]["reply_markup"] == {"remove_keyboard": True}
    assert calls[1] == ("deleteMessage", {"chat_id": 1, "message_id": 33})


def test_the_bot_api_can_go_through_a_proxy(monkeypatch):
    import config
    seen = {}

    class FakeClient:
        def __init__(self, **kw):
            seen.update(kw)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            class R:
                def json(self):
                    return {"ok": True, "result": {}}
            return R()

    monkeypatch.setattr(config, "TG_BOT_TOKEN", "t")
    monkeypatch.setattr(config, "TG_PROXY", "http://proxy.test:8888")
    monkeypatch.setattr(telegram.httpx, "AsyncClient", FakeClient)
    assert run(telegram.call("getMe"))["ok"]
    assert seen["proxy"] == "http://proxy.test:8888"
