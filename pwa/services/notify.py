"""
services/notify.py — what the bell says, and when a letter goes with it.

Events and their channels:

    kind              bell   letter   when
    paid              yes    (the receipt is sent by the activation itself)
    granted           yes    (so is the access letter: admin grant)
    trial_started     yes    —        a trial is granted
    trial_ends_1d     yes    yes      under 24 hours left of a trial
    trial_ended       yes    —        the trial's device was taken off
    sub_ends_3d       yes    yes      under 3 days left of a paid period
    sub_ends_1d       yes    —        under 24 hours left
    sub_ended         yes    yes      the period ended and devices came off
    service           yes    —        a message from the operator to everyone

Letters go only where a customer has to act and might not open the portal in
time: renewing before the end, and learning that it ended. Everything else
is in the bell alone — a letter for every event is how letters stop being read.

Reminders are made by the hourly job (expire_subscriptions.py) and are
idempotent through Notification.dedupe_key, which carries the period's end:
several runs inside one window give one message, and a renewed period gets
its own.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Notification, User
from services import mailer

logger = logging.getLogger(__name__)

_MSK = timezone(timedelta(hours=3))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _when(dt: datetime, lang: str) -> str:
    """'09.10 в 14:30 МСК' — Moscow time, which is what customers here read."""
    d = _aware(dt).astimezone(_MSK)
    return d.strftime("%d.%m at %H:%M Moscow time") if lang == "en" else d.strftime("%d.%m в %H:%M МСК")


def _date(dt: datetime) -> str:
    return _aware(dt).astimezone(_MSK).strftime("%d.%m.%Y")


# (title, body) per language. {plan}, {until}, {date} are filled in.
TEXTS = {
    "paid": {
        "ru": ("Оплата получена", "{plan} — подписка действует до {date}."),
        "en": ("Payment received", "{plan} — active until {date}."),
    },
    "granted": {
        "ru": ("Доступ открыт", "{plan} — подписка действует до {date}."),
        "en": ("Your access is open", "{plan} — active until {date}."),
    },
    "trial_started": {
        "ru": ("Пробный период начался", "Устройство готово в «Мой конфиг». Пробный период действует до {until}."),
        "en": ("Your trial has started", "Your device is ready in My config. The trial runs until {until}."),
    },
    "trial_ends_1d": {
        "ru": ("Пробный период заканчивается", "Он закончится {until}. Чтобы продолжить, выберите тариф — "
                                              "при оплате выдаётся устройство с полной скоростью."),
        "en": ("Your trial is ending", "It ends {until}. To carry on, choose a plan — paying issues a device "
                                      "at full speed."),
    },
    "trial_ended": {
        "ru": ("Пробный период закончился", "Устройство пробного периода отключено. Выберите тариф, чтобы продолжить."),
        "en": ("Your trial has ended", "The trial device is switched off. Choose a plan to carry on."),
    },
    "sub_ends_3d": {
        "ru": ("Подписка заканчивается через 3 дня", "Она действует до {until}. Продлите заранее — оставшиеся "
                                                    "дни сохранятся, новый период добавится после них."),
        "en": ("Your subscription ends in 3 days", "It is active until {until}. Renew early — the days left "
                                                  "are kept and the new period is added after them."),
    },
    "sub_ends_1d": {
        "ru": ("Подписка заканчивается завтра", "Она действует до {until}. После этого устройства отключатся."),
        "en": ("Your subscription ends tomorrow", "It is active until {until}. After that your devices stop working."),
    },
    "sub_ended": {
        "ru": ("Подписка закончилась", "Устройства отключены. После продления в «Мой конфиг» появится новый файл."),
        "en": ("Your subscription has ended", "Your devices are switched off. After renewing, a new file appears "
                                             "in My config."),
    },
}

LINKS = {
    "paid": "config", "granted": "config", "trial_started": "config", "trial_ends_1d": "payment", "trial_ended": "payment",
    "sub_ends_3d": "payment", "sub_ends_1d": "payment", "sub_ended": "payment",
}


async def notify(db: AsyncSession, user: User, kind: str, *, dedupe: str | None = None, **params) -> bool:
    """
    Add one message to `user`'s feed. Returns False if `dedupe` says it was
    already sent. Does not commit: the caller's transaction decides.
    """
    lang = "en" if user.lang == "en" else "ru"
    title, body = TEXTS[kind][lang]
    if dedupe is not None:
        exists = (await db.execute(
            select(Notification.id).where(Notification.user_id == user.id, Notification.dedupe_key == dedupe)
        )).first()
        if exists:
            return False
    row = Notification(user_id=user.id, kind=kind, title=title.format(**params), body=body.format(**params),
                       link=LINKS.get(kind), dedupe_key=dedupe)
    try:
        # A savepoint, so a duplicate written by a concurrent run fails alone.
        async with db.begin_nested():
            db.add(row)
    except IntegrityError:
        return False
    return True


async def broadcast(db: AsyncSession, title: str, body: str) -> int:
    """The operator's message to every active account. Commits."""
    users = (await db.execute(select(User.id).where(User.is_active.is_(True)))).scalars().all()
    for uid in users:
        db.add(Notification(user_id=uid, kind="service", title=title, body=body))
    await db.commit()
    logger.info("Broadcast to %d accounts: %s", len(users), title)
    return len(users)


