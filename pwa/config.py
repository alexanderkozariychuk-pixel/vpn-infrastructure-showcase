import os
from dotenv import load_dotenv

load_dotenv()

# Foreign exit node (Cloud4Box DE) — status/logs/metrics are read from here
EXIT_IP = os.getenv("EXIT_IP", "")
EXIT_USER = os.getenv("EXIT_USER", "sovadmin")
AWG_INTERFACE = os.getenv("AWG_INTERFACE", "awg0")
AWG_SERVICE = f"awg-quick@{AWG_INTERFACE}"
# Backbone peer as seen FROM the exit node (the /30 far end = the RU entry).
# This link is what breaks; pinging it from the exit is the early-warning signal.
BACKBONE_PEER_IP = os.getenv("BACKBONE_PEER_IP", "10.77.77.2")

# Bridge
BRIDGE_IP = os.getenv("BRIDGE_IP", "")
BRIDGE_USER = os.getenv("BRIDGE_USER", "vpnadmin")
BRIDGE_AWG_INTERFACE = os.getenv("BRIDGE_AWG_INTERFACE", "awg0")

# LLM
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "google/gemini-2.0-flash-001")


# ── Plans ───────────────────────────────────────────────────────────────────
#
# The key carries both tier and period. `Payment.plan` is a plain string the
# gateways echo back untouched, so encoding the period in the key means the
# webhook knows how long a payment bought without a schema change and without
# trusting anything in the request — the amount is still read from here and
# compared against what the gateway reports.
#
# Longer periods are discounted well past the usual 10–15%. That is deliberate:
# a subscription paid six months up front is money now, which is worth more
# here than the margin given up.
#
# `card` is why the six-month plans exist only in crypto.
#
# A six-month subscription is six months of obligation, and the card rail is
# the part of this service that can end without warning and not by our
# decision. Collecting half a year up front against it means holding refund
# duties that would have to be discharged through a channel that is gone —
# and a refund to different details than the payment is exactly what the
# terms refuse, for good anti-fraud reasons. Crypto settles immediately, is
# not tied to one jurisdiction, and survives a relocation.
#
# So: card buys one or three months. Crypto buys any period.
PLANS = {
    "basic-1m": {"tier": "basic", "configs": 2, "days": 30,  "amount": "350",  "currency": "RUB", "card": True},
    "basic-3m": {"tier": "basic", "configs": 2, "days": 90,  "amount": "900",  "currency": "RUB", "card": True},
    "basic-6m": {"tier": "basic", "configs": 2, "days": 180, "amount": "1700", "currency": "RUB", "card": False},
    "ext-1m":   {"tier": "ext",   "configs": 5, "days": 30,  "amount": "650",  "currency": "RUB", "card": True},
    "ext-3m":   {"tier": "ext",   "configs": 5, "days": 90,  "amount": "1700", "currency": "RUB", "card": True},
    "ext-6m":   {"tier": "ext",   "configs": 5, "days": 180, "amount": "3200", "currency": "RUB", "card": False},
}

# Plan names written before periods existed. Payments created under the old
# name can still be pending at a gateway, and `users.plan` holds it too — so
# both must keep resolving rather than raising a KeyError inside a webhook.
_LEGACY_PLAN_ALIASES = {
    "Basic": "basic-1m",
    "Family": "ext-1m",
}

DEFAULT_CONFIG_LIMIT = 1


def plan_info(key: str | None) -> dict | None:
    """Plan metadata by key, resolving names from before periods existed."""
    if not key:
        return None
    if key in PLANS:
        return PLANS[key]
    return PLANS.get(_LEGACY_PLAN_ALIASES.get(key, ""))


def card_allowed(plan_key: str | None) -> bool:
    """
    Whether this plan may be paid by card.

    Defaults to False for anything unrecognised: a plan the table no longer
    describes must not reach the card rail by accident.
    """
    info = plan_info(plan_key)
    return bool(info and info.get("card"))


def config_limit(plan_key: str | None) -> int:
    """
    How many active configs a plan allows.

    An unknown plan gets one, not zero: a customer whose plan name no longer
    exists should keep the device they already have rather than silently lose
    access to it.
    """
    info = plan_info(plan_key)
    return info["configs"] if info else DEFAULT_CONFIG_LIMIT
