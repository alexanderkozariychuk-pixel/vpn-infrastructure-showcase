"""
The rules every letter to a customer follows (docs/email-style.md).

One action per letter, said where it leads; a preheader; the button's address
spelled out; a plain-text part that carries the same link; a footer that says
why the letter came. Checked on every letter, in both languages, so a new
letter built from the same components cannot quietly skip one.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest

from services import mailer

NOW = datetime.now(timezone.utc)
VERIFY = "https://sov3r3ign.com/verify?token=abc"
RESET = "https://sov3r3ign.com/reset?token=def"


def _letters(lang):
    return {
        "welcome": (mailer.welcome_email("ivan_1", VERIFY, lang), VERIFY),
        "verification": (mailer.verification_email(VERIFY, lang), VERIFY),
        "receipt": (mailer.payment_email("ivan_1", "basic", 30, 350, "RUB", NOW + timedelta(days=30), True, lang),
                    f"{mailer.SITE_URL}/app"),
        "reset": (mailer.password_reset_email(RESET, lang), RESET),
        **{kind: (mailer.reminder_email(kind, "ivan_1", NOW + timedelta(days=2), lang), f"{mailer.SITE_URL}/app")
           for kind in ("sub_ends_3d", "sub_ended", "trial_ends_1d")},
    }


CASES = [(lang, name) for lang in ("ru", "en") for name in _letters("ru")]


def _get(lang, name):
    (subject, html, text), target = _letters(lang)[name]
    return subject, html, text, target


@pytest.mark.parametrize("lang,name", CASES)
def test_one_primary_button_and_it_goes_where_the_letter_says(lang, name):
    _, html, _, target = _get(lang, name)
    buttons = re.findall(r'<td bgcolor="#00d4ff" style="border-radius:8px[^>]*>\s*<a href="([^"]+)"', html)
    assert buttons == [target.replace("&", "&amp;")]


@pytest.mark.parametrize("lang,name", CASES)
def test_the_subject_names_the_service(lang, name):
    subject, *_ = _get(lang, name)
    assert subject.endswith("— Sovereign")


@pytest.mark.parametrize("lang,name", CASES)
def test_a_preheader_and_a_reason_line(lang, name):
    _, html, _, _ = _get(lang, name)
    assert "display:none;max-height:0" in html
    reason = "You received this" if lang == "en" else "Вы получили это письмо"
    assert reason in html


@pytest.mark.parametrize("lang,name", CASES)
def test_the_plain_text_part_carries_the_link(lang, name):
    _, _, text, target = _get(lang, name)
    assert target in text and "<" not in text


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("name", ["welcome", "verification", "reset"])
def test_links_that_carry_a_token_are_also_spelled_out(lang, name):
    _, html, _, target = _get(lang, name)
    assert html.count(target) >= 2   # the button, and the address under it


def test_the_welcome_letter_offers_the_trial_only_while_it_is_on(monkeypatch):
    monkeypatch.setenv("TRIAL_ENABLED", "1")
    _, html, text = mailer.welcome_email("ivan_1", VERIFY)
    assert "пробный период" in html and "пробный период" in text
    monkeypatch.setenv("TRIAL_ENABLED", "0")
    _, html, text = mailer.welcome_email("ivan_1", VERIFY)
    assert "пробный период" not in html and "пробный период" not in text


@pytest.mark.parametrize("n,word", [(1, "1 день"), (3, "3 дня"), (5, "5 дней"), (11, "11 дней"), (21, "21 день")])
def test_days_are_declined(n, word):
    assert mailer._days_ru(n) == word


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_a_username_in_a_reminder_is_escaped(lang):
    _, html, _ = mailer.reminder_email("sub_ends_3d", "<b>x</b>", NOW, lang)
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_reminders_are_only_for_the_ends_that_cost_a_connection():
    with pytest.raises(ValueError):
        mailer.reminder_email("sub_ends_1d", "ivan_1", NOW)
