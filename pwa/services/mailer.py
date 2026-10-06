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

SITE_URL = os.getenv("PORTAL_BASE_URL", "https://sov3r3ign.com").rstrip("/")

# ── The letter system ─────────────────────────────────────────────────
#
# Every letter is built from the components below, so they read as one
# product. The rules they encode (docs/email-style.md has the reasoning):
#
#   * one letter, one action — a single primary button, never two;
#   * the subject says what happened or what to do, then "— Sovereign";
#   * a preheader, the line a mail list shows under the subject;
#   * every button's address is also spelled out, for clients that drop
#     buttons and for people who check a link before following it;
#   * a plain-text part with the same content;
#   * the footer says why this address received the letter;
#   * the public-wording rule applies (tests/test_public_wording.py).
#
# Mail clients ignore <style>, CSS variables and most of modern CSS, so the
# layout is tables with inline styles, and every colour is written where it
# is used. The palette is the portal's (landing.html :root).

_BG, _CARD, _BORDER, _RAISED = "#080c0f", "#0d1318", "#1e2d38", "#111a21"
_TEXT, _DIM, _BRIGHT, _ACCENT, _ACCENT_DIM = "#d8eaf6", "#7a9fb5", "#e8f4ff", "#00d4ff", "#006a80"
_GREEN = "#00ff88"
_FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_MONO = "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# Moscow time has had no daylight saving since 2014, so a fixed offset is
# exact and needs no time-zone database in the container.
_MSK = timezone(timedelta(hours=3))

_FOOTER = {
    "ru": {"account": "Личный кабинет", "support": "Поддержка", "terms": "Соглашение",
           "fallback": "Если кнопка не открывается, скопируйте адрес в браузер:"},
    "en": {"account": "Your account", "support": "Support", "terms": "Terms",
           "fallback": "If the button does not open, copy this address into your browser:"},
}


def _L(lang: str) -> dict:
    return _FOOTER["en" if lang == "en" else "ru"]


def _wrap(inner_html: str, preheader: str = "", lang: str = "ru", reason: str = "") -> str:
    """
    The frame: header with the mark, a card with an accent edge, the footer.

    `reason` is the footer's "why you got this" line. A letter that does not
    say why it arrived is the one people mark as spam.
    """
    L = _L(lang)
    site = escape(SITE_URL, quote=True)
    host = escape(SITE_URL.split("://", 1)[-1])
    hidden = (
        f'<div style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;'
        f'font-size:1px;line-height:1px;color:{_BG}">{escape(preheader)}'
        # Pads the preview so the client does not fill it with body text.
        f'{"&#8199;&#847; " * 40}</div>' if preheader else ""
    )
    link = f"color:{_DIM};text-decoration:none"
    return f"""\
<!DOCTYPE html>
<html lang="{'en' if lang == 'en' else 'ru'}">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
<title>Sovereign</title></head>
<body style="margin:0;padding:0;background:{_BG}" bgcolor="{_BG}">
{hidden}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_BG}" style="background:{_BG}">
<tr><td align="center" style="padding:36px 14px 40px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:540px">
    <tr><td style="padding:0 6px 22px">
      <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
        <td valign="middle" style="padding-right:12px">
          <a href="{site}" style="text-decoration:none"><img src="{site}/static/icons/icon-192.png" width="34" height="34" alt="" style="display:block;border:0;border-radius:8px"></a>
        </td>
        <td valign="middle" style="font-family:{_FONT};font-size:21px;font-weight:700;letter-spacing:-0.3px;color:{_BRIGHT}">
          <a href="{site}" style="color:{_BRIGHT};text-decoration:none">Sover<span style="color:{_ACCENT}">ei</span>gn</a>
        </td>
      </tr></table>
    </td></tr>
    <tr><td bgcolor="{_ACCENT}" style="height:3px;line-height:3px;font-size:0;background:{_ACCENT};border-radius:12px 12px 0 0">&nbsp;</td></tr>
    <tr><td bgcolor="{_CARD}" style="background:{_CARD};border:1px solid {_BORDER};border-top:0;border-radius:0 0 12px 12px;padding:34px 30px 32px;font-family:{_FONT};font-size:15px;line-height:1.65;color:{_TEXT}">
      {inner_html}
    </td></tr>
    <tr><td style="padding:24px 6px 0;font-family:{_FONT};font-size:13px;line-height:1.7;color:{_DIM}">
      <a href="{site}/app" style="{link}">{L["account"]}</a>
      &nbsp;·&nbsp; <a href="mailto:{escape(SUPPORT_INBOX, quote=True)}" style="{link}">{L["support"]}</a>
      &nbsp;·&nbsp; <a href="{site}/offer" style="{link}">{L["terms"]}</a>
    </td></tr>
    <tr><td style="padding:10px 6px 0;font-family:{_FONT};font-size:12px;line-height:1.6;color:#4f6a7a">
      {reason}{"<br>" if reason else ""}© Sovereign · {host}
    </td></tr>
  </table>
</td></tr>
</table>
</body>
</html>"""


