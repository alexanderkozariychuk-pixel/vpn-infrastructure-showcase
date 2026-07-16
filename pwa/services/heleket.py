r"""
Heleket crypto payment gateway integration.

Signature algorithm (per Heleket docs):
    sign = md5( base64( json_body ) + PAYMENT_API_KEY )

Critical gotcha: Heleket's backend (PHP json_encode) ESCAPES forward slashes
(/  ->  \/) and non-ASCII (\uXXXX). We must serialize identically or the
signature will not match — this matters because url_callback contains slashes.
We therefore sign and send the EXACT same serialized string.
"""
import os
import json
import base64
import hashlib
import hmac
import logging
import httpx

logger = logging.getLogger(__name__)

HELEKET_API = "https://api.heleket.com/v1"
MERCHANT_ID = os.getenv("HELEKET_MERCHANT_ID", "")
PAYMENT_API_KEY = os.getenv("HELEKET_API_KEY", "")


def _serialize(payload: dict) -> str:
    """Serialize a dict the same way PHP json_encode does: compact,
    ASCII-escaped, with forward slashes escaped."""
    s = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    return s.replace("/", "\\/")


def _make_sign(body_str: str) -> str:
    b64 = base64.b64encode(body_str.encode()).decode()
    return hashlib.md5((b64 + PAYMENT_API_KEY).encode()).hexdigest()


async def create_invoice(amount: str, currency: str, order_id: str,
                         url_callback: str, url_return: str | None = None,
                         url_success: str | None = None) -> dict:
    """Create a payment invoice. Returns Heleket 'result' dict containing
    at least 'uuid' and 'url' (the payment page to redirect the user to)."""
    payload = {
        "amount": str(amount),
        "currency": currency,
        "order_id": order_id,
        "url_callback": url_callback,
    }
    if url_return:
        payload["url_return"] = url_return
    if url_success:
        payload["url_success"] = url_success

    body_str = _serialize(payload)
    headers = {
        "merchant": MERCHANT_ID,
        "sign": _make_sign(body_str),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        # send the EXACT signed string, not a re-serialized json= payload
        resp = await client.post(f"{HELEKET_API}/payment", headers=headers, content=body_str)
        resp.raise_for_status()
        data = resp.json()
    return data.get("result", data)


def verify_webhook(raw_body: bytes) -> dict | None:
    """Verify an incoming webhook. Returns the parsed payload dict if the
    signature is valid, otherwise None."""
    try:
        data = json.loads(raw_body)
    except Exception:
        return None

    received_sign = data.get("sign")
    if not received_sign:
        return None

    # Recreate sign over the body WITHOUT the sign field
    check = {k: v for k, v in data.items() if k != "sign"}
    body_str = _serialize(check)
    expected = _make_sign(body_str)

    # constant-time compare (hmac, NOT hashlib — hashlib has no compare_digest)
    if not hmac.compare_digest(expected, str(received_sign)):
        # Log byte-level mismatch: PHP json_encode vs our re-serialization can
        # diverge on numeric types (10.00 -> 10.0). Needed to debug the first
        # real webhook; remove the raw dump once signatures are confirmed stable.
        logger.error(
            "Webhook signature mismatch.\n  raw:      %r\n  reserial: %r\n  expected: %s\n  received: %s",
            raw_body, body_str, expected, received_sign,
        )
        return None
    return data
