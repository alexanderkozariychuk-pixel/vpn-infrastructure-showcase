"""
Role separation between authenticated clients and the admin.

`require_auth` only proves a token is valid, and every registered client holds
a valid token. Until these guards existed, the routes that read production node
state, list other users, and flip `is_subscribed` accepted any client's token —
in a public repository, where the route names are published.

So these tests are written around what must be *rejected*. Each case is a way a
paying (or non-paying) customer could have reached something that is not theirs.
"""

import asyncio
import os

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# auth.jwt refuses to import without a secret, by design — the old default was
# public in this repo's history. Set one before importing.
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")

from auth.jwt import create_token, require_admin, require_auth  # noqa: E402


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _call(guard, token: str) -> dict:
    """The guards are async; run one without pulling in an async test plugin."""
    return asyncio.run(guard(_creds(token)))


@pytest.fixture
def client_token() -> str:
    """What every registered customer gets at login."""
    return create_token({"sub": "customer", "role": "client"})


@pytest.fixture
def admin_token() -> str:
    return create_token({"sub": "admin", "role": "admin"})


def test_client_token_is_rejected_by_admin_guard(client_token):
    """The whole point: a valid client token must not open an admin route."""
    with pytest.raises(HTTPException) as exc:
        _call(require_admin, client_token)
    assert exc.value.status_code == 403


def test_token_without_a_role_is_rejected(admin_token):
    """
    Tokens minted before the role claim existed carry no role at all. They must
    fail closed rather than be treated as trusted because they are old.
    """
    legacy = create_token({"sub": "admin"})
    with pytest.raises(HTTPException) as exc:
        _call(require_admin, legacy)
    assert exc.value.status_code == 403


def test_role_is_matched_exactly(client_token):
    """No prefix, case or substring match — only the exact string 'admin'."""
    for role in ("Admin", "ADMIN", "administrator", "admin ", " admin", "superadmin"):
        token = create_token({"sub": "customer", "role": role})
        with pytest.raises(HTTPException) as exc:
            _call(require_admin, token)
        assert exc.value.status_code == 403, f"role {role!r} was accepted"


def test_garbage_token_is_rejected_as_unauthorized():
    """A forged or corrupt token fails at decode, before the role is looked at."""
    with pytest.raises(HTTPException) as exc:
        _call(require_admin, "not.a.token")
    assert exc.value.status_code == 401


def test_admin_token_passes(admin_token):
    payload = _call(require_admin, admin_token)
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"


def test_client_token_still_passes_require_auth(client_token):
    """
    Client routes must keep working — the fix tightens the admin surface, it
    does not lock customers out of their own config.
    """
    payload = _call(require_auth, client_token)
    assert payload["sub"] == "customer"
