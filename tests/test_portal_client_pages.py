"""
The client portal's own pages: My Config, Connect, Support.

Static checks against index.html, the way the rest of the portal is tested —
there is no JS test runner in this repo. Each test pins one promise the page
makes to a customer, so a later edit that quietly breaks it fails here.
"""

import re
from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "pwa" / "static" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _dict(html: str, lang: str) -> str:
    """The body of one language's translation table."""
    start = html.index(f"\n  {lang}: {{\n")
    end = html.index("\n  },", start)
    return html[start:end]


# ── My Config ────────────────────────────────────────────────────────────────

def test_my_config_lists_every_device_not_just_the_newest():
    """
    A plan buys several devices. The old page read /api/client/config, which
    returns one — the newest — so a customer with two devices could only ever
    see and download one of them.
    """
    html = _html()
    assert "`${API}/api/client/configs`" in html
    assert "/api/client/configs/${encodeURIComponent(id)}/raw" in html
    assert "`${API}/api/client/config`" not in html, "the single-config endpoint is back"
    assert 'id="cl-devices"' in html


def test_copy_is_defined_once_and_copies_the_file_not_the_page():
    """
    There used to be two copyConfig functions; the later one won and copied
    the block's innerText — the "Copy" button label included, at the top of
    the customer's config.
    """
    html = _html()
    assert html.count("function copyConfig(") == 1
    body = html[html.index("function copyConfig("):]
    body = body[:body.index("\n}\n")]
    assert "_configText" in body
    assert "innerText" not in body


def test_a_downloaded_file_is_named_after_its_device():
    """
    Two devices must not download under the same name, and AmneziaWG on
    Android refuses long .conf filenames — so the device's short name, not
    sovereign-<username>.
    """
    html = _html()
    body = html[html.index("function downloadConfig("):]
    body = body[:body.index("\n}\n")]
    assert "_configName" in body
    assert "sovereign-${user}" not in body


def test_device_names_are_escaped_before_they_reach_the_page():
    """Names are set by the client apps, so they are input, not markup."""
    html = _html()
    body = html[html.index("function renderDevices("):]
    body = body[:body.index("\n}\n")]
    assert "escHtml(String(c.name" in body


# ── Connect ──────────────────────────────────────────────────────────────────

def test_connect_offers_android_and_ios_each_with_its_own_steps():
    html = _html()
    assert 'id="client-page-connect"' in html
    assert 'data-page="connect"' in html, "no menu item for the section"
    for plat in ("android", "ios"):
        assert f'data-plat="{plat}"' in html
        assert f'id="conn-panel-{plat}"' in html
        # Hidden until chosen: the customer sees only their own device's steps.
        panel = html[html.index(f'id="conn-panel-{plat}"'):]
        assert panel[:panel.index(">")].rstrip().endswith("hidden")


def test_connect_says_the_apps_are_coming_and_amneziawg_is_how_it_works_today():
    for lang in ("en", "ru"):
        table = _dict(_html(), lang)
        assert "'conn-android-app'" in table and "'conn-ios-app'" in table
        via = re.search(r"'conn-via-awg': '([^']*)'", table)
        assert via and "AmneziaWG" in via.group(1), f"{lang}: the AmneziaWG line is missing"


def test_every_connect_step_has_text_in_both_languages():
    html = _html()
    keys = set(re.findall(r'data-i18n="(conn-[\w-]+)"', html))
    assert keys, "no connect keys in the markup"
    for lang in ("en", "ru"):
        table = _dict(html, lang)
        missing = sorted(k for k in keys if f"'{k}':" not in table)
        assert not missing, f"{lang} has no text for {missing}"


def test_motion_respects_reduced_motion():
    html = _html()
    block = html[html.index("@media (prefers-reduced-motion: reduce)"):]
    block = block[:block.index("\n    }\n")]
    assert ".conn-step" in block and ".conn-pulse" in block


# ── Support ──────────────────────────────────────────────────────────────────

def test_support_no_longer_teaches_crypto_wallets():
    """
    Payment moved to Platega; the old FAQ walked customers through buying
    ETH, installing MetaMask and guarding a seed phrase. None of it applies,
    and a support page coaching wallet setup is the wrong page to keep.
    """
    html = _html()
    start = html.index('id="client-page-support"')
    page = html[start:html.index("</main>", start)]
    for word in ("MetaMask", "seed", "ERC-20", "bestchange", "хэш транзакции"):
        assert word not in page, f"support still mentions {word!r}"
    assert 'id="support-form-wrap"' in page, "the request form must stay"
