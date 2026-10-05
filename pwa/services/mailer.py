"""
services/mailer.py — transactional email via Resend HTTP API.

Outbound SMTP (587/465) is blocked at the hosting network level (confirmed
2026-08-05), so this sends over HTTPS instead. Reads:
  RESEND_API_KEY, MAIL_FROM

All sends are best-effort: failures are logged, never raised into the
request path, so a mail outage can't break registration/payment/etc.
"""
import asyncio
import os
import logging
from datetime import datetime, timedelta, timezone
from html import escape

import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Sovereign <support@sov3r3ign.com>")
SUPPORT_INBOX = os.getenv("SUPPORT_INBOX", "sovrn.support@gmail.com")
RESEND_API = "https://api.resend.com/emails"


async def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> bool:
    """
    Send an email via Resend. Returns True on success, False on failure.
    Never raises — failures are logged so callers can ignore the result safely.
    """
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return False

    payload = {"from": MAIL_FROM, "to": [to], "subject": subject, "html": body_html}
    if body_text:
        payload["text"] = body_text
    headers = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(RESEND_API, headers=headers, json=payload)
            resp.raise_for_status()
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False



# Letters sent from inside a gateway callback should not hold up the answer to
# the gateway: Resend can take seconds, and a slow acknowledgement is how a
# callback gets retried. These go out after the response, from the same
# process. The set keeps a reference to each task — the event loop holds only
# a weak one, and an unreferenced task can be collected before it runs.
_pending: set = set()


def send_later(to: str, subject: str, body_html: str, body_text: str = "") -> None:
    task = asyncio.get_running_loop().create_task(send_email(to, subject, body_html, body_text))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for letters scheduled with send_later. For tests and shutdown."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)

# ── Email templates (RU / EN) ────────────────────────────────────────
#
# Everything that came from a request is escaped before it goes into HTML.
# The welcome letter used to put the username in raw, and registration took
# any username and any address: one request made support@sov3r3ign.com send
# a stranger a letter with someone else's markup and links in it. Escaping
# here holds even if a field's own validation is ever loosened.

SITE_URL = os.getenv("PORTAL_BASE_URL", "https://sov3r3ign.com")

# The portal's palette (landing.html :root). Mail clients ignore <style> and
# CSS variables, so every colour is written inline where it is used.
_BG, _CARD, _BORDER = "#080c0f", "#0d1318", "#1e2d38"
_TEXT, _DIM, _BRIGHT, _ACCENT = "#d8eaf6", "#7a9fb5", "#e8f4ff", "#00d4ff"
_FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# Moscow time has had no daylight saving since 2014, so a fixed offset is
# exact and needs no time-zone database in the container.
_MSK = timezone(timedelta(hours=3))


def _wrap(inner_html: str, preheader: str = "") -> str:
    """
    The frame every letter shares: wordmark, card, footer.

    Tables, not divs, because that is what Outlook and the older mobile
    clients lay out reliably. `preheader` is the line a mail list shows under
    the subject; it is hidden in the letter itself.
    """
    hidden = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{_BG}">'
        f"{escape(preheader)}</div>" if preheader else ""
    )
    return f"""\
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark"></head>
<body style="margin:0;padding:0;background:{_BG}">
{hidden}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG}">
<tr><td align="center" style="padding:40px 16px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px">
    <tr><td style="padding:0 4px 28px;font-family:{_FONT};font-size:22px;font-weight:700;letter-spacing:-0.3px;color:{_BRIGHT}">
      Sover<span style="color:{_ACCENT}">ei</span>gn
    </td></tr>
    <tr><td style="background:{_CARD};border:1px solid {_BORDER};border-radius:12px;padding:32px 28px;font-family:{_FONT};font-size:15px;line-height:1.65;color:{_TEXT}">
      {inner_html}
    </td></tr>
    <tr><td style="padding:24px 4px 0;font-family:{_FONT};font-size:12px;line-height:1.6;color:{_DIM}">
      <a href="{escape(SITE_URL, quote=True)}" style="color:{_DIM};text-decoration:underline">{escape(SITE_URL.split("://", 1)[-1])}</a>
      &nbsp;·&nbsp; {escape(SUPPORT_INBOX)}
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""


def _h(text: str) -> str:
    return f'<p style="margin:0 0 16px;font-size:20px;font-weight:600;line-height:1.35;color:{_BRIGHT}">{text}</p>'


def _p(text: str, dim: bool = False, last: bool = False) -> str:
    colour = f"color:{_DIM};font-size:13px;" if dim else ""
    return f'<p style="margin:0 0 {0 if last else 16}px;{colour}">{text}</p>'


def _button(href: str, label: str) -> str:
    """A link styled as a button; a table cell so Outlook keeps the fill."""
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 24px">
<tr><td style="border-radius:8px;background:{_ACCENT}">
  <a href="{escape(href, quote=True)}" style="display:inline-block;padding:13px 28px;font-family:{_FONT};font-size:15px;font-weight:600;color:{_BG};text-decoration:none;border-radius:8px">{label}</a>
</td></tr></table>"""


