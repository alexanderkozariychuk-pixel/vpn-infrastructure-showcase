"""
Accounts: what a stranger can make the portal do, and how often.

Before this, registration accepted any username and any address and mailed a
welcome letter with the username pasted into its HTML; login, registration,
password reset and the support form had no limits; and reset tokens sat in the
database in the clear. Each of those is pinned here.
"""

import os
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import auth, password_reset, register, support  # noqa: E402
from auth.jwt import decode_token, hash_password  # noqa: E402
from db.models import User  # noqa: E402
from services import mailer, ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_limits():
    for lim in ratelimit.ALL:
        lim.reset()
    yield
    for lim in ratelimit.ALL:
        lim.reset()


def _req(ip="198.51.100.7"):
    """What the routes read from a request: the address nginx put in X-Real-IP."""
    return SimpleNamespace(headers={"x-real-ip": ip}, client=None)


def _status(exc_info):
    return exc_info.value.status_code


def _user(db, username="ivan", email=None, password="correct-horse"):
    u = User(id=str(uuid.uuid4()), username=username,
             email=email or f"{uuid.uuid4().hex[:6]}@example.com",
             password_hash=hash_password(password))
    db.add(u)
    db.run(db.commit())
    return u


def _reg(username="ivan_1", email=None, password="long-enough"):
    return register.RegisterRequest(username=username,
                                    email=email or f"{uuid.uuid4().hex[:6]}@example.com",
                                    password=password)


# ── what registration accepts ─────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "ivan.petrov",        # a dot: the node's peer-name rule has none
    "иван",               # Cyrillic
    "ab",                 # too short
    "a" * 28,             # auto-<28> is 33, over the wrapper's 32
    "<b>x</b>",           # markup
    "ivan petrov",        # a space
])
def test_a_username_the_node_would_refuse_is_refused_at_registration(name):
    with pytest.raises(ValidationError):
        _reg(username=name)


def test_the_longest_accepted_username_still_fits_the_peer_name():
    r = _reg(username="a" * 27)
    assert len(f"auto-{r.username}") == 32


@pytest.mark.parametrize("name", ["admin", "Admin", "ROOT", "support"])
def test_names_that_read_as_the_operator_are_reserved(name):
    with pytest.raises(ValidationError):
        _reg(username=name)


def test_a_short_password_is_refused_by_the_server_not_only_the_page():
    with pytest.raises(ValidationError):
        _reg(password="1234567")


def test_the_email_is_stored_in_lower_case(db):
    r = _reg(email="Ivan.Petrov@Example.COM")
    db.run(register.register(r, _req(), db))
    stored = db.run(db.execute(select(User.email))).scalar_one()
    assert stored == "ivan.petrov@example.com"


def test_one_mailbox_is_one_account_whatever_the_case(db):
    db.run(register.register(_reg(username="first", email="ivan@example.com"), _req(), db))
    with pytest.raises(HTTPException) as e:
        db.run(register.register(_reg(username="second", email="IVAN@EXAMPLE.com"), _req(), db))
    assert _status(e) == 409


def test_usernames_differing_only_in_case_are_one_name(db):
    db.run(register.register(_reg(username="Ivan"), _req(), db))
    with pytest.raises(HTTPException) as e:
        db.run(register.register(_reg(username="ivan"), _req(), db))
    assert _status(e) == 409


def test_registration_is_limited_per_address(db):
    for i in range(ratelimit.REGISTER_PER_IP.limit):
        db.run(register.register(_reg(username=f"user_{i}"), _req("203.0.113.1"), db))
    with pytest.raises(HTTPException) as e:
        db.run(register.register(_reg(username="one_more"), _req("203.0.113.1"), db))
    assert _status(e) == 429
    assert int(e.value.headers["Retry-After"]) > 0
    # another address is not affected
    db.run(register.register(_reg(username="elsewhere"), _req("203.0.113.2"), db))


# ── login ─────────────────────────────────────────────────────────────────

def _login(db, username, password, ip="198.51.100.7"):
    return db.run(auth.login(auth.LoginRequest(username=username, password=password), _req(ip), db))


def test_failed_logins_for_one_name_from_one_address_are_cut_off(db):
    _user(db)
    for _ in range(ratelimit.LOGIN_FAILS.limit):
        with pytest.raises(HTTPException) as e:
            _login(db, "ivan", "wrong")
        assert _status(e) == 401
    # the right password no longer helps from here...
    with pytest.raises(HTTPException) as e:
        _login(db, "ivan", "correct-horse")
    assert _status(e) == 429
    # ...but the owner on another network is not locked out
    assert _login(db, "ivan", "correct-horse", ip="198.51.100.99").access_token


def test_a_successful_login_does_not_count_as_a_failure(db):
    _user(db)
    for _ in range(ratelimit.LOGIN_FAILS.limit + 2):
        assert _login(db, "ivan", "correct-horse").access_token


def test_every_login_from_one_address_counts_toward_a_ceiling(db):
    _user(db)
    for _ in range(ratelimit.LOGIN_PER_IP.limit):
        _login(db, "ivan", "correct-horse")
    with pytest.raises(HTTPException) as e:
        _login(db, "ivan", "correct-horse")
    assert _status(e) == 429


