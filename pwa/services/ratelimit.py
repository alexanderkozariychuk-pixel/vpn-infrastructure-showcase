"""
services/ratelimit.py — how often one source may try something.

Login, registration and password reset had no limits at all: an admin
password could be guessed over the internet at whatever rate the network
allowed, and the registration form would send our welcome letter to any
address, as often as anyone liked.

Counts live in this process's memory. That is enough because the portal runs
as a single uvicorn worker (entrypoint.sh starts one, without --workers): every
request passes through the same dictionary. A second worker would quietly
halve every limit — each would keep its own counts — so adding one means
moving this to the database or Redis first. A restart forgets the counts;
that only ever errs toward letting someone retry sooner.

Keys are built from the source address, so they are only as honest as that
address. services/net.resolve_source_ip reads X-Real-IP, which nginx must
*set* (proxy_set_header X-Real-IP $remote_addr). Without that line a caller
could name any address and dodge every per-address limit, and requests
without the header would all share nginx's own address and one counter.
"""

import time
from collections import deque

from fastapi import HTTPException


class Limiter:
    """At most `limit` events per key in any `window` seconds (sliding)."""

    # Every this many recorded events, forget keys whose window has emptied,
    # so a stream of one-off addresses cannot grow the dictionary forever.
    _SWEEP_EVERY = 1000

    def __init__(self, limit: int, window: int, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._events: dict[str, deque] = {}
        self._since_sweep = 0

    def _prune(self, key: str, now: float) -> deque | None:
        q = self._events.get(key)
        if q is None:
            return None
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            del self._events[key]
            return None
        return q

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may act again, or None if it may act now."""
        now = self._clock()
        q = self._prune(key, now)
        if q is None or len(q) < self.limit:
            return None
        return max(1, int(q[0] + self.window - now) + 1)

    def add(self, key: str) -> None:
        now = self._clock()
        self._events.setdefault(key, deque()).append(now)
        self._since_sweep += 1
        if self._since_sweep >= self._SWEEP_EVERY:
            self._since_sweep = 0
            for k in list(self._events):
                self._prune(k, now)

    def reset(self) -> None:
        self._events.clear()


def too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many attempts, try again later",
        headers={"Retry-After": str(retry_after)},
    )


def check(limiter: Limiter, key: str) -> None:
    """Raise 429 if `key` is over its limit; otherwise do nothing."""
    wait = limiter.retry_after(key)
    if wait is not None:
        raise too_many(wait)


def take(limiter: Limiter, key: str) -> None:
    """Count one attempt for `key`, refusing it if the limit is already used."""
    check(limiter, key)
    limiter.add(key)


# ── the limits ────────────────────────────────────────────────────────────
#
# Login: every attempt from an address counts toward a generous ceiling, and
# failed ones for a given (address, username) toward a tighter one. There is
# deliberately no lock on a username alone: that would let anyone lock a
# customer out of their own account by failing on purpose. A guess spread
# across many addresses is slowed only by argon2 and the 8-character minimum.
LOGIN_PER_IP = Limiter(limit=30, window=15 * 60)
LOGIN_FAILS = Limiter(limit=10, window=15 * 60)

# Registration sends a letter, so it is limited per address.
REGISTER_PER_IP = Limiter(limit=5, window=60 * 60)

# Reset requests send a letter to an address someone typed: per address of the
# requester, and per mailbox so no one inbox can be flooded from many places.
FORGOT_PER_IP = Limiter(limit=5, window=60 * 60)
FORGOT_PER_EMAIL = Limiter(limit=3, window=60 * 60)

# Submitting a reset token. Tokens are 256-bit, so this is not what stops a
# guess; it keeps a script from hammering argon2 through this door.
RESET_PER_IP = Limiter(limit=10, window=60 * 60)

# Support tickets are letters to our own inbox, through the same sending quota.
SUPPORT_PER_IP = Limiter(limit=5, window=60 * 60)

ALL = (LOGIN_PER_IP, LOGIN_FAILS, REGISTER_PER_IP,
       FORGOT_PER_IP, FORGOT_PER_EMAIL, RESET_PER_IP, SUPPORT_PER_IP)
