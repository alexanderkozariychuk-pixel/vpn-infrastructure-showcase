"""
Shared fixtures.

`services.freekassa` reads its credentials at import time, so tests patch the
module attributes rather than the environment — setting environment variables
after import would have no effect. That is worth noting as a design smell in
the module itself: configuration read at import is configuration that cannot
be changed without reloading.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pwa"))

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
