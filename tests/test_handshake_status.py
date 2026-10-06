"""Admin client list: the status badge read from `awg show`'s handshake text."""
import os

import pytest

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api.clients import _classify_handshake, handshake_age  # noqa: E402


@pytest.mark.parametrize("text,age", [
    ("Now", 0),
    ("45 seconds ago", 45),
    ("1 minute, 5 seconds ago", 65),
    ("2 hours, 3 minutes, 4 seconds ago", 7384),
    ("1 day, 2 hours, 3 minutes, 4 seconds ago", 93784),
    ("3 weeks, 1 day ago", 3 * 604800 + 86400),
    ("never", None),
    ("", None),
])
def test_age(text, age):
    assert handshake_age(text) == age


@pytest.mark.parametrize("text,status", [
    ("Now", "active"),
    ("1 minute, 59 seconds ago", "active"),
    ("3 minutes ago", "active"),
    ("3 minutes, 1 second ago", "idle"),
    ("2 hours, 3 minutes, 4 seconds ago", "idle"),
    ("5 days, 1 hour, 1 minute, 1 second ago", "idle"),
    ("never", "inactive"),
])
def test_status(text, status):
    assert _classify_handshake(text) == status
