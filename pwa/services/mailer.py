"""
services/mailer.py — transactional email via Resend HTTP API.

Outbound SMTP (587/465) is blocked at the hosting network level (confirmed
2026-08-05), so this sends over HTTPS instead. Reads:
  RESEND_API_KEY, MAIL_FROM

All sends are best-effort: failures are logged, never raised into the
request path, so a mail outage can't break registration/payment/etc.
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
MAIL_FROM = os.getenv("MAIL_FROM", "Sovereign <support@sov3r3ign.com>")
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


# ── Email templates (RU / EN) ────────────────────────────────────────

def _wrap(inner_html: str) -> str:
    """Shared dark-themed wrapper matching the portal aesthetic."""
    return f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#080c0f;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px">
    <div style="text-align:center;margin-bottom:32px">
      <span style="font-size:22px;font-weight:600;color:#00d4ff;letter-spacing:1px">SOVEREIGN</span>
    </div>
    <div style="background:#0d1318;border:1px solid #1e2d38;border-radius:10px;padding:32px;color:#d8eaf6;line-height:1.7">
      {inner_html}
    </div>
    <div style="text-align:center;margin-top:24px;color:#5a7a8a;font-size:12px">
      support@sov3r3ign.com
    </div>
  </div>
</body>
</html>"""


def welcome_email(username: str, lang: str = "ru") -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a registration welcome."""
    if lang == "en":
        subject = "Welcome to Sovereign"
        inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">Welcome, {username}</p>
        <p style="margin:0 0 16px">Your Sovereign account has been created successfully.</p>
        <p style="margin:0 0 16px">You can now sign in to the portal, choose a plan, and get your personal connection config.</p>
        <p style="margin:0;color:#7a9fb5;font-size:13px">If you didn't create this account, you can safely ignore this message.</p>"""
        text = f"Welcome to Sovereign, {username}. Your account has been created. Sign in to the portal to get started."
    else:
        subject = "Добро пожаловать в Sovereign"
        inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">Здравствуйте, {username}</p>
        <p style="margin:0 0 16px">Ваш аккаунт Sovereign успешно создан.</p>
        <p style="margin:0 0 16px">Теперь вы можете войти в портал, выбрать тариф и получить персональный конфиг для подключения.</p>
        <p style="margin:0;color:#7a9fb5;font-size:13px">Если вы не создавали этот аккаунт, просто проигнорируйте это письмо.</p>"""
        text = f"Добро пожаловать в Sovereign, {username}. Ваш аккаунт создан. Войдите в портал чтобы начать."
    return subject, _wrap(inner), text


def password_reset_email(reset_url: str, lang: str = "ru") -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a password reset."""
    if lang == "en":
        subject = "Reset your Sovereign password"
        inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">Password reset</p>
        <p style="margin:0 0 16px">We received a request to reset your password. Click the button below to set a new one. This link expires in 1 hour.</p>
        <p style="margin:24px 0"><a href="{reset_url}" style="background:#00d4ff;color:#080c0f;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:600">Reset password</a></p>
        <p style="margin:0;color:#7a9fb5;font-size:13px">If you didn't request this, you can safely ignore this message — your password won't change.</p>"""
        text = f"Reset your Sovereign password: {reset_url} (expires in 1 hour). If you didn't request this, ignore this email."
    else:
        subject = "Сброс пароля Sovereign"
        inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">Сброс пароля</p>
        <p style="margin:0 0 16px">Мы получили запрос на сброс пароля. Нажмите кнопку ниже чтобы задать новый. Ссылка действительна 1 час.</p>
        <p style="margin:24px 0"><a href="{reset_url}" style="background:#00d4ff;color:#080c0f;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:600">Сбросить пароль</a></p>
        <p style="margin:0;color:#7a9fb5;font-size:13px">Если вы не запрашивали сброс, проигнорируйте это письмо — пароль не изменится.</p>"""
        text = f"Сброс пароля Sovereign: {reset_url} (действует 1 час). Если вы не запрашивали — проигнорируйте."
    return subject, _wrap(inner), text


def support_ticket_email(category: str, details: dict, user_email: str) -> tuple[str, str, str]:
    """Returns (subject, body_html, body_text) for a support ticket (to support inbox)."""
    subject = f"[Support] {category}"
    rows = "".join(
        f'<p style="margin:0 0 8px"><b style="color:#7a9fb5">{k}:</b> {v}</p>'
        for k, v in details.items() if v
    )
    inner = f"""\
        <p style="margin:0 0 16px;font-size:18px;color:#e8f4ff">New support request</p>
        <p style="margin:0 0 8px"><b style="color:#7a9fb5">Category:</b> {category}</p>
        {rows}
        <p style="margin:16px 0 0"><b style="color:#7a9fb5">From:</b> {user_email}</p>"""
    text = f"New support request. Category: {category}. From: {user_email}. Details: {details}"
    return subject, _wrap(inner), text
