"""
The price on the page must be the price that gets charged.

The portal carries its own copy of the plan table, because it renders prices
before any request is made. The server reads its own table and compares the
amount against what the gateway reports, so a stale number in the page cannot
be paid — but it can be *shown*, and a customer who clicks "1700 ₽" and lands
on a gateway asking 3200 does not come back.

This test is the thing that notices when the two drift apart.
"""

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from config import PLANS  # noqa: E402


INDEX = Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html"


@pytest.fixture(scope="module")
def portal_plans() -> dict:
    """The PLANS object as the page declares it."""
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r"const PLANS = \{(.*?)\n\};", html, re.S)
    assert match, "PLANS object not found in index.html"

    body = match.group(1)
    plans = {}
    for key, fields in re.findall(r"'([\w-]+)':\s*\{([^}]*)\}", body):
        entry = {}
        for name, value in re.findall(r"(\w+):\s*'?([\w-]+)'?", fields):
            entry[name] = int(value) if value.isdigit() else value
        plans[key] = entry
    assert plans, "PLANS object parsed as empty"
    return plans


def test_same_plan_keys(portal_plans):
    assert set(portal_plans) == set(PLANS), (
        "plan keys differ between the portal and the server: "
        f"{sorted(set(portal_plans) ^ set(PLANS))}"
    )


def test_same_prices(portal_plans):
    mismatched = {
        key: (portal_plans[key]["amount"], int(PLANS[key]["amount"]))
        for key in PLANS
        if key in portal_plans and portal_plans[key]["amount"] != int(PLANS[key]["amount"])
    }
    assert not mismatched, f"portal shows a different price than the server charges: {mismatched}"


def test_same_device_limits(portal_plans):
    """
    The device count is a promise made on the pricing card and enforced by the
    server when a config is requested. Disagreement here is a support ticket.
    """
    mismatched = {
        key: (portal_plans[key]["configs"], PLANS[key]["configs"])
        for key in PLANS
        if key in portal_plans and portal_plans[key]["configs"] != PLANS[key]["configs"]
    }
    assert not mismatched, f"device limits differ: {mismatched}"


def test_same_periods(portal_plans):
    mismatched = {
        key: (portal_plans[key]["days"], PLANS[key]["days"])
        for key in PLANS
        if key in portal_plans and portal_plans[key]["days"] != PLANS[key]["days"]
    }
    assert not mismatched, f"periods differ: {mismatched}"


def test_every_checkout_button_names_a_real_tier():
    """
    The page builds a plan key as `${tier}-${period}`. A tier in the markup
    that no plan uses would send the server a key it rejects, after the
    customer has already chosen to pay.
    """
    html = INDEX.read_text(encoding="utf-8")
    tiers = set(re.findall(r"openCheckout\('([\w-]+)'\)", html))
    known = {info["tier"] for info in PLANS.values()}
    assert tiers <= known, f"markup offers unknown tiers: {sorted(tiers - known)}"


def test_every_tier_has_all_periods():
    """A tier missing a period would render a card with no price on that tab."""
    periods = {key.rsplit("-", 1)[1] for key in PLANS}
    for tier in {info["tier"] for info in PLANS.values()}:
        for period in periods:
            assert f"{tier}-{period}" in PLANS, f"{tier} has no {period} plan"


def test_period_tabs_match_the_plan_table():
    html = INDEX.read_text(encoding="utf-8")
    tabs = set(re.findall(r'data-period="([\w-]+)"', html))
    periods = {key.rsplit("-", 1)[1] for key in PLANS}
    assert tabs == periods, f"period tabs {sorted(tabs)} do not match plans {sorted(periods)}"


def test_advertised_discount_is_never_overstated():
    """
    One label sits on a period tab shared by both tiers, so it has to hold for
    the worse of the two. The invariant is one-directional on purpose: claiming
    less than the customer gets is fine, claiming more is a false price.
    """
    html = INDEX.read_text(encoding="utf-8")
    claimed = {
        period: int(value)
        for period, value in re.findall(r"'period-save-(\w+)':\s*'−(\d+)%'", html)
    }
    assert claimed, "discount labels not found"

    for period, pct in claimed.items():
        months = int(period.rstrip("m"))
        for tier in {info["tier"] for info in PLANS.values()}:
            monthly = int(PLANS[f"{tier}-1m"]["amount"])
            actual = int(PLANS[f"{tier}-{period}"]["amount"]) / months
            real_pct = (1 - actual / monthly) * 100
            assert pct <= real_pct + 0.5, (
                f"{tier}-{period} advertises −{pct}% but gives only "
                f"−{real_pct:.1f}%"
            )


