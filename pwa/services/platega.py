"""
services/platega.py — Platega payment gateway.

One gateway for everything: the customer picks SBP / card / crypto on
Platega's own page. We create the transaction without fixing a method
(POST /v2/transaction/process) and redirect to the `url` it returns.

Auth is a header pair — X-MerchantId + X-Secret — the same on our outgoing
requests and on the callback Platega sends us. There is no signature over the
callback body: on its own a callback proves only that the caller knows our
secret. So the callback is a nudge, never the truth. `fetch_status` re-asks
Platega over our own authenticated request, and only its answer decides
whether a subscription is granted — a forged CONFIRMED callback changes
nothing, because Platega still says PENDING.

Secrets live in the environment (.env on the server), never in the repo.
"""

import hmac
import logging
import os

import httpx

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("PLATEGA_BASE_URL", "https://app.platega.io").rstrip("/")
MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "")
SECRET = os.getenv("PLATEGA_SECRET", "")

# Platega's PaymentStatus enum.
CONFIRMED = "CONFIRMED"
CANCELED = "CANCELED"
PENDING = "PENDING"
CHARGEBACKED = "CHARGEBACKED"

_TIMEOUT = httpx.Timeout(20.0)


def _headers() -> dict:
    return {
        "X-MerchantId": MERCHANT_ID,
        "X-Secret": SECRET,
        "Content-Type": "application/json",
    }


async def create_transaction(
    amount,
    currency: str,
    description: str,
    return_url: str,
    failed_url: str,
    order_id: str | None = None,
    user_id: str | None = None,
    user_name: str | None = None,
    client_ip: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """
    Create a payment the customer completes on Platega's page.

    `amount` goes in as a JSON number. Returns the raw response dict,
    {transactionId, status, url, expiresIn, rate}; the caller stores
    transactionId as the payment's provider_ref and redirects to `url`.

    `client` is for tests; production passes none and one is opened here.
    """
    payload: dict = {
        "paymentDetails": {"amount": amount, "currency": currency},
        "description": description,
        "return": return_url,
        "failedUrl": failed_url,
    }
    if order_id:
        payload["orderId"] = order_id
    # Antifraud metadata, sent whenever we have a user. Harmless when the shop
    # does not require it; the shop is disabled if it does and we omit it, so
    # the safe default is to always send it.
    if user_id:
        meta = {"userId": str(user_id), "userName": user_name or str(user_id)}
        if client_ip:
            meta["clientIp"] = client_ip
        payload["metadata"] = meta

    return await _post_json("/v2/transaction/process", payload, client)


async def fetch_status(transaction_id: str, client: httpx.AsyncClient | None = None) -> dict | None:
    """
    The real state of a transaction, straight from Platega — the source of
    truth a callback is checked against. Returns the response dict, or None if
    Platega does not know the id (404).
    """
    path = f"/transaction/{transaction_id}"
    if client is not None:
        resp = await client.get(f"{BASE_URL}{path}", headers=_headers())
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.get(f"{BASE_URL}{path}", headers=_headers())
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


async def _post_json(path: str, payload: dict, client: httpx.AsyncClient | None) -> dict:
    if client is not None:
        resp = await client.post(f"{BASE_URL}{path}", headers=_headers(), json=payload)
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            resp = await c.post(f"{BASE_URL}{path}", headers=_headers(), json=payload)
    resp.raise_for_status()
    return resp.json()


def secret_matches(supplied: str | None) -> bool:
    """
    Constant-time check of the X-Secret a callback carries. First gate only —
    a caller with the secret can still forge a body, which is why the caller
    verifies through fetch_status rather than trusting what the callback says.
    """
    return bool(SECRET) and hmac.compare_digest(supplied or "", SECRET)
