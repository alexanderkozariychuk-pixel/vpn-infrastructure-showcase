"""
"Remember me" on the site: a refresh token on request, swapped for a new
day's token, closed on sign-out — and the page's side wired the same way.
"""
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import auth  # noqa: E402
from auth.jwt import hash_password  # noqa: E402
from db.models import User  # noqa: E402
from services import ratelimit  # noqa: E402

PAGE = (Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _limits():
    for lim in ratelimit.ALL:
        lim.reset()


def _req():
    return SimpleNamespace(headers={"x-real-ip": "198.51.100.9"}, client=None)


def _user(db):
    u = User(id=str(uuid.uuid4()), username="rem_1", email="r@x.test", password_hash=hash_password("secret-pass"))
    db.add(u)
    db.run(db.commit())
    return u


def _login(db, remember):
    return db.run(auth.login(auth.LoginRequest(username="rem_1", password="secret-pass", refresh=remember), _req(), db))


def test_without_the_box_no_long_session(db):
    _user(db)
    assert _login(db, False).refresh_token is None


def test_with_it_the_refresh_token_brings_a_new_day(db):
    _user(db)
    rt = _login(db, True).refresh_token
    assert rt
    again = db.run(auth.refresh(auth.RefreshRequest(refresh_token=rt), _req(), db))
    assert again.access_token


def test_sign_out_ends_it_on_the_server(db):
    _user(db)
    rt = _login(db, True).refresh_token
    db.run(auth.logout(auth.RefreshRequest(refresh_token=rt), db))
    with pytest.raises(HTTPException) as e:
        db.run(auth.refresh(auth.RefreshRequest(refresh_token=rt), _req(), db))
    assert e.value.status_code == 401


def test_the_page_has_the_box_ticked_and_asks_for_it():
    assert '<input type="checkbox" id="inp-remember" checked>' in PAGE
    assert "refresh: rememberMe()" in PAGE
    for lang in ("'login-remember': 'Remember me'", "'login-remember': 'Запомнить меня'"):
        assert lang in PAGE


def test_the_page_retries_a_401_once_with_a_fresh_token():
    assert "window.fetch = async function (url, opts)" in PAGE
    assert "if (_refreshing) return _refreshing;" in PAGE
    # the refresh call itself is never retried, and Telegram never uses it
    assert "String(url).indexOf('/api/auth/') >= 0" in PAGE
    assert "&& IS_TG)) return Promise.resolve(false)" in PAGE


def test_without_the_box_the_session_dies_with_the_tab():
    fn = PAGE[PAGE.index("function saveSession("):PAGE.index("let _refreshing")]
    assert "sessionStorage.setItem('sov_token', accessToken)" in fn
    assert "localStorage.removeItem('sov_refresh')" in fn


def test_sign_out_closes_the_long_session_on_the_server():
    fn = PAGE[PAGE.index("function doLogout()"):PAGE.index("function hdrs()")]
    assert "/api/auth/logout" in fn and "sov_refresh" in fn
