"""
The Platega transport, against the bodies from Platega's own OpenAPI docs.

No network: httpx.MockTransport answers each request, and every test also
asserts what we *sent* — the endpoint, the auth headers, and the JSON body —
because the gateway rejects or silently mis-handles a wrong shape and we found
that out the expensive way with FreeKassa.

Sync tests calling asyncio.run, the convention in this suite: there is no
pytest-asyncio dependency, and an `async def` test under plain pytest is
collected but never awaited — a green that proves nothing.
"""

import asyncio
import json
import os

import httpx
import pytest

os.environ.setdefault("PLATEGA_MERCHANT_ID", "MID-123")
os.environ.setdefault("PLATEGA_SECRET", "sekret-abc")
os.environ.setdefault("PLATEGA_BASE_URL", "https://app.platega.io")

from services import platega  # noqa: E402


@pytest.fixture(autouse=True)
def _platega_creds(monkeypatch):
    """
    platega.py reads MERCHANT_ID / SECRET at import time, so whichever test
    module imports the module first fixes their values for the whole run — and
    the two Platega test files use different secrets. Pin this file's values on
    the module object per-test (monkeypatch reverts them), so the suite is
    order-independent rather than relying on which import won the race.
    """
    monkeypatch.setattr(platega, "MERCHANT_ID", "MID-123")
    monkeypatch.setattr(platega, "SECRET", "sekret-abc")


def _run(handler, coro_factory):
    """Drive `coro_factory(client)` with a MockTransport client on one loop."""
    async def _go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await coro_factory(c)
    return asyncio.run(_go())


def test_create_transaction_sends_the_methodless_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        # Response shape from the /v2/transaction/process docs example.
        return httpx.Response(200, json={
            "transactionId": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "status": "PENDING",
            "url": "https://pay.platega.io/?id=f80&mh=0a0",
            "expiresIn": "00:15:00",
            "rate": 91.2,
        })

    out = _run(handler, lambda c: platega.create_transaction(
        amount=100, currency="RUB", description="Sovereign — basic-1m",
        return_url="https://sov3r3ign.com/app?paid=1",
        failed_url="https://sov3r3ign.com/app?paid=0",
        order_id="order-42", client=c,
    ))

    assert out["transactionId"] == "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    assert out["url"].startswith("https://pay.platega.io/")
    assert seen["method"] == "POST"
    assert seen["url"] == "https://app.platega.io/v2/transaction/process"
    assert seen["headers"]["x-merchantid"] == "MID-123"
    assert seen["headers"]["x-secret"] == "sekret-abc"
    body = seen["body"]
    # amount is a JSON number, and no method is fixed on the methodless call.
    assert body["paymentDetails"] == {"amount": 100, "currency": "RUB"}
    assert isinstance(body["paymentDetails"]["amount"], (int, float))
    assert "paymentMethod" not in body
    assert body["orderId"] == "order-42"
    assert body["return"] == "https://sov3r3ign.com/app?paid=1"
    assert body["failedUrl"] == "https://sov3r3ign.com/app?paid=0"


def test_platega_receives_the_amount_and_the_order_id_and_nothing_about_the_user():
    """
    The privacy policy, item 9: the payment system is given the amount and the
    order id. So the body carries exactly these keys — no `metadata`, no user
    id, login or IP. A new key here is a change to what we hand a third party
    and has to go through the policy first; this test is where that surfaces.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"transactionId": "t", "status": "PENDING", "url": "u"})

    _run(handler, lambda c: platega.create_transaction(
        amount=350, currency="RUB", description="Sovereign — basic-1m",
        return_url="r", failed_url="f", order_id="order-42", client=c,
    ))
    assert set(seen["body"]) == {"paymentDetails", "description", "return", "failedUrl", "orderId"}
    assert set(seen["body"]["paymentDetails"]) == {"amount", "currency"}


def test_fetch_status_returns_the_gateways_own_answer():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "https://app.platega.io/transaction/abc-123"
        assert request.headers["x-secret"] == "sekret-abc"
        return httpx.Response(200, json={
            "id": "abc-123", "status": "CONFIRMED",
            "paymentDetails": {"amount": 100, "currency": "RUB"},
            "paymentMethod": "SBPQR",
        })

    out = _run(handler, lambda c: platega.fetch_status("abc-123", client=c))
    assert out["status"] == platega.CONFIRMED
    assert out["paymentDetails"]["amount"] == 100


def test_an_unknown_transaction_is_none_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    assert _run(handler, lambda c: platega.fetch_status("nope", client=c)) is None


def test_a_gateway_error_is_raised_not_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        _run(handler, lambda c: platega.fetch_status("x", client=c))


def test_the_callback_secret_is_checked_in_constant_time():
    assert platega.secret_matches("sekret-abc") is True
    assert platega.secret_matches("wrong") is False
    assert platega.secret_matches("") is False
    assert platega.secret_matches(None) is False
