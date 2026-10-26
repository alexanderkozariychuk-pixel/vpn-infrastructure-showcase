"""
The referral programme is shown where customers are, not one tab deep in
Payment: its own menu item, a strip on the config page, a line in the
receipt and in the renewal reminder.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import credit, mailer, notify  # noqa: E402

INDEX = Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html"


def test_the_menu_has_an_invite_page():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data-page="invite"' in html
    assert 'id="client-page-invite"' in html
    assert "paytab-referral" not in html, "the old tab inside Payment is still there"


def test_the_config_page_carries_the_strip_and_it_can_be_closed():
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="ref-strip"' in html and "function dismissRefStrip(" in html
    assert "refreshRefStrip(paid)" in html, "the strip is not tied to a paid subscription"


def test_letters_link_to_the_invite_page():
    html = INDEX.read_text(encoding="utf-8")
    assert "function openDeepLink(" in html and "'invite'" in html
    until = datetime.now(timezone.utc) + timedelta(days=30)
    for lang in ("ru", "en"):
        _, body, text = mailer.payment_email("a", "basic", 30, 350, "RUB", until, False, lang)
        assert "/app#invite" in body and "/app#invite" in text
        assert f"+{credit.REFERRAL_REWARD_DAYS}" in body
        _, body, text = mailer.reminder_email("sub_ends_3d", "a", until, lang)
        assert "/app#invite" in body and "/app#invite" in text


def test_the_bell_mentions_it_after_payment_and_before_the_end():
    for kind in ("paid", "sub_ends_3d"):
        for lang in ("ru", "en"):
            assert "+30" in notify.TEXTS[kind][lang][1], (kind, lang)
    assert notify.LINKS["referral_bonus"] == "invite"