def _letter(user: User, kind: str, until: datetime):
    subject, html, text = mailer.reminder_email(kind, user.username, until, user.lang or "ru")
    mailer.send_later(user.email, subject, html, text)


async def remind_due(db: AsyncSession, now: datetime | None = None) -> dict:
    """
    Reminders before an end: paid periods at 3 days and 1 day, trials at 1 day.
    Run by the hourly job. Each fires once per period (dedupe_key).
    """
    now = now or datetime.now(timezone.utc)
    stats = {"reminders": 0}

    subs = (await db.execute(select(User).where(
        User.is_subscribed.is_(True), User.subscribed_until.is_not(None),
        User.subscribed_until > now, User.subscribed_until <= now + timedelta(days=3),
    ))).scalars().all()
    for u in subs:
        until = _aware(u.subscribed_until)
        lang = "en" if u.lang == "en" else "ru"
        if until <= now + timedelta(days=1):
            kind, key = "sub_ends_1d", f"sub1:{until.isoformat()}"
        else:
            kind, key = "sub_ends_3d", f"sub3:{until.isoformat()}"
        if await notify(db, u, kind, dedupe=key, until=_when(until, lang)):
            stats["reminders"] += 1
            if kind == "sub_ends_3d":
                _letter(u, kind, until)

    trials = (await db.execute(select(User).where(
        User.trial_until.is_not(None), User.trial_until > now, User.trial_until <= now + timedelta(days=1),
    ))).scalars().all()
    for u in trials:
        # A purchase ends the trial early (trial_until = now); nothing to remind.
        if u.subscribed_until is not None and _aware(u.subscribed_until) > now:
            continue
        until = _aware(u.trial_until)
        lang = "en" if u.lang == "en" else "ru"
        if await notify(db, u, "trial_ends_1d", dedupe=f"trial1:{until.isoformat()}", until=_when(until, lang)):
            stats["reminders"] += 1
            _letter(u, "trial_ends_1d", until)

    await db.commit()
    return stats


async def ended(db: AsyncSession, user: User, kind: str, until: datetime) -> None:
    """Called by the expiry sweeps when a period's devices have come off."""
    if await notify(db, user, kind, dedupe=f"{kind}:{_aware(until).isoformat()}"):
        if kind == "sub_ended":
            _letter(user, kind, until)


def describe(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "link": n.link,
            "created_at": n.created_at, "read": n.read_at is not None}
