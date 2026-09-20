"""
Shared fixtures.

`services.freekassa` reads its credentials at import time, so tests patch the
module attributes rather than the environment — setting environment variables
after import would have no effect. That is worth noting as a design smell in
the module itself: configuration read at import is configuration that cannot
be changed without reloading.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pwa"))

# Several application modules refuse to import without these — deliberately,
# because the old defaults were public in this repository's history. Set here
# so every test module gets them before it imports anything from pwa/.
os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from services import freekassa  # noqa: E402


TEST_MERCHANT = "7012"
TEST_SECRET_1 = "form-secret-not-a-real-key"
TEST_SECRET_2 = "notify-secret-not-a-real-key"


@pytest.fixture
def fk(monkeypatch):
    """The module with known credentials, restored after each test."""
    monkeypatch.setattr(freekassa, "MERCHANT_ID", TEST_MERCHANT)
    monkeypatch.setattr(freekassa, "SECRET_1", TEST_SECRET_1)
    monkeypatch.setattr(freekassa, "SECRET_2", TEST_SECRET_2)
    monkeypatch.setattr(freekassa, "PAY_URL", "https://pay.example.test/")
    return freekassa


@pytest.fixture
def signed_notification(fk):
    """
    A valid notification, built the way the gateway documents it:

        md5(MERCHANT_ID:AMOUNT:secret_word_2:MERCHANT_ORDER_ID)

    Computed here independently of the implementation — a test that reuses the
    code under test to build its own expected value proves nothing.
    """
    import hashlib

    def _make(amount="300.00", order_id="order-1", merchant=TEST_MERCHANT,
              secret=TEST_SECRET_2):
        raw = f"{merchant}:{amount}:{secret}:{order_id}"
        return {
            "MERCHANT_ID": merchant,
            "AMOUNT": amount,
            "MERCHANT_ORDER_ID": order_id,
            "SIGN": hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest(),
        }

    return _make


# ── async database fixture ──────────────────────────────────────────────────
#
# One event loop per test, shared by setup, the test body and teardown.
#
# Calling asyncio.run() per statement — which is what these tests did first —
# gives each call its own loop and closes it on the way out. The session and
# its aiosqlite connection stay bound to the loop that created them, so the
# driver's background thread then raises "Event loop is closed" during
# teardown. The suite passed anyway, which is exactly why it was worth fixing:
# a warning that only appears at teardown is the kind that turns into a flaky
# failure on some later pytest.
#
# The loop travels on the fixture object rather than in a module global.
# pytest imports this file as a plugin, and `from conftest import ...` in a
# test module produces a *second* copy of it — a global set by the fixture in
# one copy is still None in the other.


class _Session:
    """The session, plus `.run()` to drive it on the loop it belongs to."""

    def __init__(self, session, loop):
        self._session = session
        self._loop = loop

    def run(self, coro):
        return self._loop.run_until_complete(coro)

    def __getattr__(self, name):
        # Everything else — add, execute, commit — is the real session, so
        # application code under test cannot tell the difference.
        return getattr(self._session, name)


@pytest.fixture
def db():
    """A session against a real in-memory database, not a mock."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from db.base import Base

    loop = asyncio.new_event_loop()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return maker()

    session = loop.run_until_complete(_setup())
    try:
        yield _Session(session, loop)
    finally:
        loop.run_until_complete(session.close())
        loop.run_until_complete(engine.dispose())
        loop.close()
