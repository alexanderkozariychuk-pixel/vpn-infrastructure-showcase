"""
Email confirmation, and the letters around an account.

A purchase needs a confirmed address: the receipt, the reset link and every
notice go there. Registration sends one letter that is both the welcome and
the confirmation; a payment sends one receipt, once.
"""

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import email_verify, password_reset, payment, register  # noqa: E402
from config import plan_info  # noqa: E402
from db.models import Config, Payment, User  # noqa: E402
from services import mailer, provisioner, ratelimit  # noqa: E402
from services.provisioner import activate_payment  # noqa: E402

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def _fresh_limits():
    for lim in ratelimit.ALL:
        lim.reset()
    yield
    for lim in ratelimit.ALL:
        lim.reset()


@pytest.fixture
def outbox(monkeypatch):
    """Every letter the code tried to send, as (to, subject, html, text)."""
    sent = []

    async def fake_send(to, subject, html, text=""):
        sent.append((to, subject, html, text))
        return True

    monkeypatch.setattr(mailer, "send_email", fake_send)
    # Modules that imported the name directly hold their own reference.
    for mod in (register, email_verify, password_reset):
        monkeypatch.setattr(mod, "send_email", fake_send)
    return sent


def _req(ip="198.51.100.7"):
    return SimpleNamespace(headers={"x-real-ip": ip}, client=None)


def _token_in(letter) -> str:
    m = re.search(r"/verify\?token=([A-Za-z0-9_-]+)", letter[3])
    assert m, "no confirmation link in the letter"
    return m.group(1)


def _register(db, username="ivan_1", email="ivan@example.com", lang="ru"):
    req = register.RegisterRequest(username=username, email=email,
                                   password="long-enough", lang=lang)
    db.run(register.register(req, _req(), db))
    return db.run(db.execute(select(User).where(User.username == username))).scalar_one()


def _verify(db, token):
    return db.run(email_verify.verify_email(email_verify.VerifyRequest(token=token), _req(), db))


# ── registration sends one letter with a working link ────────────────────

def test_registration_sends_one_letter_that_welcomes_and_confirms(db, outbox):
    user = _register(db)
    assert len(outbox) == 1
    to, subject, html, text = outbox[0]
    assert to == "ivan@example.com"
    assert "ivan_1" in html
    assert "/verify?token=" in html and "/verify?token=" in text
    assert user.email_verified_at is None


def test_the_link_from_the_letter_confirms_the_address(db, outbox):
    user = _register(db)
    assert _verify(db, _token_in(outbox[0]))["ok"] is True
    db.run(db.refresh(user))
    assert user.email_verified_at is not None


def test_the_database_holds_only_a_digest_of_the_token(db, outbox):
    user = _register(db)
    token = _token_in(outbox[0])
    assert user.email_verify_token and user.email_verify_token != token
    with pytest.raises(HTTPException) as e:
        _verify(db, user.email_verify_token)
    assert e.value.status_code == 400


def test_a_link_works_once(db, outbox):
    _register(db)
    token = _token_in(outbox[0])
    _verify(db, token)
    with pytest.raises(HTTPException) as e:
        _verify(db, token)
    assert e.value.status_code == 400


def test_an_expired_link_does_not_confirm(db, outbox):
    user = _register(db)
    user.email_verify_expires = NOW - timedelta(minutes=1)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        _verify(db, _token_in(outbox[0]))
    assert e.value.status_code == 400
    db.run(db.refresh(user))
    assert user.email_verified_at is None


def test_the_letter_is_in_the_language_the_account_was_made_in(db, outbox):
    user = _register(db, lang="en")
    assert user.lang == "en"
    assert outbox[0][1].startswith("Confirm your email")


def test_an_unknown_language_falls_back_to_russian(db, outbox):
    assert _register(db, lang="xx").lang == "ru"


# ── asking for the letter again ──────────────────────────────────────────

def _resend(db, user, ip="198.51.100.7"):
    return db.run(email_verify.resend_verification(_req(ip), db, {"sub": user.username}))


def test_a_new_letter_replaces_the_old_link(db, outbox):
    user = _register(db)
    old = _token_in(outbox[0])
    _resend(db, user)
    new = _token_in(outbox[1])
    assert new != old
    with pytest.raises(HTTPException):
        _verify(db, old)
    assert _verify(db, new)["ok"] is True


def test_new_letters_are_limited_per_account_across_addresses(db, outbox):
    user = _register(db)
    for i in range(ratelimit.VERIFY_RESEND.limit):
        _resend(db, user, ip=f"203.0.113.{i + 1}")
    with pytest.raises(HTTPException) as e:
        _resend(db, user, ip="203.0.113.200")
    assert e.value.status_code == 429
    assert len(outbox) == 1 + ratelimit.VERIFY_RESEND.limit


def test_a_confirmed_account_gets_no_new_letter(db, outbox):
    user = _register(db)
    _verify(db, _token_in(outbox[0]))
    assert _resend(db, user)["already_verified"] is True
    assert len(outbox) == 1


# ── what confirmation unlocks ────────────────────────────────────────────

def _order(db, user):
    req = payment.CreatePaymentRequest(plan="basic-1m")
    return db.run(payment._open_order(db, user, req))


def test_an_unconfirmed_account_cannot_open_an_order(db, outbox):
    user = _register(db)
    with pytest.raises(HTTPException) as e:
        _order(db, user)
    assert e.value.status_code == 403
    assert e.value.detail == "email_not_verified"
    # and the refusal leaves no pending order behind
    assert db.run(db.execute(select(Payment))).scalars().all() == []