def _eyebrow(text: str) -> str:
    return (f'<p style="margin:0 0 10px;font-family:{_MONO};font-size:11px;letter-spacing:1.8px;'
            f'text-transform:uppercase;color:{_ACCENT}">{text}</p>')


def _h(text: str) -> str:
    return (f'<p style="margin:0 0 14px;font-size:24px;font-weight:600;line-height:1.3;'
            f'letter-spacing:-0.3px;color:{_BRIGHT}">{text}</p>')


def _p(text: str, dim: bool = False, last: bool = False) -> str:
    colour = f"color:{_DIM};font-size:13px;line-height:1.6;" if dim else ""
    return f'<p style="margin:0 0 {0 if last else 16}px;{colour}">{text}</p>'


def _button(href: str, label: str) -> str:
    """The letter's one action. A table cell, so Outlook keeps the fill."""
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:10px 0 26px">
<tr><td bgcolor="{_ACCENT}" style="border-radius:8px;background:{_ACCENT}">
  <a href="{escape(href, quote=True)}" style="display:inline-block;padding:14px 30px;font-family:{_FONT};font-size:15px;font-weight:600;line-height:1.2;color:#04191f;text-decoration:none;border-radius:8px">{label}&nbsp;&nbsp;→</a>
</td></tr></table>"""


def _fallback_link(href: str, lang: str) -> str:
    return (f'<p style="margin:0 0 16px;font-size:12px;line-height:1.6;color:{_DIM}">{_L(lang)["fallback"]}<br>'
            f'<a href="{escape(href, quote=True)}" style="color:{_DIM};word-break:break-all;'
            f'text-decoration:underline">{escape(href)}</a></p>')


def _divider() -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
            f'<tr><td style="padding:6px 0 22px"><div style="height:1px;line-height:1px;font-size:0;'
            f'background:{_BORDER}">&nbsp;</div></td></tr></table>')


def _section(title: str) -> str:
    return (f'<p style="margin:0 0 14px;font-size:12px;letter-spacing:1.6px;text-transform:uppercase;'
            f'color:{_DIM}">{title}</p>')


def _steps(items: list[tuple[str, str]]) -> str:
    """Numbered steps: (bold lead, the rest)."""
    rows = "".join(
        f'<tr><td valign="top" width="40" style="padding:0 14px 16px 0">'
        f'<div style="width:26px;height:26px;line-height:26px;border:1px solid {_ACCENT_DIM};border-radius:50%;'
        f'text-align:center;font-family:{_MONO};font-size:12px;color:{_ACCENT}">{n}</div></td>'
        f'<td valign="top" style="padding:2px 0 16px;font-family:{_FONT};font-size:15px;line-height:1.55;color:{_TEXT}">'
        f'<span style="color:{_BRIGHT};font-weight:600">{lead}</span>'
        f'{"<br>" if rest else ""}<span style="color:{_DIM};font-size:14px">{rest}</span></td></tr>'
        for n, (lead, rest) in enumerate(items, 1)
    )
    return f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 6px">{rows}</table>'


def _callout(badge: str, text: str) -> str:
    """A tinted panel for one secondary fact — never a second button."""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 24px">
<tr><td bgcolor="{_RAISED}" style="background:{_RAISED};border:1px solid {_ACCENT_DIM};border-radius:10px;padding:16px 18px">
  <p style="margin:0 0 6px;font-family:{_MONO};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:{_ACCENT}">{badge}</p>
  <p style="margin:0;font-family:{_FONT};font-size:14px;line-height:1.6;color:{_TEXT}">{text}</p>
</td></tr></table>"""


