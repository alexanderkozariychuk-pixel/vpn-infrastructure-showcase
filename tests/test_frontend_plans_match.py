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


def test_only_the_short_periods_take_a_card():
    by_card = {key: bool(info.get("card")) for key, info in PLANS.items()}
    for key, allowed in by_card.items():
        expected = PLANS[key]["days"] < 180
        assert allowed is expected, f"{key}: card={allowed}, days={PLANS[key]['days']}"


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


def test_the_terms_say_so_too():
    """
    The rule is a promise to the customer, not only a server-side check. If the
    terms do not carry it, a six-month buyer has no written answer to 'why can
    I not pay by card' — and no written answer to what happens if the channel
    used for their payment stops existing.
    """
    # Markup wraps lines wherever it likes, so match the rendered text rather
    # than the source: a phrase split across two lines is still the phrase.
    raw = OFFER.read_text(encoding="utf-8")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))

    assert "только криптовалютой" in text, "terms do not state the crypto-only rule"
    assert "иным согласованным с вами способом" in text, (
        "terms lack the alternative-refund clause — a six-month buyer has no "
        "written answer to what happens if the channel they paid through stops "
        "existing"
    )
    assert "300 рублей в месяц" not in text, "terms still quote the old single price"