def test_a_confirmed_account_can(db, outbox):
    user = _register(db)
    _verify(db, _token_in(outbox[0]))
    db.run(db.refresh(user))
    pay, quote = _order(db, user)
    assert pay.status == "pending" and quote["amount"] == 350


def test_the_profile_says_whether_the_address_is_confirmed(db, outbox):
    user = _register(db)
    assert db.run(register.get_me(db, {"sub": user.username}))["email_verified"] is False
    _verify(db, _token_in(outbox[0]))
    assert db.run(register.get_me(db, {"sub": user.username}))["email_verified"] is True


def test_a_completed_password_reset_confirms_the_address(db, outbox, monkeypatch):
    user = _register(db)
    links = []
    real = password_reset.password_reset_email
    monkeypatch.setattr(password_reset, "password_reset_email",
                        lambda url, lang="ru": (links.append(url), real(url, lang))[1])
    db.run(password_reset.forgot_password(
        password_reset.ForgotRequest(email="ivan@example.com"), _req(), db))
    token = links[0].split("token=", 1)[1]
    db.run(password_reset.reset_password(
        password_reset.ResetRequest(token=token, new_password="brand-new-pass"), _req(), db))
    db.run(db.refresh(user))
    assert user.email_verified_at is not None


# ── the receipt ──────────────────────────────────────────────────────────

@pytest.fixture
def issued(monkeypatch):
    async def fake(user, db, name="device"):
        c = Config(id=str(uuid.uuid4()), user_id=user.id, name=name, peer_ip="10.88.88.77",
                   private_key="enc", public_key="PUBX", preshared_key="enc", is_active=True)
        db.add(c)
        return c
    monkeypatch.setattr(provisioner, "issue_config", fake)


def _paying(db, plan="basic-3m", with_config=False, lang="ru"):
    u = User(id=str(uuid.uuid4()), username="payer", email="payer@example.com",
             password_hash="x", email_verified_at=NOW, lang=lang)
    p = Payment(id=str(uuid.uuid4()), user_id=u.id, plan=plan,
                amount=int(plan_info(plan)["amount"]), currency="RUB", status="pending")
    db.add(u)
    db.add(p)
    if with_config:
        db.add(Config(id=str(uuid.uuid4()), user_id=u.id, name="device-1", peer_ip="10.88.88.42",
                      private_key="enc", public_key="PUBOLD", preshared_key="enc", is_active=True))
    db.run(db.commit())
    return u, p


def test_activation_sends_one_receipt_with_the_plan_and_the_end_date(db, outbox, issued):
    user, pay = _paying(db, "basic-3m")
    assert db.run(activate_payment(user, pay, db)) is True
    db.run(mailer.drain())
    receipts = [m for m in outbox if "Оплата получена" in m[1]]
    assert len(receipts) == 1
    to, _, html, text = receipts[0]
    assert to == "payer@example.com"
    assert "Базовый, 3 месяца" in html
    assert "900 ₽" in html
    until = user.subscribed_until.astimezone(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")
    assert until in html and until in text
    assert "Первое устройство уже создано" in html


def test_a_renewal_receipt_says_the_remaining_days_are_kept(db, outbox, issued):
    user, pay = _paying(db, "ext-1m", with_config=True)
    db.run(activate_payment(user, pay, db))
    db.run(mailer.drain())
    html = [m for m in outbox if "Оплата получена" in m[1]][0][2]
    assert "Оставшиеся дни сохранены" in html
    assert "Расширенный, 1 месяц" in html


def test_the_receipt_is_in_the_accounts_language(db, outbox, issued):
    user, pay = _paying(db, lang="en")
    db.run(activate_payment(user, pay, db))
    db.run(mailer.drain())
    assert any(m[1].startswith("Payment received") for m in outbox)


def test_a_failed_activation_sends_no_receipt(db, outbox, monkeypatch):
    async def none(user, db, name="device"):
        return None
    monkeypatch.setattr(provisioner, "issue_config", none)
    user, pay = _paying(db)
    assert db.run(activate_payment(user, pay, db)) is False
    db.run(mailer.drain())
    assert outbox == []


def test_a_mail_failure_does_not_undo_the_activation(db, issued, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("template broke")
    monkeypatch.setattr(mailer, "payment_email", boom)
    user, pay = _paying(db)
    assert db.run(activate_payment(user, pay, db)) is True
    assert pay.status == "paid"


# ── the letters themselves ───────────────────────────────────────────────

def test_every_letter_escapes_what_it_is_given():
    for _, html, _ in (
        mailer.welcome_email("<i>x</i>", 'https://e.com/verify?token=a"b'),
        mailer.verification_email('https://e.com/verify?token=a"b'),
        mailer.password_reset_email('https://e.com/reset?token=a"b'),
        mailer.payment_email("<i>x</i>", "basic", 30, 350, "RUB", NOW, first=True),
    ):
        assert "<i>x</i>" not in html
        assert 'token=a"b' not in html


def test_every_letter_has_a_plain_text_part():
    for subject, html, text in (
        mailer.welcome_email("ivan", "https://e.com/verify?token=t"),
        mailer.verification_email("https://e.com/verify?token=t"),
        mailer.password_reset_email("https://e.com/reset?token=t"),
        mailer.payment_email("ivan", "ext", 180, 3200, "RUB", NOW, first=False),
    ):
        assert subject and text.strip() and "<" not in text
