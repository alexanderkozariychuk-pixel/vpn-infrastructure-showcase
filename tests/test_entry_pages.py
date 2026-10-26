"""
The way in: the home page with its intro, and the portal opening on sign-in.

2026-09-29: the portal's own promo screen was merged into the home page. A
visitor now arrives at sov3r3ign.com, sees the intro once per session, and
goes to the account from there; /app opens directly on sign-in. The promo
screen took with it a public "admin" link and a hard-coded "All systems
operational" that stayed green whatever the nodes were doing.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pwa" / "static"
LANDING = STATIC / "landing.html"
INDEX = STATIC / "index.html"


def _landing() -> str:
    return LANDING.read_text(encoding="utf-8")


def _portal() -> str:
    return INDEX.read_text(encoding="utf-8")


# ── the intro ────────────────────────────────────────────────────────────────

def test_the_intro_never_hides_the_page_from_crawlers_or_no_js_visitors():
    """
    The overlay is display:none unless the head script has set html.intro —
    a moderator, a crawler or a visitor without JS gets the page at once.
    """
    html = _landing()
    assert "#intro { display: none; }" in html
    head = html[:html.index("</head>")]
    assert "classList.add('intro')" in head, "the intro must be decided before first paint"


def test_the_intro_is_skipped_for_reduced_motion_and_after_the_first_time():
    head = _landing()[:_landing().index("</head>")]
    script = head[head.index("<script>"):head.index("</script>")]
    assert "prefers-reduced-motion: reduce" in script
    assert "sessionStorage.getItem('sov_intro')" in script


def test_the_intro_removes_itself_without_any_later_script():
    """If the script at the end of the page never runs, CSS still lifts it."""
    html = _landing()
    rule = html[html.index("html.intro #intro {"):]
    rule = rule[:rule.index("}")]
    assert "animation: intro-out" in rule
    assert re.search(r"@keyframes intro-out \{ to \{[^}]*visibility: hidden", html)


def test_nothing_waits_on_an_animation_to_appear_under_reduced_motion():
    """.rise starts at opacity 0; reduced motion must not leave it there."""
    html = _landing()
    block = html[html.index("@media (prefers-reduced-motion: reduce) {"):]
    block = block[:block.index("\n  }\n")]
    assert ".rise { opacity: 1 !important; animation: none !important; }" in block


# ── the home page ────────────────────────────────────────────────────────────

def test_the_home_page_carries_the_slogan():
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", _landing(), re.S).group(1)
    text = re.sub(r"<[^>]+>", "", h1)
    assert text == "Подключение, собранное лично под вас"


def test_the_account_is_in_the_top_bar_and_the_hero_offers_the_trial():
    """2026-10-27: a second blue "Личный кабинет" in the hero called for
    nothing; the hero's main button is the trial."""
    html = _landing()
    top = html[html.index('<header class="topbar">'):html.index("</header>")]
    hero = html[html.index('<div class="hero">'):html.index('class="perks')]
    assert 'href="/app"' in top and "Личный кабинет" in top
    assert "Личный кабинет" not in hero
    assert 'id="hero-trial" href="/app?trial=1"' in hero


def test_packets_light_up_the_buttons():
    html = _landing()
    assert 'id="net-top"' in html and "querySelectorAll('.signin, #hero-trial')" in html
    assert ".signin.hit" in html and ".cta.hit" in html
    # still for those who asked for less motion
    assert "if (!top || still) return;" in html


# ── the portal ───────────────────────────────────────────────────────────────

def test_the_portal_has_no_promo_screen_of_its_own():
    html = _portal()
    assert 'id="view-landing"' not in html
    assert "showView('landing')" not in html


def test_the_portal_opens_on_sign_in():
    assert '<div id="view-login" class="view active">' in _portal()


def test_sign_in_offers_registration_and_the_way_home():
    html = _portal()
    login = html[html.index('<div id="view-login"'):html.index('<div id="view-reset"')]
    assert "showView('register')" in login, "a new customer has no way to register"
    assert 'href="/"' in login


def test_no_public_admin_link_and_no_fake_status():
    """
    The admin panel is reached by signing in as admin — the portal routes by
    username — so nothing on a public screen needs to advertise it. And a
    status line that is green whatever the nodes are doing is worse than none.
    """
    html = _portal()
    # The screens anyone can see: sign-in, password reset, registration.
    public = html[html.index('<div id="view-login"'):html.index('<div id="view-dashboard"')]
    assert "showView('login', 'admin')" not in html
    assert "admin" not in public.lower()
    assert "All systems operational" not in html
    assert "Все системы работают" not in html


def test_sign_in_and_registration_speak_the_customers_language():
    """
    Sign-in is now the portal's front door. Its title and labels were
    hard-coded English on a Russian site although the translations existed
    in both tables — the markup simply never used them.
    """
    html = _portal()
    login = html[html.index('<div id="view-login"'):html.index('<div id="view-dashboard"')]
    for bare in ("<label>Username</label>", "<label>Password</label>", ">Sign<span> in</span>",
                 "<label>Email</label>", "<label>Confirm Password</label>"):
        assert bare not in login, f"untranslated: {bare}"
    keys = set(re.findall(r'data-i18n="([\w-]+)"', login))
    assert {"login-home", "login-no-account", "btn-create", "label-username",
            "label-password", "login-title-1", "reg-title-1", "btn-reg"} <= keys, keys
    for lang in ("en", "ru"):
        start = html.index(f"\n  {lang}: {{\n")
        table = html[start:html.index("\n  },", start)]
        missing = sorted(k for k in keys if f"'{k}':" not in table)
        assert not missing, f"{lang}: {missing}"


def test_an_empty_translation_is_used_not_replaced_by_english():
    """
    Found on the rendered page: the Russian sign-in title read "Вход in".
    Its second half is deliberately '', and t() treated '' as missing and
    fell through to English. A present key is the translation.
    """
    html = _portal()
    fn = html[html.index("function t(key) {"):]
    fn = fn[:fn.index("\n}\n")]
    assert "hasOwnProperty" in fn
    assert "|| translations['en'][key]" not in fn


def test_the_account_has_the_landing_network_quietly_behind_it():
    html = _portal()
    assert 'id="bg-net"' in html and ".bg-net { position: fixed;" in html and "z-index: -1" in html
    # no flashes inside the account, and still for reduced motion
    assert ".hit" not in html.split('id="bg-net"')[1].split("</script>")[0]
    assert ".bg-net .pkt { display: none; }" in html
