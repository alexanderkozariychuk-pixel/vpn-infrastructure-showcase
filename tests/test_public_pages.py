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


def test_the_hero_price_is_a_real_plan_price():
    """
    The headline figure, the one a visitor reads before anything else. It used
    to say 300 ₽ — the single price from before periods existed.

    Scoped to the hero deliberately. An earlier version of this test forbade
    the string "300 ₽" anywhere on the page, which broke the day the tariff
    table started showing per-month equivalents: 900 ₽ for three months really
    is 300 ₽ a month. The number was never the problem; advertising a price
    nobody can pay was.
    """
    import re as _re

    html = LANDING.read_text(encoding="utf-8")
    hero = html[html.index('class="hero"'):html.index("</section>", html.index('class="hero"'))
                if "</section>" in html[html.index('class="hero"'):]
                else html.index('<section')]
    shown = _re.search(r'class="price">\s*(\d+)\s*₽', hero)
    assert shown, "the hero shows no price at all"

    real = {int(p["amount"]) for p in PLANS.values()}
    assert int(shown.group(1)) in real, (
        f"the hero advertises {shown.group(1)} ₽, which is not a price the "
        f"server charges: {sorted(real)}"
    )


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


# ── the icon beside the search result ───────────────────────────────────────
#
# Google takes the favicon from the HOME PAGE specifically — not from the
# portal, not from a manifest — and Googlebot-Image has to be able to fetch
# the file. The landing declared only 16 and 32 px, below the size Google's
# own guidance points at, and /favicon.ico answered 404.

ICONS = STATIC / "icons"


def test_the_home_page_declares_an_icon_large_enough_for_search():
    raw = LANDING.read_text(encoding="utf-8")
    sizes = [int(s.split("x")[0]) for s in re.findall(r'rel="icon"[^>]*sizes="(\d+x\d+)"', raw)]
    assert sizes, "the home page declares no sized icon at all"
    assert max(sizes) >= 48, (
        f"largest declared icon is {max(sizes)}px; Google recommends larger "
        f"than 48px for the favicon beside a search result"
    )


def test_every_declared_icon_file_exists_and_is_square():
    from PIL import Image

    raw = LANDING.read_text(encoding="utf-8")
    hrefs = re.findall(r'rel="(?:icon|apple-touch-icon)"[^>]*href="([^"]+)"', raw)
    assert hrefs, "the home page links no icons"

    for href in hrefs:
        # /favicon.ico is served by a route, not from the static tree.
        path = ICONS / "favicon.ico" if href == "/favicon.ico" else STATIC.parent / href.lstrip("/")
        assert path.exists(), f"{href} is declared but not in the build"
        with Image.open(path) as im:
            assert im.width == im.height, f"{href} is {im.width}x{im.height}, not square"


def test_the_root_favicon_carries_the_sizes_a_search_result_uses():
    from PIL import Image

    ico = ICONS / "favicon.ico"
    assert ico.exists(), "no favicon.ico — the path browsers request unprompted"
    with Image.open(ico) as im:
        sizes = {s[0] for s in im.info.get("sizes", [])}
    assert 48 in sizes, f"favicon.ico has {sorted(sizes)}, no 48px frame"


def test_nothing_blocks_the_crawler_from_the_icons():
    robots = ROBOTS.read_text(encoding="utf-8")
    disallowed = re.findall(r"^Disallow:\s*(\S+)", robots, re.M)
    for blocked in disallowed:
        assert not "/static/icons/".startswith(blocked.rstrip("*")) or blocked == "/", (
            f"robots.txt disallows {blocked}, which covers the icons"
        )
    assert "Allow: /favicon.ico" in robots


def test_the_home_page_can_be_added_to_a_home_screen():
    """
    The portal had the touch icon and manifest; the landing did not, so adding
    *it* to a home screen produced a blank square.
    """
    raw = LANDING.read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon"' in raw
    assert 'rel="manifest"' in raw


