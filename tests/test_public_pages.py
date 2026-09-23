"""
The pages a stranger sees before they are a customer.

These drift silently, which is what makes them worth a test. The portal is
exercised constantly and a wrong number there gets noticed within a day; the
landing page is the one nobody signed in ever looks at again. It was still
advertising 300 ₽ a month — a price that stopped existing when periods
shipped — and still telling people to write to support for a second device,
three days after configs became self-service.

Nothing here checks wording or ranking. It checks that the public pages agree
with the product and with each other.
"""

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from config import PLANS, config_limit  # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "pwa" / "static"
LANDING = STATIC / "landing.html"
ROBOTS = STATIC / "robots.txt"
SITEMAP = STATIC / "sitemap.xml"

# The public page routes main.py serves. A new one added there without a line
# here is a page nobody will find.
PUBLIC_PAGES = ["/", "/about", "/offer", "/privacy"]
PRIVATE_PAGES = ["/app", "/reset"]


def _text(path: Path) -> str:
    """Rendered text — markup wraps lines wherever it likes."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", path.read_text(encoding="utf-8")))


# ── the landing agrees with the product ─────────────────────────────────────

def test_the_advertised_price_is_a_price_that_exists():
    cheapest = min(int(p["amount"]) for p in PLANS.values())
    text = _text(LANDING)
    assert f"{cheapest} ₽" in text, (
        f"the landing does not show the entry price ({cheapest} ₽) — it is the "
        f"first number a visitor sees and the one they expect at checkout"
    )


def test_the_landing_does_not_quote_a_retired_price():
    """300 ₽ was the single price before periods existed."""
    text = _text(LANDING)
    retired = {"300 ₽"} - {f"{int(p['amount'])} ₽" for p in PLANS.values()}
    for price in retired:
        assert price not in text, f"the landing still quotes {price}"


def test_the_landing_does_not_send_people_to_support_for_a_device():
    """
    Configs are self-service, up to the plan's limit. Telling a customer to
    write to support creates a ticket for something they can do themselves,
    and makes the product look more manual than it is.
    """
    text = _text(LANDING)
    assert "напишите в поддержку, выдадим" not in text
    assert "в личном кабинете" in text, (
        "the landing does not mention that devices are added in the portal"
    )


def test_the_landing_states_the_real_device_limits():
    limits = sorted({config_limit(k) for k in PLANS})
    text = _text(LANDING)
    assert str(max(limits)) in text or "пяти" in text, (
        f"the landing does not reflect the plan device limits {limits}"
    )


def test_support_is_the_service_address_not_a_personal_one():
    """
    The terms name sovrn.support@gmail.com. Two addresses on one site is one
    of them going unanswered.
    """
    raw = LANDING.read_text(encoding="utf-8")
    assert "sovrn.support@gmail.com" in raw
    assert "alexanderkozariychuk@gmail.com" not in raw


def test_the_landing_redirect_reads_the_key_the_portal_writes():
    """
    It read `token` while the portal writes `sov_token`, so the "returning
    visitor goes straight to the app" path had never once fired.
    """
    landing = LANDING.read_text(encoding="utf-8")
    portal = (STATIC / "index.html").read_text(encoding="utf-8")

    written = set(re.findall(r"localStorage\.setItem\('([a-z_]+)'", portal))
    read = set(re.findall(r"localStorage\.getItem\('([a-z_]+)'\)", landing))
    assert read <= written, (
        f"the landing reads {sorted(read - written)}, which the portal never "
        f"writes (it writes {sorted(written)})"
    )


# ── crawler-facing files ────────────────────────────────────────────────────

def test_robots_allows_the_public_pages_and_keeps_the_portal_out():
    robots = ROBOTS.read_text(encoding="utf-8")
    for page in PRIVATE_PAGES:
        assert f"Disallow: {page}" in robots, f"{page} is not kept out of the index"
    assert "Sitemap: https://sov3r3ign.com/sitemap.xml" in robots


def test_every_public_page_is_in_the_sitemap():
    sitemap = SITEMAP.read_text(encoding="utf-8")
    for page in PUBLIC_PAGES:
        url = "https://sov3r3ign.com" + (page if page != "/" else "/")
        assert f"<loc>{url}</loc>" in sitemap, f"{page} is missing from the sitemap"


def test_no_signed_in_page_is_in_the_sitemap():
    sitemap = SITEMAP.read_text(encoding="utf-8")
    for page in PRIVATE_PAGES:
        assert f"<loc>https://sov3r3ign.com{page}</loc>" not in sitemap


def test_the_portal_stays_out_of_search_results():
    portal = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'name="robots" content="noindex' in portal


@pytest.mark.parametrize("page", ["landing.html", "offer.html", "privacy.html", "about.html"])
def test_public_pages_declare_russian(page):
    """`lang` is what a crawler and a screen reader both believe."""
    html = (STATIC / page).read_text(encoding="utf-8")
    assert re.search(r'<html[^>]*lang="ru"', html), f"{page} does not declare lang=ru"


# ── link previews ───────────────────────────────────────────────────────────

def test_the_landing_has_a_link_preview():
    """
    The way this service actually grows is someone pasting a referral link
    into a messenger. A link with no card reads as spam.
    """
    raw = LANDING.read_text(encoding="utf-8")
    for tag in ("og:title", "og:description", "og:image", "og:url", "twitter:card"):
        assert tag in raw, f"the landing has no {tag}"


def test_the_preview_image_exists():
    raw = LANDING.read_text(encoding="utf-8")
    match = re.search(r'property="og:image" content="https://sov3r3ign\.com(/[^"]+)"', raw)
    assert match, "og:image is not a path on this site"
    assert (STATIC.parent / match.group(1).lstrip("/")).exists(), (
        f"og:image points at {match.group(1)}, which is not in the build"
    )
