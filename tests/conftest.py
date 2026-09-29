"""
Shared fixtures.

Some service modules read their credentials at import time (services.platega
does), so tests patch module attributes rather than the environment —
setting environment variables after import would have no effect. That is
worth noting as a design smell in those modules: configuration read at
import is configuration that cannot be changed without reloading.
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
