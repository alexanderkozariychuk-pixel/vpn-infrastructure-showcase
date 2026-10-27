"""
"Sign in with Google": a token Google signed for us signs in, ties to an
account with the same CONFIRMED address, or creates one after a username —
and nothing else gets through.
"""
import os
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk, jwt
from sqlalchemy import select

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

import config  # noqa: E402
from api import google_auth as g  # noqa: E402
from db.models import User  # noqa: E402
from services import ratelimit  # noqa: E402

CLIENT = "123-test.apps.googleusercontent.com"
_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = _priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
PUB = _priv.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()
JWKS = {"keys": [{**jwk.construct(PUB, "RS256").to_dict(), "kid": "k1", "use": "sig", "alg": "RS256"}]}
_other = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()


def token(sub="g-1", email="ivan@gmail.com", verified=True, aud=CLIENT, iss="https://accounts.google.com",
          exp=None, key=PEM):
    claims = {"sub": sub, "email": email, "email_verified": verified, "aud": aud, "iss": iss,
              "iat": int(time.time()), "exp": exp or int(time.time()) + 600}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture(autouse=True)
def on(monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", CLIENT)

    async def keys():
        return JWKS
    monkeypatch.setattr(g, "_google_keys", keys)
    for lim in ratelimit.ALL:
        lim.reset()


def _req():
    return SimpleNamespace(headers={"x-real-ip": "198.51.100.20"}, client=None)


def call(db, cred, **kw):
    return db.run(g.google_sign_in(g.GoogleIn(credential=cred, **kw), _req(), db))


def refused(db, cred, **kw):
    with pytest.raises(HTTPException) as e:
        call(db, cred, **kw)
    return e.value.status_code, e.value.detail


def _user(db, name="ivan_1", email="ivan@gmail.com", verified=True, **kw):
    u = User(id=str(uuid.uuid4()), username=name, email=email, password_hash="x",
             email_verified_at=datetime.now(timezone.utc) if verified else None, **kw)
    db.add(u)
    db.run(db.commit())
    return u


@pytest.mark.parametrize("bad", [
    dict(aud="someone-else"), dict(iss="https://evil.example"), dict(verified=False),
    dict(exp=int(time.time()) - 60), dict(key=_other),
])
def test_only_a_token_google_signed_for_us(db, bad):
    assert refused(db, token(**bad))[0] == 401


def test_garbage_and_no_client_id(db, monkeypatch):
    assert refused(db, "not.a.jwt")[0] == 401
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
    assert refused(db, token()) == (503, "google_off")


def test_someone_new_picks_a_name_and_gets_a_confirmed_account(db):
    code, detail = refused(db, token())
    assert code == 404 and detail == {"code": "need_username", "suggest": "ivan"}
    r = call(db, token(), username="ivan_g", remember=True)
    assert r["username"] == "ivan_g" and r["access_token"] and r["refresh_token"]
    u = db.run(db.execute(select(User).where(User.username == "ivan_g"))).scalar_one()
    assert u.google_sub == "g-1" and u.email == "ivan@gmail.com" and u.email_verified_at is not None


def test_next_time_it_just_signs_in(db):
    call(db, token(), username="ivan_g")
    r = call(db, token())
    assert r["username"] == "ivan_g" and r["refresh_token"] is None


def test_a_confirmed_address_ties_the_existing_account(db):
    u = _user(db)
    r = call(db, token(email="Ivan@Gmail.com"))
    db.run(db.refresh(u))
    assert r["username"] == "ivan_1" and u.google_sub == "g-1"


def test_an_unconfirmed_address_is_not_enough(db):
    """Anyone can type someone else's address at registration."""
    u = _user(db, verified=False)
    assert refused(db, token()) == (409, "email_unconfirmed")
    db.run(db.refresh(u))
    assert u.google_sub is None


def test_names_are_checked_like_everywhere(db):
    _user(db, name="Taken_1", email="other@x.test")
    assert refused(db, token(), username="taken_1") == (409, "username_taken")
    assert refused(db, token(), username="bad name") == (422, "bad_username")


def test_a_disabled_account_stays_out(db):
    _user(db, is_active=False)
    assert refused(db, token())[0] == 403


def test_the_page_gets_the_client_id():
    assert db_free_run(g.auth_options()) == {"google_client_id": CLIENT}


def db_free_run(c):
    import asyncio
    return asyncio.run(c)


def test_the_page_offers_google_outside_telegram_only():
    from pathlib import Path
    page = (Path(g.__file__).parent.parent / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="g-btn-login"' in page and 'id="g-btn-register"' in page and 'id="view-gname"' in page
    assert "if (IS_TG) tgBoot();\n  else initGoogle();" in page
    privacy = (Path(g.__file__).parent.parent / "static" / "privacy.html").read_text(encoding="utf-8")
    assert "входите через Google" in privacy