def test_the_favicon_is_the_heavy_cut_not_the_app_icon():
    """
    The app icon is drawn for 180 px and up. At 16 px its strokes fall below a
    pixel and the mark becomes three faint dots with nothing joining them —
    which is the one idea it exists to carry. The favicon links must point at
    the heavier cut, not at icon-*.png.
    """
    raw = LANDING.read_text(encoding="utf-8")
    icon_hrefs = re.findall(r'rel="icon"[^>]*href="([^"]+)"', raw)
    app_icons = [h for h in icon_hrefs if "/icon-" in h]
    assert not app_icons, (
        f"the home page serves the app icon as its favicon: {app_icons} — "
        f"use the favicon-*.png cut from icons/make_favicon.py"
    )


def test_the_heavy_cut_actually_covers_more_ink_at_16px():
    """
    The property the cut exists for, measured rather than asserted: at 16 px
    the favicon must put visibly more accent colour on screen than the app
    icon does. A regenerated set with the wrong parameters would pass every
    other test here and still be invisible in a search result.
    """
    from PIL import Image

    def accent_pixels(path, size=16):
        with Image.open(path) as im:
            small = im.convert("RGB").resize((size, size), Image.LANCZOS)
            # Anything clearly brighter than the near-black background.
            pixels = list(small.convert('RGB').tobytes())
            triples = zip(pixels[0::3], pixels[1::3], pixels[2::3])
            return sum(1 for r, _g, b in triples if b > 90 and b > r + 40)

    heavy = accent_pixels(ICONS / "favicon-16.png")
    light = accent_pixels(ICONS / "icon-192.png")
    assert heavy > light * 1.5, (
        f"the favicon cut covers {heavy} px at 16x16 against the app icon's "
        f"{light} — it is not meaningfully heavier"
    )


# ── the public tariff table ─────────────────────────────────────────────────
#
# Prices used to be visible only after logging in. That is fine for a customer
# who already bought, and useless for everyone deciding whether to: someone
# comparing services, and a payment provider's moderator checking what is
# charged for what. The landing showed one number — the entry price — and a
# button leading to a login form.

def test_every_plan_appears_in_the_public_table():
    """
    All six, not just the cheapest. A table that omits the plan someone is
    about to buy is worse than no table.
    """
    text = _text(LANDING)
    missing = [k for k, v in PLANS.items() if f"{int(v['amount'])} ₽" not in text]
    assert not missing, f"these plans are not shown publicly: {missing}"


def test_the_public_table_quotes_no_price_that_does_not_exist():
    """The check that catches a price edited in one place and not the other."""
    import re as _re

    section = LANDING.read_text(encoding="utf-8")
    start = section.index('id="tariffs"')
    end = section.index("</section>", start)
    quoted = {int(m) for m in _re.findall(r"<b>(\d+) ₽</b>", section[start:end])}
    real = {int(v["amount"]) for v in PLANS.values()}
    assert quoted == real, (
        f"public table shows {sorted(quoted)}, the server charges {sorted(real)}"
    )


def test_the_public_table_states_the_device_limits():
    text = _text(LANDING)
    for limit in sorted({config_limit(k) for k in PLANS}):
        assert f"до {limit} конфигураций" in text, (
            f"the table does not state the {limit}-config limit"
        )


def test_the_table_marks_exactly_the_crypto_only_periods():
    """
    Both directions, on purpose. The earlier version only checked that
    crypto-only plans carried the mark; when the restriction was lifted and
    no plan was crypto-only any more, its loop ran zero times and it passed
    while proving nothing. This also fails if a mark is left behind on a plan
    that now takes the fiat rail — which is the mistake actually available
    today.
    """
    section = LANDING.read_text(encoding="utf-8")
    start = section.index('id="tariffs"')
    table = section[start:section.index("</section>", start)]

    for key, info in PLANS.items():
        amount = int(info["amount"])
        cell = table[table.index(f"<b>{amount} ₽</b>"):]
        cell = cell[:cell.index("</td>")]
        marked = "only-crypto" in cell
        assert marked is (not info["card"]), (
            f"{key}: table marks it crypto-only={marked}, "
            f"the server says card={info['card']}"
        )


def test_the_tariffs_are_reachable_from_the_footer():
    """A moderator should not have to scroll to find them."""
    assert 'href="/#tariffs"' in LANDING.read_text(encoding="utf-8")
