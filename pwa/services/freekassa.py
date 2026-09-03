"""
services/freekassa.py — FreeKassa SCI integration.

Docs: https://docs.freekassa.net/

Two secrets, not interchangeable:
  FK_SECRET_1 -> signs the outgoing payment form
  FK_SECRET_2 -> signs the incoming notification

Both signatures are plain MD5 over a colon-joined string, so the signature
by itself is weak. Safety comes from the combination of:
  - source IP allowlist
  - amount checked against the server-side PLANS table, never the request
  - idempotency on our own order id
"""

import os
import hmac
import hashlib
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

MERCHANT_ID = os.getenv("FK_MERCHANT_ID", "")
SECRET_1 = os.getenv("FK_SECRET_1", "")
SECRET_2 = os.getenv("FK_SECRET_2", "")

# FreeKassa rotates payment domains (pay.fk.money, fmt.me, ...). Keep this in
# the environment so a mirror change is a restart, not a rebuild.
PAY_URL = os.getenv("FK_PAY_URL", "https://pay.fk.money/")

# Documented notification sources. Re-check against the docs periodically.
NOTIFY_IPS = frozenset({
    "168.119.157.136",
    "168.119.60.227",
    "178.154.197.79",
    "51.250.54.238",
})


def build_payment_url(order_id: str, amount: str, currency: str = "RUB",
                      email: str | None = None) -> str:
    """
    Build the SCI redirect URL.

    `amount` is used verbatim in both the URL and the signature — the two must
    be the same string. Passing "300" here and signing "300.00" fails with no
    useful error from FreeKassa.
    """
    raw = f"{MERCHANT_ID}:{amount}:{SECRET_1}:{currency}:{order_id}"
    params = {
        "m": MERCHANT_ID,
        "oa": amount,
        "o": order_id,
        "currency": currency,
        "s": hashlib.md5(raw.encode()).hexdigest(),
        "lang": "ru",
    }
    if email:
        params["em"] = email
    return f"{PAY_URL}?{urlencode(params)}"


def verify_notification(params: dict) -> bool:
    """
    Verify a notification signature.

    AMOUNT is used exactly as received: FreeKassa signs the string it sends,
    so normalising it here would break an otherwise valid signature. The
    business check on the amount happens separately, against PLANS.
    """
    sign = str(params.get("SIGN", "")).lower()
    merchant_id = str(params.get("MERCHANT_ID", ""))
    amount = str(params.get("AMOUNT", ""))
    order_id = str(params.get("MERCHANT_ORDER_ID", ""))

    if not sign or merchant_id != MERCHANT_ID:
        return False

    raw = f"{merchant_id}:{amount}:{SECRET_2}:{order_id}"
    expected = hashlib.md5(raw.encode()).hexdigest()
    return hmac.compare_digest(expected, sign)


def resolve_source_ip(request) -> str:
    """
    Real source address behind nginx.

    Only correct if nginx *sets* the header rather than passing through what
    the client sent:

        proxy_set_header X-Real-IP $remote_addr;

    Without that line an attacker supplies the header themselves and the
    allowlist check passes for anyone. Verify it in the live nginx config.
    """
    return (
        request.headers.get("x-real-ip")
        or (request.client.host if request.client else "")
    )


def ip_allowed(ip: str) -> bool:
    return ip in NOTIFY_IPS
