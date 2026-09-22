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


# ── every admin route is actually wired to the guard ────────────────────────
#
# The tests above prove the guard works. This one proves it is *attached* —
# which is the failure that actually happened: eight routes reading node
# state and listing users were reachable with any customer's token, not
# because the guard was wrong but because it was not on them. A new admin
# route is exactly the moment to forget again.

def _admin_routes():
    """Every route under /api/admin plus the operational ones, from the app."""
    os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

    # main.py mounts ./static, so it has to be imported the way it is run:
    # with pwa/ as the working directory.
    import sys
    from contextlib import chdir

    pwa = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pwa")
    if "main" not in sys.modules:
        with chdir(pwa):
            import main  # noqa: F401
    import main
    from fastapi.routing import APIRoute

    found, seen = [], set()

    def walk(router):
        if id(router) in seen:
            return
        seen.add(id(router))
        for route in getattr(router, "routes", []):
            if isinstance(route, APIRoute):
                found.append(route)
            inner = getattr(route, "original_router", None) or getattr(route, "app", None)
            if inner is not None and hasattr(inner, "routes"):
                walk(inner)

    walk(main.app.router)
    return found


# Client-facing routes live under /api/client and are guarded by require_auth;
# everything else that reads or changes the service itself is admin-only.
CLIENT_PREFIXES = ("/api/client", "/api/auth", "/api/payment", "/api/register",
                   "/api/support", "/api/password")

# Deliberately unauthenticated, and each one justified here rather than
# silently skipped: /api is the latency ping the portal measures against.
PUBLIC_ROUTES = {"/api"}


def test_every_non_client_route_is_behind_the_admin_guard():
    from auth.jwt import require_admin as guard

    unguarded = []
    for route in _admin_routes():
        path = route.path
        if (path in PUBLIC_ROUTES or path.startswith(CLIENT_PREFIXES)
                or not path.startswith("/api")):
            continue
        deps = [d.call for d in route.dependant.dependencies]
        if guard not in deps:
            unguarded.append(f"{sorted(route.methods)} {path}")

    assert not unguarded, (
        "these routes are not behind require_admin: " + ", ".join(unguarded)
    )


def test_the_admin_promo_routes_are_registered():
    """A guarded router nobody included is a feature that silently is not there."""
    paths = {r.path for r in _admin_routes()}
    assert "/api/admin/promo" in paths
    assert "/api/admin/promo/{code}/deactivate" in paths