def _facts(rows: list[tuple[str, str]]) -> str:
    """Label / value pairs, as on a receipt."""
    body = "".join(
        f'<tr><td style="padding:10px 16px 10px 0;border-bottom:1px solid {_BORDER};font-family:{_FONT};'
        f'font-size:14px;color:{_DIM}">{k}</td>'
        f'<td align="right" style="padding:10px 0;border-bottom:1px solid {_BORDER};font-family:{_FONT};'
        f'font-size:14px;font-weight:600;color:{_BRIGHT}">{v}</td></tr>'
        for k, v in rows
    )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 22px">{body}</table>'


def _days_ru(n: int) -> str:
    a, b = n % 100, n % 10
    return f"{n} " + ("дней" if 10 < a < 20 else "день" if b == 1 else "дня" if 2 <= b <= 4 else "дней")


def _trial_offer() -> tuple[bool, int]:
    # Imported here: services.trial reads the environment at call time, and the
    # letter should say what is true when it is sent.
    from services.trial import TRIAL_DAYS, trial_enabled
    return trial_enabled(), TRIAL_DAYS


def welcome_email(username: str, verify_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """
    The first letter: welcome and mailbox confirmation in one.

    One letter rather than two. Two arriving in the same minute read as a
    mailing, and are filtered as one more often. It mentions the trial only
    while trials are on.
    """
    name = escape(username)
    trial_on, days = _trial_offer()
    host = escape(SITE_URL.split("://", 1)[-1])
    if lang == "en":
        subject = "Confirm your email — Sovereign"
        steps = [
            ("Confirm your email", "the button above; it takes a second"),
            ("Start the free trial or choose a plan", "both are in your account"),
            ("Install AmneziaWG and import your device file", "the account shows how, step by step"),
        ]
        inner = (
            _eyebrow("Registration")
            + _h(f"Welcome, {name}")
            + _p("Your account is ready. Confirm that this address is yours — receipts, "
                 "password resets and notices about the service come here.")
            + _button(verify_url, "Confirm email")
            + (_callout(f"{days} days free",
                        "Once your email is confirmed, start the trial in your account: one device, "
                        "no payment, no card.") if trial_on else "")
            + _section("What comes next")
            + _steps(steps)
            + _divider()
            + _fallback_link(verify_url, lang)
            + _p("The link is valid for 48 hours. If you did not sign up, just delete this letter: "
                 "nothing can be bought with an unconfirmed address.", dim=True, last=True)
        )
        reason = f"You received this because this address was used to sign up at {host}."
        text = (f"Welcome to Sovereign, {username}.\n\nConfirm your email (valid 48 hours):\n{verify_url}\n\n"
                + (f"Once confirmed, you can start a {days}-day free trial in your account.\n\n" if trial_on else "")
                + "If you did not sign up, delete this letter.")
        pre = "One step left: confirm your address."
    else:
        subject = "Подтвердите почту — Sovereign"
        steps = [
            ("Подтвердите почту", "кнопка выше, это одна секунда"),
            ("Активируйте пробный период или выберите тариф" if trial_on else "Выберите тариф",
             "всё в личном кабинете"),
            ("Установите AmneziaWG и импортируйте файл устройства", "в кабинете есть пошаговая инструкция"),
        ]
        inner = (
            _eyebrow("Регистрация")
            + _h(f"Добро пожаловать, {name}")
            + _p("Аккаунт готов. Подтвердите, что этот адрес ваш — на него придут чек об оплате, "
                 "ссылка для восстановления пароля и уведомления о сервисе.")
            + _button(verify_url, "Подтвердить почту")
            + (_callout(f"{_days_ru(days)} бесплатно",
                        "После подтверждения почты в личном кабинете можно активировать пробный период: "
                        "одно устройство, без оплаты и без карты.") if trial_on else "")
            + _section("Что дальше")
            + _steps(steps)
            + _divider()
            + _fallback_link(verify_url, lang)
            + _p("Ссылка действует 48 часов. Если вы не регистрировались — просто удалите письмо: "
                 "без подтверждения на этот адрес ничего не оформить.", dim=True, last=True)
        )
        reason = f"Вы получили это письмо, потому что этот адрес указали при регистрации на {host}."
        text = (f"Добро пожаловать в Sovereign, {username}.\n\nПодтвердите почту (ссылка действует 48 часов):\n"
                f"{verify_url}\n\n"
                + (f"После подтверждения в личном кабинете можно активировать пробный период "
                   f"на {_days_ru(days)}.\n\n" if trial_on else "")
                + "Если вы не регистрировались — удалите письмо.")
        pre = "Остался один шаг — подтвердите адрес."
    return subject, _wrap(inner, pre, lang, reason), text


def verification_email(verify_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """A fresh confirmation link, sent when the customer asks for one again."""
    host = escape(SITE_URL.split("://", 1)[-1])
    if lang == "en":
        subject = "Confirm your email — Sovereign"
        inner = (
            _eyebrow("Email confirmation")
            + _h("Here is a new link")
            + _p("You asked for the confirmation letter again. Earlier links no longer work.")
            + _button(verify_url, "Confirm email")
            + _fallback_link(verify_url, lang)
            + _p("The link is valid for 48 hours.", dim=True, last=True)
        )
        reason = f"You received this because a confirmation link was requested from your account at {host}."
        text = f"Confirm your Sovereign email (valid 48 hours):\n{verify_url}"
        pre = "A new confirmation link."
    else:
        subject = "Подтвердите почту — Sovereign"
        inner = (
            _eyebrow("Подтверждение почты")
            + _h("Новая ссылка")
            + _p("Вы запросили письмо для подтверждения ещё раз. Прежние ссылки больше не действуют.")
            + _button(verify_url, "Подтвердить почту")
            + _fallback_link(verify_url, lang)
            + _p("Ссылка действует 48 часов.", dim=True, last=True)
        )
        reason = f"Вы получили это письмо, потому что ссылку для подтверждения запросили в личном кабинете на {host}."
        text = f"Подтвердите почту Sovereign (ссылка действует 48 часов):\n{verify_url}"
        pre = "Новая ссылка для подтверждения."
    return subject, _wrap(inner, pre, lang, reason), text


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
    money = f"{amount:,}".replace(",", " ") + (" ₽" if currency == "RUB" else f" {escape(currency)}")
    portal = f"{SITE_URL}/app"
    host = escape(SITE_URL.split("://", 1)[-1])

    if lang == "en":
        subject = "Payment received — Sovereign"
        next_line = ("Your first device has been created. Download its file in your account and import it into AmneziaWG."
                     if first else "The days you had left are kept: the new period is added after them.")
        inner = (
            _eyebrow("Receipt")
            + _h(f"Thank you, {name}")
            + _p("Payment received, your subscription is active.")
            + _facts([("Plan", plan), ("Paid", money), ("Active until", date)])
            + _p(next_line)
            + _button(portal, "Open your account")
            + _p("Keep this letter as a record of the payment.", dim=True, last=True)
        )
        reason = f"You received this because a payment was made from your account at {host}."
        text = (f"Payment received, {username}.\nPlan: {plan_title(tier, days, lang)}\nPaid: {money}\n"
                f"Active until: {date}\n\n{next_line}\n{portal}")
        pre = f"Active until {date}."
    else:
        subject = "Оплата получена — Sovereign"
        next_line = ("Первое устройство уже создано — скачайте его файл в личном кабинете и импортируйте в AmneziaWG."
                     if first else "Оставшиеся дни сохранены: новый период добавлен после них.")
        inner = (
            _eyebrow("Чек")
            + _h(f"Спасибо, {name}")
            + _p("Оплата получена, подписка активна.")
            + _facts([("Тариф", plan), ("Оплачено", money), ("Действует до", date)])
            + _p(next_line)
            + _button(portal, "Открыть личный кабинет")
            + _p("Сохраните это письмо как подтверждение оплаты.", dim=True, last=True)
        )
        reason = f"Вы получили это письмо, потому что с вашего аккаунта на {host} была произведена оплата."
        text = (f"Оплата получена, {username}.\nТариф: {plan_title(tier, days, lang)}\nОплачено: {money}\n"
                f"Действует до: {date}\n\n{next_line}\n{portal}")
        pre = f"Подписка действует до {date}."
    return subject, _wrap(inner, pre, lang, reason), text


def granted_email(
    username: str, tier: str, days: int, until: datetime, first: bool, lang: str = "ru",
) -> tuple[str, str, str]:
    """Access opened by the operator (a gift, or moving a customer over from
    before the portal). Like the receipt, without the money."""
    name = escape(username)
    plan = escape(plan_title(tier, days, lang))
    date = until.astimezone(_MSK).strftime("%d.%m.%Y")
    portal = f"{SITE_URL}/app"
    host = escape(SITE_URL.split("://", 1)[-1])
    if lang == "en":
        subject = "Your access is open — Sovereign"
        next_line = ("Your first device has been created. Download its file in your account and import it into AmneziaWG."
                     if first else "The days you had left are kept: the new period is added after them.")
        inner = (
            _eyebrow("Access")
            + _h(f"{name}, your access is open")
            + _p("Your subscription is active. There is nothing to pay.")
            + _facts([("Plan", plan), ("Active until", date)])
            + _p(next_line)
            + _button(portal, "Open your account")
            + _fallback_link(portal, lang)
            + _p("Renewing later works the same as for everyone: from the account, whenever you like.",
                 dim=True, last=True)
        )
        reason = f"You received this because access was opened for your account at {host}."
        text = (f"Your Sovereign access is open, {username}.\nPlan: {plan_title(tier, days, lang)}\n"
                f"Active until: {date}\n\n{next_line}\n{portal}")
        pre = f"Active until {date}."
    else:
        subject = "Доступ открыт — Sovereign"
        next_line = ("Первое устройство уже создано — скачайте его файл в личном кабинете и импортируйте в AmneziaWG."
                     if first else "Оставшиеся дни сохранены: новый период добавлен после них.")
        inner = (
            _eyebrow("Доступ")
            + _h(f"{name}, доступ открыт")
            + _p("Подписка активна, оплачивать ничего не нужно.")
            + _facts([("Тариф", plan), ("Действует до", date)])
            + _p(next_line)
            + _button(portal, "Открыть личный кабинет")
            + _fallback_link(portal, lang)
            + _p("Продлить потом можно как обычно — в личном кабинете, когда удобно.", dim=True, last=True)
        )
        reason = f"Вы получили это письмо, потому что для вашего аккаунта на {host} открыт доступ."
        text = (f"Доступ Sovereign открыт, {username}.\nТариф: {plan_title(tier, days, lang)}\n"
                f"Действует до: {date}\n\n{next_line}\n{portal}")
        pre = f"Подписка действует до {date}."
    return subject, _wrap(inner, pre, lang, reason), text


def reminder_email(kind: str, username: str, until: datetime, lang: str = "ru") -> tuple[str, str, str]:
    """
    Letters about an end: a paid period in 3 days, a paid period that has
    ended, a trial with under a day left. The same message is in the bell;
    these are the three where missing it costs the customer their connection.
    """
    name = escape(username)
    d = until.astimezone(_MSK)
    date, time = d.strftime("%d.%m.%Y"), d.strftime("%H:%M")
    portal = f"{SITE_URL}/app"
    host = escape(SITE_URL.split("://", 1)[-1])
    en = lang == "en"
    if kind == "sub_ends_3d":
        subject = "Your subscription ends in 3 days — Sovereign" if en else "Подписка заканчивается через 3 дня — Sovereign"
        inner = (
            _eyebrow("Subscription" if en else "Подписка")
            + _h(f"{name}, your subscription ends on {date}" if en else f"{name}, подписка заканчивается {date}")
            + _p("Renew before then and nothing stops: the days you have left are kept, and the new period "
                 "is added after them." if en else
                 "Продлите заранее, и ничего не прервётся: оставшиеся дни сохранятся, а новый период "
                 "добавится после них.")
            + _facts([("Active until" if en else "Действует до", f"{date}, {time}")])
            + _button(portal, "Renew" if en else "Продлить подписку")
            + _fallback_link(portal, lang)
            + _p("Subscriptions never renew on their own — this is the only reminder by email." if en else
                 "Подписка не продлевается сама — это единственное напоминание на почту.", dim=True, last=True)
        )
        text_lines = (f"Your Sovereign subscription ends on {date}, {time}. Renew: {portal}" if en else
                      f"Подписка Sovereign заканчивается {date} в {time}. Продлить: {portal}")
        pre = "Renew early — the days left are kept." if en else "Продлите заранее — оставшиеся дни сохранятся."
    elif kind == "sub_ended":
        subject = "Your subscription has ended — Sovereign" if en else "Подписка закончилась — Sovereign"
        inner = (
            _eyebrow("Subscription" if en else "Подписка")
            + _h("Your subscription has ended" if en else "Подписка закончилась")
            + _p(f"It was active until {date}. Your devices are switched off." if en else
                 f"Она действовала до {date}. Устройства отключены.")
            + _p("Renew whenever you like: a new device file appears in your account right after payment." if en else
                 "Продлить можно в любой момент: сразу после оплаты в личном кабинете появится новый файл устройства.")
            + _button(portal, "Choose a plan" if en else "Выбрать тариф")
            + _fallback_link(portal, lang)
            + _p("We will not write about this again." if en else "Больше писать об этом не будем.",
                 dim=True, last=True)
        )
        text_lines = (f"Your Sovereign subscription ended on {date}. Renew: {portal}" if en else
                      f"Подписка Sovereign закончилась {date}. Продлить: {portal}")
        pre = "A new device file appears right after payment." if en else "После оплаты сразу появится новый файл устройства."
    elif kind == "trial_ends_1d":
        subject = "Your trial ends tomorrow — Sovereign" if en else "Пробный период заканчивается — Sovereign"
        inner = (
            _eyebrow("Free trial" if en else "Пробный период")
            + _h(f"{name}, your trial ends {date} at {time}" if en else f"{name}, пробный период закончится {date} в {time}")
            + _p("To carry on without a break, choose a plan: paying issues a new device at full speed, "
                 "and the trial device is switched off." if en else
                 "Чтобы продолжить без перерыва, выберите тариф: при оплате выдаётся новое устройство "
                 "с полной скоростью, а пробное отключается.")
            + _button(portal, "Choose a plan" if en else "Выбрать тариф")
            + _fallback_link(portal, lang)
            + _p("Nothing is charged automatically." if en else "Ничего не списывается автоматически.",
                 dim=True, last=True)
        )
        text_lines = (f"Your Sovereign trial ends {date} at {time}. Choose a plan: {portal}" if en else
                      f"Пробный период Sovereign закончится {date} в {time}. Выбрать тариф: {portal}")
        pre = "Choose a plan to carry on without a break." if en else "Выберите тариф, чтобы продолжить без перерыва."
    else:
        raise ValueError(kind)
    reason = (f"You received this because you have an account at {host}." if en else
              f"Вы получили это письмо, потому что у вас есть аккаунт на {host}.")
    return subject, _wrap(inner, pre, lang, reason), text_lines


def password_reset_email(reset_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a password reset."""
    host = escape(SITE_URL.split("://", 1)[-1])
    if lang == "en":
        subject = "Reset your password — Sovereign"
        inner = (
            _eyebrow("Password")
            + _h("Set a new password")
            + _p("We received a request to reset the password for your account.")
            + _button(reset_url, "Set a new password")
            + _fallback_link(reset_url, lang)
            + _p("The link is valid for 1 hour and works once. If you did not ask for this, ignore the letter — "
                 "your password stays as it is.", dim=True, last=True)
        )
        reason = f"You received this because a password reset was requested for this address at {host}."
        text = (f"Reset your Sovereign password (valid 1 hour):\n{reset_url}\n\n"
                "If you did not ask for this, ignore this letter.")
        pre = "A link to set a new password."
    else:
        subject = "Сброс пароля — Sovereign"
        inner = (
            _eyebrow("Пароль")
            + _h("Задайте новый пароль")
            + _p("Мы получили запрос на сброс пароля от вашего аккаунта.")
            + _button(reset_url, "Задать новый пароль")
            + _fallback_link(reset_url, lang)
            + _p("Ссылка действует 1 час и срабатывает один раз. Если вы не запрашивали сброс — "
                 "проигнорируйте письмо, пароль останется прежним.", dim=True, last=True)
        )
        reason = f"Вы получили это письмо, потому что для этого адреса запросили сброс пароля на {host}."
        text = (f"Сброс пароля Sovereign (ссылка действует 1 час):\n{reset_url}\n\n"
                "Если вы не запрашивали сброс — проигнорируйте письмо.")
        pre = "Ссылка, чтобы задать новый пароль."
    return subject, _wrap(inner, pre, lang, reason), text


def support_ticket_email(category: str, details: dict, user_email: str) -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a support ticket (to support inbox)."""
    subject = f"[Support] {category}"
    rows = "".join(
        f'<p style="margin:0 0 8px"><b style="color:#7a9fb5">{escape(str(k))}:</b> {escape(str(v))}</p>'
        for k, v in details.items() if v
    )
    inner = f"""\
        <p style="margin:0 0 16px;font-size:20px;font-weight:600;color:#e8f4ff">New support request</p>
        <p style="margin:0 0 8px"><b style="color:#7a9fb5">Category:</b> {escape(category)}</p>
        {rows}
        <p style="margin:16px 0 0"><b style="color:#7a9fb5">From:</b> {escape(user_email)}</p>"""
    text = f"New support request. Category: {category}. From: {user_email}. Details: {details}"
    return subject, _wrap(inner, lang="en"), text