def test_advertised_discount_is_not_pointlessly_modest():
    """The flip side: a label far below the real discount is money left on the table."""
    html = INDEX.read_text(encoding="utf-8")
    claimed = {
        period: int(value)
        for period, value in re.findall(r"'period-save-(\w+)':\s*'−(\d+)%'", html)
    }
    for period, pct in claimed.items():
        months = int(period.rstrip("m"))
        worst = min(
            (1 - int(PLANS[f"{tier}-{period}"]['amount']) / months
             / int(PLANS[f"{tier}-1m"]['amount'])) * 100
            for tier in {info["tier"] for info in PLANS.values()}
        )
        assert worst - pct <= 3, (
            f"{period} tab claims −{pct}% while every tier gives at least −{worst:.1f}%"
        )


def test_json_shape_is_what_the_endpoints_expect():
    """The payment endpoints take {'plan': <key>}; keys must be plain strings."""
    for key in PLANS:
        assert json.dumps({"plan": key}), key
        assert re.fullmatch(r"[a-z]+-\d+m", key), f"unexpected plan key shape: {key}"


# ── card availability ───────────────────────────────────────────────────────
#
# Six months is crypto-only. That rule lives in three places — the plan table,
# the checkout, and the terms the customer accepts — and all three have to say
# the same thing. A page offering a card button the endpoint refuses is worse
# than no button at all.

OFFER = INDEX.parent / "offer.html"


def test_the_card_flag_is_still_enforced_server_side():
    """
    Every plan takes the fiat rail today, so nothing exercises this path — and
    a guard nothing exercises is a guard that quietly rots.

    The flag used to be False for the six-month plans, while fiat and crypto
    came from two independent providers and splitting the long periods across
    them spread the risk of losing one. With both rails behind a single
    provider that split protects nothing, so the restriction is lifted. The
    mechanism stays: if the rails are ever separated again, flipping the flag
    has to be the whole change.
    """
    import inspect

    from api import payment

    source = inspect.getsource(payment.create_payment_freekassa)
    assert "card_allowed" in source, (
        "the fiat endpoint no longer checks card_allowed — flipping a plan "
        "back to card=False would then silently do nothing"
    )


def test_card_flag_agrees_between_server_and_portal(portal_plans):
    mismatched = {
        key: (portal_plans[key].get("card"), PLANS[key].get("card"))
        for key in PLANS
        if key in portal_plans
        and str(portal_plans[key].get("card")).lower() != str(PLANS[key].get("card")).lower()
    }
    assert not mismatched, f"card availability differs: {mismatched}"


def test_the_portal_hides_the_card_option_rather_than_failing_after_the_click():
    html = INDEX.read_text(encoding="utf-8")
    assert "pay-method-card" in html, "the card method needs an id to be hidden"
    assert "plan.card ?" in html, "checkout does not branch on card availability"


def test_the_terms_do_not_carry_the_retired_payment_restriction():
    """
    The terms used to state that six months could be paid in crypto only. That
    promise is gone from the product, and a document promising a restriction
    the service no longer applies is worse than one that never mentioned it —
    a customer reads it and expects to be refused.

    Also, a payment provider reads this document during moderation. A clause
    explaining that we route long subscriptions away from the fiat rail
    because it might stop working reads exactly as it sounds.
    """
    raw = OFFER.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))

    assert "только криптовалютой" not in text, (
        "the terms still restrict a period to crypto, but no plan does"
    )
    assert "300 рублей в месяц" not in text, "terms still quote the old single price"