def test_admin_guesses_are_limited_too(db):
    for _ in range(ratelimit.LOGIN_FAILS.limit):
        with pytest.raises(HTTPException):
            _login(db, auth.ADMIN_USERNAME, "guess")
    with pytest.raises(HTTPException) as e:
        _login(db, auth.ADMIN_USERNAME, "test-admin-password")
    assert _status(e) == 429


def test_login_ignores_case_and_the_token_carries_the_stored_name(db):
    _user(db, username="Ivan")
    tok = _login(db, "IVAN", "correct-horse").access_token
    assert decode_token(tok)["sub"] == "Ivan"


# ── password reset ────────────────────────────────────────────────────────

@pytest.fixture
def sent(monkeypatch):
    """Reset links as they would have been mailed."""
    urls = []
    real = password_reset.password_reset_email

    def capture(url, lang="ru"):
        urls.append(url)
        return real(url, lang)

    monkeypatch.setattr(password_reset, "password_reset_email", capture)
    return urls


def _forgot(db, email, ip="198.51.100.7"):
    return db.run(password_reset.forgot_password(
        password_reset.ForgotRequest(email=email), _req(ip), db))


def _reset(db, token, password="brand-new-pass", ip="198.51.100.7"):
    return db.run(password_reset.reset_password(
        password_reset.ResetRequest(token=token, new_password=password), _req(ip), db))


def test_the_database_holds_a_digest_that_cannot_be_used_as_the_token(db, sent):
    u = _user(db, email="ivan@example.com")
    _forgot(db, "ivan@example.com")
    token = sent[0].split("token=", 1)[1]
    db.run(db.refresh(u))
    assert u.reset_token and u.reset_token != token
    # what a leaked dump would give someone does not open the door
    with pytest.raises(HTTPException) as e:
        _reset(db, u.reset_token)
    assert _status(e) == 400
    # the link itself does
    assert _reset(db, token)["ok"] is True


def test_reset_finds_the_account_whatever_case_the_address_is_typed_in(db, sent):
    _user(db, email="ivan@example.com")
    _forgot(db, "IVAN@EXAMPLE.COM")
    assert len(sent) == 1


def test_one_mailbox_cannot_be_flooded_with_reset_letters(db, sent):
    _user(db, email="ivan@example.com")
    for i in range(ratelimit.FORGOT_PER_EMAIL.limit):
        _forgot(db, "ivan@example.com", ip=f"198.51.100.{i + 1}")
    with pytest.raises(HTTPException) as e:
        _forgot(db, "ivan@example.com", ip="198.51.100.200")
    assert _status(e) == 429
    assert len(sent) == ratelimit.FORGOT_PER_EMAIL.limit


def test_the_reset_limit_does_not_reveal_whether_an_address_is_registered(db, sent):
    for _ in range(ratelimit.FORGOT_PER_EMAIL.limit):
        _forgot(db, "nobody@example.com")
    with pytest.raises(HTTPException) as e:
        _forgot(db, "nobody@example.com")
    assert _status(e) == 429
    assert sent == []


# ── letters ───────────────────────────────────────────────────────────────

def test_a_username_cannot_put_markup_into_a_letter():
    _, html, _ = mailer.welcome_email('<a href="https://evil.test">pay</a>')
    assert '<a href="https://evil.test">' not in html
    assert "&lt;a href=" in html


def test_a_support_ticket_cannot_put_markup_into_our_inbox():
    _, html, _ = mailer.support_ticket_email(
        "<img src=x>", {"Description": "<script>alert(1)</script>"}, "a@example.com")
    assert "<script>" not in html and "<img src=x>" not in html


def test_the_support_form_is_limited_per_address():
    t = support.SupportTicket(issue_type="other", details="help", email="a@example.com")
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        for _ in range(ratelimit.SUPPORT_PER_IP.limit):
            loop.run_until_complete(support.submit_ticket(t, _req()))
        with pytest.raises(HTTPException) as e:
            loop.run_until_complete(support.submit_ticket(t, _req()))
    finally:
        loop.close()
    assert _status(e) == 429


def test_a_support_description_has_a_size_limit():
    with pytest.raises(ValidationError):
        support.SupportTicket(issue_type="other", details="x" * 4001, email="a@example.com")


# ── the limiter itself ────────────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_the_window_slides_rather_than_resetting_on_a_boundary():
    c = _Clock()
    lim = ratelimit.Limiter(limit=2, window=60, clock=c)
    lim.add("k")
    c.t += 30
    lim.add("k")
    assert lim.retry_after("k") is not None
    c.t += 31            # the first event has left the window, the second has not
    assert lim.retry_after("k") is None
    lim.add("k")
    assert lim.retry_after("k") is not None


def test_keys_whose_window_has_emptied_are_forgotten():
    c = _Clock()
    lim = ratelimit.Limiter(limit=5, window=10, clock=c)
    for i in range(50):
        lim.add(f"one-off-{i}")
    c.t += 11
    lim._since_sweep = lim._SWEEP_EVERY - 1
    lim.add("fresh")
    assert set(lim._events) == {"fresh"}
