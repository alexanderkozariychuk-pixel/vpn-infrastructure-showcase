"""
api/telegram.py — the customers' Telegram bot.

What it does:
  * linking: the account's "Connect Telegram" makes a one-time link
    t.me/<bot>?start=<token> (15 minutes); opening it ties that chat to the
    account. Nothing is typed into the bot — no login, no password.
  * notifications: everything that goes to the bell goes to the chat too
    (services/notify.py), with a button to the right page of the account.
  * the menu: /start shows one animated card — the customer's state and
    buttons (account, subscription, invite a friend, status, support, how to
    connect; for someone new, the free trial). Buttons turn the same card to
    another screen. Payment stays on the site.
  * support: any other text goes to the operator's chat (TG_ADMIN_CHAT_ID);
    the operator answers with Telegram's "reply", and the answer goes back.

What it does not do: send device files (they hold the device's key, and a
chat keeps them on Telegram's servers) or take payments (they stay on the
site, with the provider the site is approved for).

Telegram calls POST /api/telegram/webhook with the secret given to
setWebhook in a header; anything without it is refused.
"""
import hashlib
import logging
import secrets
import time
import urllib.parse
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from auth.jwt import require_auth
from db.base import get_db
from db.models import Config, TelegramSupport, User
from services import credit, mailer, telegram
from services.subscriptions import has_active_subscription

logger = logging.getLogger(__name__)
router = APIRouter()

LINK_TTL = timedelta(minutes=15)
CHANNEL = "https://t.me/sov3r3ign_net"
SITE = mailer.SITE_URL

# The old bottom keyboard's buttons: chats that still have it keep working
# (each opens the card); /start takes the keyboard away.
B_SUB, B_RENEW, B_INVITE, B_STATUS, B_HELP = "📋 Подписка", "💳 Продлить", "🎁 Пригласить друга", "📡 Статус", "💬 Поддержка"