def test_the_terms_still_promise_a_refund_route_that_survives():
    """
    This clause stays, and is the opposite of the one above: it commits the
    service to refunding even when the original details cannot be used. It
    protects the customer rather than the service, which is what a bank
    reviewing consumer terms is looking for.
    """
    raw = OFFER.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))

    assert "иным согласованным с вами способом" in text
    assert "Отказать в возврате по этой причине сервис не вправе" in text


def test_the_checkout_does_not_compute_the_discount_itself():
    """
    Two places computing one price eventually give two answers, and the
    customer is shown the wrong one. The page renders plan cards from its own
    table — that is before anyone has logged in — but from the checkout
    onwards every figure comes from /api/payment/quote.
    """
    html = INDEX.read_text(encoding="utf-8")
    assert "/api/payment/quote" in html, "the checkout never asks the server for a price"
    assert "q.amount" in html and "q.credit_spent" in html, (
        "the order summary is not being filled from the quote"
    )
    assert "discount_percent / 100" not in html, (
        "the page is computing a discount of its own"
    )


def test_every_refusal_reason_has_wording_in_both_languages():
    """
    A code the customer cannot use has to say why, in the language they are
    reading. The server returns a token precisely because it cannot know that
    language — so a reason added there without wording here would surface as
    a bare token like `used_up` in a Russian portal.
    """
    from services.credit import REFUSAL_TEXT

    html = INDEX.read_text(encoding="utf-8")
    start_en, start_ru = html.index("\n  en: {"), html.index("\n  ru: {")
    en = set(re.findall(r"^\s*'([a-z0-9\-]+)':", html[start_en:start_ru], re.M))
    ru = set(re.findall(r"^\s*'([a-z0-9\-]+)':", html[start_ru:], re.M))

    for token in REFUSAL_TEXT:
        key = "promo-no-" + token.replace("_", "-")
        assert key in en, f"no English wording for refusal {token!r} ({key})"
        assert key in ru, f"no Russian wording for refusal {token!r} ({key})"


def test_the_referral_panel_is_wired_up():
    html = INDEX.read_text(encoding="utf-8")
    for needed in ("/api/client/credit", "/api/client/referral",
                   "paytab-referral", "loadReferral"):
        assert needed in html, f"referral panel is missing {needed}"


def test_the_terms_cover_points_and_referral_codes():
    """
    The programme creates an obligation — points the service will honour as a
    discount months from now — and an obligation with nothing written down is
    one the customer cannot hold anyone to. Each figure here is also a number
    in the code, so this is the second place either one can be caught drifting.
    """
    from services.credit import (
        DEFAULT_DISCOUNT_PERCENT, MAX_CREDIT_SHARE, REFERRAL_REWARD,
        REWARD_VESTING_DAYS,
    )

    raw = OFFER.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))

    assert "Баллы и промокоды" in text, "the terms say nothing about points"
    assert str(REFERRAL_REWARD) in text, f"the reward ({REFERRAL_REWARD}) is not stated"
    assert f"{DEFAULT_DISCOUNT_PERCENT}%" in text, "the invitee discount is not stated"
    assert f"{REWARD_VESTING_DAYS} дней" in text, "the vesting period is not stated"
    assert int(MAX_CREDIT_SHARE * 2) == 1 and "не более половины" in text, (
        "the cap on how much of an order points may cover is not stated"
    )
    # Points that look like a stored balance of money are a different kind of
    # product with a different set of rules attached to it.
    assert "не являются денежными средствами" in text, (
        "the terms do not say points are not money"
    )


def test_dates_follow_the_portal_language_not_the_browser():
    """
    `toLocaleDateString()` with no argument follows the browser's locale. The
    portal has its own language toggle, and that is the only setting the
    customer chose — a Russian portal was showing 9/19/2026 to anyone whose
    browser was English. Every date goes through one formatter now.
    """
    html = INDEX.read_text(encoding="utf-8")
    # A call, not the word — the comment explaining this rule says it too.
    bare = re.findall(r"\.toLocaleDateString\(\s*\)", html)
    assert not bare, (
        f"{len(bare)} date(s) formatted with the browser's locale instead of "
        f"the portal's language — route them through fmtDate()"
    )
    assert "function fmtDate(" in html, "the shared date formatter is gone"