def _fallback_link(href: str, lang: str) -> str:
    lead = "If the button does not open, copy this address into your browser:" if lang == "en" \
        else "Если кнопка не открывается, скопируйте адрес в браузер:"
    return _p(
        f'{lead}<br><span style="word-break:break-all;color:{_TEXT}">{escape(href)}</span>',
        dim=True,
    )


def _steps(items: list[str]) -> str:
    rows = "".join(
        f'<tr><td valign="top" style="padding:0 12px 10px 0;font-family:{_FONT};font-size:13px;'
        f'font-weight:600;color:{_ACCENT}">{n}</td>'
        f'<td style="padding:0 0 10px;font-family:{_FONT};font-size:15px;color:{_TEXT}">{t}</td></tr>'
        for n, t in enumerate(items, 1)
    )
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 8px">{rows}</table>'


def welcome_email(username: str, verify_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """
    The first letter: welcome and mailbox confirmation in one.

    One letter rather than two. Two arriving in the same minute read as a
    mailing, and are filtered as one more often.
    """
    name = escape(username)
    if lang == "en":
        subject = "Confirm your email — Sovereign"
        inner = (
            _h(f"Welcome, {name}")
            + _p("Your account has been created. One step is left: confirm that this address is yours.")
            + _button(verify_url, "Confirm email")
            + _p("What comes next:")
            + _steps([
                "Choose a plan in your account.",
                "Install AmneziaWG on your phone or computer.",
                "Download your device file from the account and import it.",
            ])
            + _fallback_link(verify_url, lang)
            + _p("The link is valid for 48 hours. If you did not create an account, ignore this letter: "
                 "without confirmation, nothing can be bought with this address.", dim=True, last=True)
        )
        text = (f"Welcome to Sovereign, {username}.\n\nConfirm your email (valid 48 hours):\n{verify_url}\n\n"
                "If you did not create an account, ignore this letter.")
        pre = "One step left: confirm your address."
    else:
        subject = "Подтвердите почту — Sovereign"
        inner = (
            _h(f"Добро пожаловать, {name}")
            + _p("Аккаунт создан. Остался один шаг — подтвердите, что этот адрес ваш.")
            + _button(verify_url, "Подтвердить почту")
            + _p("Что дальше:")
            + _steps([
                "Выберите тариф в личном кабинете.",
                "Установите AmneziaWG на телефон или компьютер.",
                "Скачайте файл устройства из кабинета и импортируйте его в приложение.",
            ])
            + _fallback_link(verify_url, lang)
            + _p("Ссылка действует 48 часов. Если вы не регистрировались — просто проигнорируйте письмо: "
                 "без подтверждения оформить что-либо на этот адрес нельзя.", dim=True, last=True)
        )
        text = (f"Добро пожаловать в Sovereign, {username}.\n\nПодтвердите почту (ссылка действует 48 часов):\n"
                f"{verify_url}\n\nЕсли вы не регистрировались — проигнорируйте письмо.")
        pre = "Остался один шаг — подтвердите адрес."
    return subject, _wrap(inner, pre), text


def verification_email(verify_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """A fresh confirmation link, sent when the customer asks for one again."""
    if lang == "en":
        subject = "Confirm your email — Sovereign"
        inner = (
            _h("Confirm your email")
            + _p("Here is a new confirmation link. Earlier links no longer work.")
            + _button(verify_url, "Confirm email")
            + _fallback_link(verify_url, lang)
            + _p("The link is valid for 48 hours.", dim=True, last=True)
        )
        text = f"Confirm your Sovereign email (valid 48 hours):\n{verify_url}"
        pre = "A new confirmation link."
    else:
        subject = "Подтвердите почту — Sovereign"
        inner = (
            _h("Подтверждение почты")
            + _p("Вот новая ссылка для подтверждения. Прежние ссылки больше не действуют.")
            + _button(verify_url, "Подтвердить почту")
            + _fallback_link(verify_url, lang)
            + _p("Ссылка действует 48 часов.", dim=True, last=True)
        )
        text = f"Подтвердите почту Sovereign (ссылка действует 48 часов):\n{verify_url}"
        pre = "Новая ссылка для подтверждения."
    return subject, _wrap(inner, pre), text


_TIER = {"basic": ("Базовый", "Basic"), "ext": ("Расширенный", "Extended")}
_PERIOD = {30: ("1 месяц", "1 month"), 90: ("3 месяца", "3 months"), 180: ("6 месяцев", "6 months")}


def plan_title(tier: str, days: int, lang: str = "ru") -> str:
    i = 1 if lang == "en" else 0
    t = _TIER.get(tier, (tier, tier))[i]
    d = _PERIOD.get(days, (f"{days} дн.", f"{days} days"))[i]
    return f"{t}, {d}"


def payment_email(
    username: str, tier: str, days: int, amount: int, currency: str,
    until: datetime, first: bool, lang: str = "ru",
) -> tuple[str, str, str]:
    """The receipt, sent once when a payment is activated."""
    name = escape(username)
    plan = escape(plan_title(tier, days, lang))
    date = until.astimezone(_MSK).strftime("%d.%m.%Y")
    money = f"{amount:,}".replace(",", " ") + (" ₽" if currency == "RUB" else f" {escape(currency)}")
    portal = f"{SITE_URL}/app"

    def row(label, value):
        return (f'<tr><td style="padding:6px 16px 6px 0;font-family:{_FONT};font-size:14px;color:{_DIM}">{label}</td>'
                f'<td style="padding:6px 0;font-family:{_FONT};font-size:14px;color:{_BRIGHT};font-weight:600">{value}</td></tr>')

    if lang == "en":
        subject = "Payment received — Sovereign"
        table = row("Plan", plan) + row("Paid", money) + row("Active until", date)
        next_line = ("Your first device has been created. Download its file in your account and import it into AmneziaWG."
                     if first else "The days you had left are kept: the new period is added after them.")
        inner = (
            _h(f"Thank you, {name}")
            + _p("Payment received, your subscription is active.")
            + f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px">{table}</table>'
            + _p(next_line)
            + _button(portal, "Open your account")
            + _p("Keep this letter as a record of the payment.", dim=True, last=True)
        )
        text = (f"Payment received, {username}.\nPlan: {plan_title(tier, days, lang)}\nPaid: {money}\n"
                f"Active until: {date}\n\n{next_line}\n{portal}")
        pre = f"Active until {date}."
    else:
        subject = "Оплата получена — Sovereign"
        table = row("Тариф", plan) + row("Оплачено", money) + row("Действует до", date)
        next_line = ("Первое устройство уже создано — скачайте его файл в личном кабинете и импортируйте в AmneziaWG."
                     if first else "Оставшиеся дни сохранены: новый период добавлен после них.")
        inner = (
            _h(f"Спасибо, {name}")
            + _p("Оплата получена, подписка активна.")
            + f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px">{table}</table>'
            + _p(next_line)
            + _button(portal, "Открыть личный кабинет")
            + _p("Сохраните это письмо как подтверждение оплаты.", dim=True, last=True)
        )
        text = (f"Оплата получена, {username}.\nТариф: {plan_title(tier, days, lang)}\nОплачено: {money}\n"
                f"Действует до: {date}\n\n{next_line}\n{portal}")
        pre = f"Подписка действует до {date}."
    return subject, _wrap(inner, pre), text


def password_reset_email(reset_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a password reset."""
    if lang == "en":
        subject = "Reset your password — Sovereign"
        inner = (
            _h("Password reset")
            + _p("We received a request to reset your password. Set a new one with the button below.")
            + _button(reset_url, "Set a new password")
            + _fallback_link(reset_url, lang)
            + _p("The link is valid for 1 hour and works once. If you did not ask for this, ignore the letter — "
                 "your password stays as it is.", dim=True, last=True)
        )
        text = (f"Reset your Sovereign password (valid 1 hour):\n{reset_url}\n\n"
                "If you did not ask for this, ignore this letter.")
        pre = "A link to set a new password."
    else:
        subject = "Сброс пароля — Sovereign"
        inner = (
            _h("Сброс пароля")
            + _p("Мы получили запрос на сброс пароля. Задайте новый по кнопке ниже.")
            + _button(reset_url, "Задать новый пароль")
            + _fallback_link(reset_url, lang)
            + _p("Ссылка действует 1 час и срабатывает один раз. Если вы не запрашивали сброс — "
                 "проигнорируйте письмо, пароль останется прежним.", dim=True, last=True)
        )
        text = (f"Сброс пароля Sovereign (ссылка действует 1 час):\n{reset_url}\n\n"
                "Если вы не запрашивали сброс — проигнорируйте письмо.")
        pre = "Ссылка, чтобы задать новый пароль."
    return subject, _wrap(inner, pre), text


def support_ticket_email(category: str, details: dict, user_email: str) -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a support ticket (to support inbox)."""
    subject = f"[Support] {category}"
    rows = "".join(
        f'<p style="margin:0 0 8px"><b style="color:#7a9fb5">{escape(str(k))}:</b> {escape(str(v))}</p>'
        for k, v in details.items() if v
    )
    inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">New support request</p>
        <p style="margin:0 0 8px"><b style="color:#7a9fb5">Category:</b> {escape(category)}</p>
        {rows}
        <p style="margin:16px 0 0"><b style="color:#7a9fb5">From:</b> {escape(user_email)}</p>"""
    text = f"New support request. Category: {category}. From: {user_email}. Details: {details}"
    return subject, _wrap(inner), text