# Support messages per chat: at most this many in an hour.
_SUPPORT_LIMIT, _SUPPORT_WINDOW = 10, 3600
_support_seen: dict[int, deque] = defaultdict(deque)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _me(db: AsyncSession, payload: dict) -> User:
    user = (await db.execute(select(User).where(User.username == payload.get("sub")))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ── the account side ────────────────────────────────────────────────────────

@router.get("/api/client/telegram")
async def tg_state(db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    user = await _me(db, payload)
    return {"enabled": telegram.enabled() and bool(config.TG_BOT_USERNAME),
            "linked": user.telegram_id is not None,
            "bot": config.TG_BOT_USERNAME or None}


@router.post("/api/client/telegram/link")
async def tg_link(db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    if not (telegram.enabled() and config.TG_BOT_USERNAME):
        raise HTTPException(status_code=503, detail="bot is off")
    user = await _me(db, payload)
    token = secrets.token_urlsafe(24)  # 32 characters, inside /start's 64
    user.telegram_link_hash = _hash(token)
    user.telegram_link_expires = datetime.now(timezone.utc) + LINK_TTL
    await db.commit()
    return {"url": f"https://t.me/{config.TG_BOT_USERNAME}?start={token}"}


@router.delete("/api/client/telegram/link")
async def tg_unlink(db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    user = await _me(db, payload)
    chat = user.telegram_id
    user.telegram_id = None
    user.telegram_link_hash = None
    await db.commit()
    if chat:
        await telegram.send(chat, "Telegram отключён от аккаунта Sovereign. Уведомления сюда больше не придут.")
    return {"ok": True}


# ── the bot ─────────────────────────────────────────────────────────────────

NOT_LINKED = ("Бот пока не знает ваш аккаунт. Подключите его в личном кабинете: "
              "«Настройки» → «Подключить Telegram».")


def _site_button(text: str, page: str) -> list[list[dict]]:
    """Opens that page of the account inside Telegram (the Mini App)."""
    return [[{"text": text, "web_app": {"url": f"{SITE}/app?tg=1#{page}"}}]]


async def _user_by_chat(db: AsyncSession, chat_id: int) -> User | None:
    return (await db.execute(select(User).where(User.telegram_id == chat_id))).scalar_one_or_none()


async def _link(db: AsyncSession, chat_id: int, token: str) -> str:
    user = (await db.execute(select(User).where(User.telegram_link_hash == _hash(token)))).scalar_one_or_none()
    if user is None or _aware(user.telegram_link_expires) is None or _aware(user.telegram_link_expires) < datetime.now(timezone.utc):
        return "Ссылка устарела или уже использована. Получите новую в личном кабинете: «Настройки» → «Подключить Telegram»."
    # One chat, one account: a chat that was tied to another account moves here.
    other = await _user_by_chat(db, chat_id)
    if other is not None and other.id != user.id:
        other.telegram_id = None
        await db.flush()  # first, or the unique telegram_id clashes inside one flush
    user.telegram_id = chat_id
    user.telegram_link_hash = None
    user.telegram_link_expires = None
    await db.commit()
    return f"Готово: бот подключён к аккаунту {user.username}. Уведомления о подписке теперь приходят сюда."


async def _subscription_text(db: AsyncSession, user: User) -> str:
    if not has_active_subscription(user):
        if user.trial_until and _aware(user.trial_until) > datetime.now(timezone.utc):
            until = _aware(user.trial_until).astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y %H:%M")
            return f"Пробный период до {until} МСК. Чтобы продолжить без перерыва — выберите тариф."
        return "Активной подписки нет. Выберите тариф в личном кабинете."
    from config import plan_info
    info = plan_info(user.plan) or {}
    title = mailer.plan_title(info.get("tier", ""), info.get("days", 0), "ru") if info else (user.plan or "—")
    until = _aware(user.subscribed_until).astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
    rows = (await db.execute(select(Config.location).where(Config.user_id == user.id, Config.is_active.is_(True)))).scalars().all()
    names = {"nl": "Нидерланды", "de": "Германия"}
    counts = {}
    for loc in rows:
        counts[loc or "de"] = counts.get(loc or "de", 0) + 1
    devices = ", ".join(f"{names.get(k, k)} — {v}" for k, v in sorted(counts.items())) or "пока нет"
    return f"Тариф: {title}\nДействует до: {until}\nУстройства: {devices}"


async def _invite_text(db: AsyncSession, user: User) -> tuple[str, list[list[dict]] | None]:
    if not has_active_subscription(user):
        return "Ссылка для друзей доступна при действующей подписке.", None
    promo = await credit.issue_code(db, user)
    await db.commit()
    link = f"{SITE}/?ref={promo.code}"
    share = "https://t.me/share/url?" + urllib.parse.urlencode({
        "url": link,
        "text": f"Пользуюсь VPN Sovereign — работает стабильно. По моей ссылке скидка {promo.discount_percent}% на первую оплату.",
    })
    text = (f"Ваша ссылка: {link}\n\n"
            f"Друг получает скидку {promo.discount_percent}% на первую оплату, а вы — "
            f"+{credit.REFERRAL_REWARD_DAYS} дней к подписке за каждого, кто оплатит.")
    return text, [[{"text": "Отправить другу", "url": share}]]


def _support_allowed(chat_id: int) -> bool:
    now = time.monotonic()
    q = _support_seen[chat_id]
    while q and q[0] < now - _SUPPORT_WINDOW:
        q.popleft()
    if len(q) >= _SUPPORT_LIMIT:
        return False
    q.append(now)
    return True


async def _to_support(db: AsyncSession, chat_id: int, from_name: str, text: str) -> str:
    if not config.TG_ADMIN_CHAT_ID:
        return "Поддержка в боте пока не подключена. Напишите через личный кабинет («Техподдержка») или на sovrn.support@gmail.com."
    if not _support_allowed(chat_id):
        return "Слишком много сообщений подряд. Мы уже читаем ваши сообщения — ответим здесь."
    user = await _user_by_chat(db, chat_id)
    who = f"{user.username} · {user.plan or 'без подписки'}" if user else f"не подключён · {from_name}"
    mid = await telegram.send(config.TG_ADMIN_CHAT_ID, f"💬 {who}\n\n{text[:3500]}\n\n↩️ Ответьте на это сообщение (Reply).")
    if mid is None:
        return "Не получилось передать сообщение. Напишите через личный кабинет или на sovrn.support@gmail.com."
    db.add(TelegramSupport(admin_message_id=mid, user_chat_id=chat_id))
    await db.commit()
    return "Получили, ответим здесь. Обычно — в течение рабочего дня."


async def _admin_reply(db: AsyncSession, msg: dict) -> None:
    to = msg.get("reply_to_message") or {}
    row = (await db.execute(select(TelegramSupport).where(
        TelegramSupport.admin_message_id == to.get("message_id")))).scalar_one_or_none()
    if row is None:
        await telegram.send(config.TG_ADMIN_CHAT_ID, "Чтобы ответить клиенту, используйте «Ответить» (Reply) на его сообщение.")
        return
    ok = await telegram.send(row.user_chat_id, f"💬 Поддержка Sovereign:\n\n{msg.get('text', '')}")
    await telegram.send(config.TG_ADMIN_CHAT_ID, "✓ Отправлено" if ok else "✗ Не доставлено: клиент мог заблокировать бота.")


# ── the menu card ───────────────────────────────────────────────────────────
#
# One animated card (services/telegram.send_menu) with the customer's state
# in the caption and the buttons under it. Inline buttons turn the same card
# to another screen (callback "m:<screen>"), so the chat does not fill up.
# Pages of the account open inside Telegram (web_app); payment stays there.

MSK = timezone(timedelta(hours=3))
HELP_TEXT = ("Опишите проблему одним сообщением прямо в этот чат — устройство, сеть "
             "(Wi-Fi или мобильная, оператор), локацию и что происходит. Ответим здесь.\n\n"
             "Не присылайте файлы подключения и пароли.")


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _app(text: str, page: str = "", query: str = "") -> dict:
    return {"text": text, "web_app": {"url": f"{SITE}/app?tg=1{query}" + (f"#{page}" if page else "")}}


def _cb(text: str, screen: str) -> dict:
    return {"text": text, "callback_data": f"m:{screen}"}


BACK = [[_cb("← Назад", "home")]]


async def _home(db: AsyncSession, chat_id: int, first_name: str = "", ref: str = "") -> tuple[str, list]:
    user = await _user_by_chat(db, chat_id)
    hello = f"Привет, {_esc(first_name)}!" if first_name else "Привет!"
    if user is None:
        q = f"&ref={urllib.parse.quote(ref)}" if ref else ""
        caption = (f"<b>{hello}</b>\n\nSovereign — персональное защищённое соединение: "
                   "свой ключ для каждого устройства, маршрут через несколько узлов.\n\n"
                   "🎁 <b>Пробный период — бесплатно</b>, без карты и без почты: аккаунт создаётся "
                   "прямо здесь, за одну минуту.")
        return caption, [
            [_app("🎁 Попробовать бесплатно", query=f"&trial=1{q}")],
            [_app("У меня уже есть аккаунт", query="&login=1")],
            [_cb("📡 Статус", "status"), _cb("💬 Поддержка", "help")],
        ]
    now = datetime.now(timezone.utc)
    if has_active_subscription(user):
        until = _aware(user.subscribed_until).astimezone(MSK).strftime("%d.%m.%Y")
        state = f"✅ Подписка активна до <b>{until}</b>"
        pay = _cb("💳 Подписка", "sub")
    elif user.trial_until and _aware(user.trial_until) > now:
        until = _aware(user.trial_until).astimezone(MSK).strftime("%d.%m %H:%M")
        state = f"🎁 Пробный период до <b>{until}</b> МСК"
        pay = _app("💳 Выбрать тариф", "payment")
    else:
        state = "⏸ Подписка не активна"
        pay = _app("💳 Продлить", "payment")
    caption = f"<b>{hello}</b>\n\n{state}\nАккаунт: {_esc(user.username)}"
    return caption, [
        [_app("📱 Кабинет", "config")],
        [pay, _cb("🤝 Пригласить друга", "invite")],
        [_cb("📡 Статус", "status"), _cb("💬 Поддержка", "help")],
        [_app("❓ Как подключить", "connect")],
    ]


async def _screen(db: AsyncSession, chat_id: int, screen: str, first_name: str = "") -> tuple[str, list]:
    if screen == "status":
        return ("📡 <b>Статус</b>\n\nОбе локации проверяются каждые 2 минуты так, как подключается клиент. "
                "Табло — в закрепе канала, там же посты о сбоях и плановых работах.",
                [[{"text": "Открыть канал", "url": CHANNEL}]] + BACK)
    if screen == "help":
        return "💬 <b>Поддержка</b>\n\n" + _esc(HELP_TEXT), BACK
    user = await _user_by_chat(db, chat_id)
    if user is None and screen in ("sub", "invite"):
        return _esc(NOT_LINKED), BACK
    if screen == "sub":
        return ("💳 <b>Подписка</b>\n\n" + _esc(await _subscription_text(db, user)),
                [[_app("Продлить или сменить тариф", "payment")]] + BACK)
    if screen == "invite":
        text, share = await _invite_text(db, user)
        return "🤝 <b>Пригласить друга</b>\n\n" + _esc(text), (share or []) + BACK
    return await _home(db, chat_id, first_name)


async def _send_screen(db: AsyncSession, chat_id: int, screen: str, first_name: str = "", note: str = "") -> None:
    caption, buttons = await _screen(db, chat_id, screen, first_name)
    if note:
        caption = f"{_esc(note)}\n\n{caption}"
    await telegram.send_menu(chat_id, caption, buttons)


async def _on_callback(db: AsyncSession, cq: dict) -> None:
    msg = cq.get("message") or {}
    chat = msg.get("chat") or {}
    await telegram.answer_callback(cq.get("id", ""))
    data = cq.get("data") or ""
    if chat.get("type") != "private" or not data.startswith("m:"):
        return
    first = (cq.get("from") or {}).get("first_name") or ""
    caption, buttons = await _screen(db, chat["id"], data[2:], first)
    await telegram.edit_menu(chat["id"], msg.get("message_id"), caption, buttons)


async def handle(db: AsyncSession, update: dict) -> None:
    if update.get("callback_query"):
        await _on_callback(db, update["callback_query"])
        return
    msg = update.get("message")
    if not msg or msg.get("chat", {}).get("type") != "private":
        return
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    name = (msg.get("from") or {}).get("username") or (msg.get("from") or {}).get("first_name") or "?"
    first = (msg.get("from") or {}).get("first_name") or ""

    if config.TG_ADMIN_CHAT_ID and chat_id == config.TG_ADMIN_CHAT_ID and msg.get("reply_to_message"):
        await _admin_reply(db, msg)
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        await telegram.drop_keyboard(chat_id)
        if len(parts) == 2 and not parts[1].startswith("ref_"):
            await _send_screen(db, chat_id, "home", first, note=await _link(db, chat_id, parts[1]))
            return
        ref = parts[1][4:] if len(parts) == 2 else ""
        caption, buttons = await _home(db, chat_id, first, ref)
        await telegram.send_menu(chat_id, caption, buttons)
        return
    if text == "/id":
        await telegram.send(chat_id, f"chat id: {chat_id}")
        return
    screens = {"/help": "help", B_HELP: "help", "/status": "status", B_STATUS: "status",
               "/me": "sub", B_SUB: "sub", "/invite": "invite", B_INVITE: "invite",
               "/menu": "home"}
    if text in screens:
        await _send_screen(db, chat_id, screens[text], first)
        return
    if text in (B_RENEW, "/renew"):
        await telegram.send(chat_id, "Продление и оплата — в личном кабинете. Оставшиеся дни сохранятся, "
                                     "новый период добавится после них.",
                            buttons=_site_button("Продлить подписку", "payment"))
        return
    if text.startswith("/"):
        await _send_screen(db, chat_id, "home", first)
        return
    if not text:
        await telegram.send(chat_id, "Пока принимаем только текст. Опишите проблему словами.")
        return
    if "PrivateKey" in text or "[Interface]" in text:
        await telegram.send(chat_id, "Похоже, это файл подключения — в нём ключ вашего устройства. "
                                     "Мы его никуда не передали. Не пересылайте его никому; опишите проблему словами.")
        return
    await telegram.send(chat_id, await _to_support(db, chat_id, name, text))


@router.post("/api/telegram/webhook")
async def webhook(request: Request, db: AsyncSession = Depends(get_db),
                  x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if not config.TG_WEBHOOK_SECRET or not secrets.compare_digest(
            x_telegram_bot_api_secret_token or "", config.TG_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        update = await request.json()
        await handle(db, update)
    except Exception:  # noqa: BLE001
        # Telegram retries a failed update for a day; one bad message must not
        # block the queue behind it.
        logger.exception("telegram update failed")
    return {"ok": True}


# ── the Mini App: the account inside Telegram ───────────────────────────────
#
# The bot's menu button opens https://<site>/app?tg=1 inside Telegram. The page
# sends Telegram.WebApp.initData here; it is signed with the bot's token, so a
# valid signature proves which Telegram user opened it (core.telegram.org/bots/
# webapps#validating-data-received-via-the-mini-app). A user whose Telegram is
# linked gets a session at once; one who is not signs in with the password
# once, and the page links the chat right after.

INIT_DATA_MAX_AGE = 24 * 3600


def verify_init_data(init_data: str, bot_token: str, now: float | None = None) -> dict | None:
    """The Telegram user from signed initData, or None if the signature or age is wrong."""
    import hmac
    import json
    try:
        pairs = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    got = pairs.pop("hash", None)
    if not got or not bot_token:
        return None
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    want = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(want, got):
        return None
    try:
        age = (now or time.time()) - int(pairs.get("auth_date", "0"))
        user = json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None
    if age > INIT_DATA_MAX_AGE or not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    return user


from pydantic import BaseModel, Field  # noqa: E402


class InitData(BaseModel):
    init_data: str = Field(min_length=1, max_length=4096)


@router.post("/api/auth/telegram")
async def tg_login(body: InitData, request: Request, db: AsyncSession = Depends(get_db)):
    from auth.jwt import create_token
    from services import ratelimit
    from services.net import resolve_source_ip
    ratelimit.take(ratelimit.LOGIN_PER_IP, resolve_source_ip(request))
    if not telegram.enabled():
        raise HTTPException(status_code=503, detail="bot is off")
    tg_user = verify_init_data(body.init_data, config.TG_BOT_TOKEN)
    if tg_user is None:
        raise HTTPException(status_code=401, detail="bad init data")
    user = await _user_by_chat(db, tg_user["id"])
    if user is None:
        raise HTTPException(status_code=404, detail="not_linked")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return {"access_token": create_token({"sub": user.username, "role": "client"}),
            "token_type": "bearer", "role": "client", "username": user.username}


@router.post("/api/client/telegram/link-webapp")
async def tg_link_webapp(body: InitData, db: AsyncSession = Depends(get_db), payload: dict = Depends(require_auth)):
    """After a password sign-in inside the Mini App: tie this Telegram to the account."""
    tg_user = verify_init_data(body.init_data, config.TG_BOT_TOKEN or "")
    if tg_user is None:
        raise HTTPException(status_code=401, detail="bad init data")
    user = await _me(db, payload)
    other = await _user_by_chat(db, tg_user["id"])
    if other is not None and other.id != user.id:
        other.telegram_id = None
        await db.flush()
    user.telegram_id = tg_user["id"]
    user.telegram_link_hash = None
    await db.commit()
    return {"ok": True}


# ── starting from the bot: an account without a mailbox ─────────────────────
#
# Someone who has never been on the site opens the bot, taps "try for free",
# and the Mini App offers to create an account: a username, nothing else. The
# Telegram account is what proves a person (it needs a phone number) — one
# trial per Telegram account, as one per confirmed mailbox (api/trial.py).
# Such an account signs in from Telegram only; it has no password to type.


class TgRegister(BaseModel):
    init_data: str = Field(min_length=1, max_length=4096)
    username: str = Field(min_length=3, max_length=27)
    ref: str | None = Field(default=None, max_length=32)


@router.post("/api/auth/telegram/register", status_code=201)
async def tg_register(body: TgRegister, request: Request, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import func
    from api.register import USERNAME_RE
    from auth.jwt import create_token, hash_password
    from services import ratelimit
    from services.net import resolve_source_ip

    ratelimit.take(ratelimit.REGISTER_PER_IP, resolve_source_ip(request))
    if not telegram.enabled():
        raise HTTPException(status_code=503, detail="bot is off")
    tg_user = verify_init_data(body.init_data, config.TG_BOT_TOKEN)
    if tg_user is None:
        raise HTTPException(status_code=401, detail="bad init data")
    if await _user_by_chat(db, tg_user["id"]) is not None:
        # This Telegram already has an account: sign in instead.
        raise HTTPException(status_code=409, detail="already_linked")
    name = body.username.strip()
    if not USERNAME_RE.fullmatch(name):
        raise HTTPException(status_code=422, detail="bad_username")
    taken = (await db.execute(select(User.id).where(func.lower(User.username) == name.lower()))).first()
    if taken:
        raise HTTPException(status_code=409, detail="username_taken")

    referred = None
    if body.ref:
        promo, _ = await credit.resolve_code(db, body.ref, User(id="-"))
        referred = promo.code if promo else None

    user = User(
        username=name,
        email=None,
        # No password anyone knows: this account signs in from Telegram.
        password_hash=hash_password(secrets.token_urlsafe(32)),
        telegram_id=tg_user["id"],
        lang="ru",
        referred_code=referred,
    )
    db.add(user)
    await db.commit()
    logger.info("Account %s created from Telegram", name)
    return {"access_token": create_token({"sub": user.username, "role": "client"}),
            "token_type": "bearer", "role": "client", "username": user.username}
