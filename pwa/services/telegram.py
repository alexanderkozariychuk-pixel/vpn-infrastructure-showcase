"""
services/telegram.py — sending through the customers' Telegram bot.

The bot itself (commands, linking, support) is api/telegram.py; this module
only talks to the Bot API. Without TG_BOT_TOKEN every call does nothing, so
the rest of the portal never has to ask whether the bot is set up.

Messages that ride along with something else — a bell notification inside a
payment callback, a reminder from the hourly job — go out with send_later,
after the caller's work, the way letters do (services/mailer.py); drain()
waits for them before a job exits.
"""
import asyncio
import logging

import httpx

import config

logger = logging.getLogger(__name__)

API = "https://api.telegram.org"


def enabled() -> bool:
    return bool(config.TG_BOT_TOKEN)


async def call(method: str, **params) -> dict:
    """One Bot API call. Never raises: {"ok": False, ...} on any failure."""
    if not enabled():
        return {"ok": False, "description": "bot is off"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(f"{API}/bot{config.TG_BOT_TOKEN}/{method}", json=params)
            return r.json()
    except Exception as e:  # noqa: BLE001
        # The URL carries the token: log the kind of failure, never the request.
        logger.warning("telegram %s failed: %s", method, e.__class__.__name__)
        return {"ok": False, "description": e.__class__.__name__}


async def send(chat_id: int, text: str, buttons: list[list[dict]] | None = None,
               keyboard: list[list[str]] | None = None) -> int | None:
    """Send a message; returns its id, or None. `buttons` are inline URL/callback rows."""
    params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    elif keyboard:
        params["reply_markup"] = {"keyboard": [[{"text": t} for t in row] for row in keyboard],
                                  "resize_keyboard": True, "is_persistent": True}
    r = await call("sendMessage", **params)
    if not r.get("ok"):
        logger.info("telegram send to %s refused: %s", chat_id, r.get("description"))
        return None
    return r["result"]["message_id"]


_pending: set = set()


def send_later(chat_id: int, text: str, buttons: list[list[dict]] | None = None) -> None:
    if not enabled() or not chat_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(send(chat_id, text, buttons))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
