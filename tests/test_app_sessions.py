"""
The Android app's long-lived sign-in: a refresh token traded for a new
day-long access token, so the app does not ask for the password every day.

What must hold: only a digest is stored; the token works until it is unused
for APP_SESSION_DAYS, and each use moves that ahead; a password reset, the
app's own sign-out and a disabled account end it; the site's sign-in gets
none; an admin never gets one.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import auth, password_reset  # noqa: E402
from auth.jwt import decode_token, hash_password  # noqa: E402
from db.models import AppSession, User  # noqa: E402
from services import app_sessions, ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_limits():
    for lim in ratelimit.ALL:
        lim.reset()
    yield
    for lim in ratelimit.ALL:
        lim.reset()


def _req(ip="198.51.100.7"):
    return SimpleNamespace(headers={"x-real-ip": ip}, client=None)


def _user(db, username="ivan", password="correct-horse", email="ivan@example.com"):
    u = User(id=str(uuid.uuid4()), username=username, email=email, password_hash=hash_password(password))
    db.add(u)
    db.run(db.commit())
    return u


def _login(db, username="ivan", password="correct-horse", refresh=True):
    return db.run(auth.login(auth.LoginRequest(username=username, password=password, refresh=refresh), _req(), db))


def _refresh(db, token):
    return db.run(auth.refresh(auth.RefreshRequest(refresh_token=token), _req(), db))


def _rows(db):
    return db.run(db.execute(select(AppSession))).scalars().all()


def test_the_app_gets_a_refresh_token_and_the_site_does_not(db):
    _user(db)
    assert _login(db, refresh=False).refresh_token is None
    assert _rows(db) == []
    r = _login(db)
    assert r.refresh_token and len(r.refresh_token) >= 40


def test_only_a_digest_is_stored(db):
    _user(db)
    token = _login(db).refresh_token
    [row] = _rows(db)
    assert row.token_hash == app_sessions.digest(token)
    assert token not in row.token_hash
    with pytest.raises(HTTPException) as e:
        _refresh(db, row.token_hash)  # what a database dump would give
    assert e.value.status_code == 401


def test_a_refresh_gives_a_new_access_token_for_the_same_account(db):
    _user(db, username="Ivan")
    token = _login(db, username="ivan").refresh_token
    r = _refresh(db, token)
    assert decode_token(r.access_token)["sub"] == "Ivan"
    assert decode_token(r.access_token)["role"] == "client"
    assert r.refresh_token is None
    # it does not rotate: the same token works again (a lost answer costs nothing)
    assert _refresh(db, token).access_token


def test_each_use_moves_the_expiry_ahead_and_an_unused_one_runs_out(db):
    _user(db)
    token = _login(db).refresh_token
    [row] = _rows(db)
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.run(db.commit())
    _refresh(db, token)
    db.run(db.refresh(row))
    left = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    assert left - datetime.now(timezone.utc) > timedelta(days=app_sessions.APP_SESSION_DAYS - 1)

    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        _refresh(db, token)
    assert e.value.status_code == 401


def test_a_password_reset_ends_every_app_session_of_the_account(db, monkeypatch):
    u = _user(db)
    other = _user(db, username="petr", email="petr@example.com")
    t1, t2 = _login(db).refresh_token, _login(db).refresh_token
    kept = _login(db, username="petr").refresh_token

    urls = []
    real = password_reset.password_reset_email
    monkeypatch.setattr(password_reset, "password_reset_email", lambda url, lang="ru": (urls.append(url), real(url, lang))[1])
    db.run(password_reset.forgot_password(password_reset.ForgotRequest(email=u.email), _req(), db))
    db.run(password_reset.reset_password(
        password_reset.ResetRequest(token=urls[0].split("token=", 1)[1], new_password="brand-new-pass"), _req(), db))

    for t in (t1, t2):
        with pytest.raises(HTTPException):
            _refresh(db, t)
    assert _refresh(db, kept).access_token
    assert other.id in {r.user_id for r in _rows(db)}


def test_signing_out_of_the_app_ends_only_its_own_session(db):
    _user(db)
    phone, tablet = _login(db).refresh_token, _login(db).refresh_token
    db.run(auth.logout(auth.RefreshRequest(refresh_token=phone), db))
    with pytest.raises(HTTPException):
        _refresh(db, phone)
    assert _refresh(db, tablet).access_token
    # an unknown token signs nothing out and says nothing about it
    assert db.run(auth.logout(auth.RefreshRequest(refresh_token="nonsense"), db)) == {"ok": True}


def test_a_disabled_account_cannot_refresh(db):
    u = _user(db)
    token = _login(db).refresh_token
    u.is_active = False
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        _refresh(db, token)
    assert e.value.status_code == 401


def test_an_admin_never_gets_a_refresh_token(db):
    r = _login(db, username=auth.ADMIN_USERNAME, password="test-admin-password")
    assert r.role == "admin" and r.refresh_token is None


def test_sessions_per_account_are_capped(db):
    _user(db)
    tokens = [_login(db).refresh_token for _ in range(app_sessions.MAX_SESSIONS_PER_USER + 3)]
    assert len(_rows(db)) == app_sessions.MAX_SESSIONS_PER_USER
    assert _refresh(db, tokens[-1]).access_token


def test_refreshing_is_rate_limited_per_address(db):
    _user(db)
    token = _login(db).refresh_token
    for _ in range(ratelimit.LOGIN_PER_IP.limit - 1):  # the sign-in above took one
        _refresh(db, token)
    with pytest.raises(HTTPException) as e:
        _refresh(db, token)
    assert e.value.status_code == 429
