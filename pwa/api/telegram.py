"""
api/telegram.py — the customers' Telegram bot.

What it does:
  * linking: the account's "Connect Telegram" makes a one-time link
    t.me/<bot>?start=<token> (15 minutes); opening it ties that chat to the
    account. Nothing is typed into the bot — no login, no password.
  * notifications: everything that goes to the bell goes to the chat too
    (services/notify.py), with a button to the right page of the account.
  * buttons: subscription, renew (opens the site — payment stays there),
    invite a friend (the referral link, ready to forward), status (the
    channel's live board).
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

B_SUB, B_RENEW, B_INVITE, B_STATUS, B_HELP = "📋 Подписка", "💳 Продлить", "🎁 Пригласить друга", "📡 Статус", "💬 Поддержка"
KEYBOARD = [[B_SUB, B_RENEW], [B_INVITE, B_STATUS], [B_HELP]]

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

WELCOME = ("Это бот сервиса Sovereign.\n\n"
           "Здесь — уведомления о подписке, продление, ссылка для друзей, статус локаций и поддержка.\n\n"
           "Чтобы бот узнал ваш аккаунт: личный кабинет → «Настройки» → «Подключить Telegram».")
NOT_LINKED = ("Бот пока не знает ваш аккаунт. Подключите его в личном кабинете: "
              "«Настройки» → «Подключить Telegram».")


def _site_button(text: str, page: str) -> list[list[dict]]:
    return [[{"text": text, "url": f"{SITE}/app#{page}"}]]


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


async def handle(db: AsyncSession, update: dict) -> None:
    msg = update.get("message")
    if not msg or msg.get("chat", {}).get("type") != "private":
        return
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    name = (msg.get("from") or {}).get("username") or (msg.get("from") or {}).get("first_name") or "?"

    if config.TG_ADMIN_CHAT_ID and chat_id == config.TG_ADMIN_CHAT_ID and msg.get("reply_to_message"):
        await _admin_reply(db, msg)
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        reply = await _link(db, chat_id, parts[1]) if len(parts) == 2 else WELCOME
        await telegram.send(chat_id, reply, keyboard=KEYBOARD)
        return
    if text == "/id":
        await telegram.send(chat_id, f"chat id: {chat_id}")
        return
    if text in ("/help", B_HELP):
        await telegram.send(chat_id, "Опишите проблему одним сообщением — устройство, сеть (Wi-Fi или мобильная, "
                                     "оператор), локацию и что происходит. Ответим здесь.\n\n"
                                     "Не присылайте файлы подключения и пароли.")
        return
    if text in ("/status", B_STATUS):
        await telegram.send(chat_id, "Статус обеих локаций обновляется каждые 2 минуты в закрепе канала.",
                            buttons=[[{"text": "Открыть статус", "url": CHANNEL}]])
        return

    user = await _user_by_chat(db, chat_id)
    if text in (B_SUB, "/me"):
        await telegram.send(chat_id, await _subscription_text(db, user) if user else NOT_LINKED,
                            buttons=_site_button("Открыть кабинет", "config") if user else None)
        return
    if text in (B_RENEW, "/renew"):
        await telegram.send(chat_id, "Продление и оплата — в личном кабинете. Оставшиеся дни сохранятся, "
                                     "новый период добавится после них.",
                            buttons=_site_button("Продлить подписку", "payment"))
        return
    if text in (B_INVITE, "/invite"):
        if not user:
            await telegram.send(chat_id, NOT_LINKED)
            return
        t, b = await _invite_text(db, user)
        await telegram.send(chat_id, t, buttons=b)
        return
    if text.startswith("/"):
        await telegram.send(chat_id, WELCOME, keyboard=KEYBOARD)
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
