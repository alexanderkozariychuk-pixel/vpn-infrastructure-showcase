#!/usr/bin/env python3
"""
Render every letter the portal sends into a folder, to look at before a
deploy:

    python3 tools/preview_emails.py            # -> /tmp/sovrn-letters/index.html
    python3 tools/preview_emails.py out/dir

Each letter in both languages, with the trial offer on and off where it
changes the letter. The mark in the header points at the live site; here it
is pointed at the file in the repository so the preview works offline.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pwa"))
os.environ.setdefault("JWT_SECRET", "preview")

from services import mailer  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sovrn-letters")
out.mkdir(parents=True, exist_ok=True)
icon = (ROOT / "pwa" / "static" / "icons" / "icon-192.png").as_uri()
now = datetime.now(timezone.utc)
verify = f"{mailer.SITE_URL}/verify?token=example-verify-token"
reset = f"{mailer.SITE_URL}/reset?token=example-reset-token"


def letters(lang):
    for trial in ("1", "0"):
        os.environ["TRIAL_ENABLED"] = trial
        yield f"welcome-trial{'on' if trial == '1' else 'off'}", mailer.welcome_email("ivan_1", verify, lang)
    yield "verification", mailer.verification_email(verify, lang)
    yield "receipt-first", mailer.payment_email("ivan_1", "basic", 90, 900, "RUB", now + timedelta(days=90), True, lang)
    yield "receipt-renewal", mailer.payment_email("ivan_1", "ext", 180, 3200, "RUB", now + timedelta(days=200), False, lang)
    yield "reset", mailer.password_reset_email(reset, lang)


rows = []
for lang in ("ru", "en"):
    for name, (subject, html, text) in letters(lang):
        fname = f"{name}-{lang}.html"
        (out / fname).write_text(html.replace(f"{mailer.SITE_URL}/static/icons/icon-192.png", icon), encoding="utf-8")
        (out / f"{name}-{lang}.txt").write_text(f"Subject: {subject}\n\n{text}\n", encoding="utf-8")
        rows.append(f'<li><a href="{fname}">{escape(subject)}</a> <small>{fname}</small></li>')

(out / "index.html").write_text(
    "<!doctype html><meta charset=utf-8><title>Sovereign letters</title>"
    "<body style='font:15px system-ui;background:#080c0f;color:#d8eaf6;padding:24px'>"
    "<h1 style='font-weight:500'>Letters</h1><ul style='line-height:2'>" + "".join(rows) +
    "</ul><style>a{color:#00d4ff}small{color:#7a9fb5;margin-left:8px}</style>", encoding="utf-8")
print(out / "index.html")
