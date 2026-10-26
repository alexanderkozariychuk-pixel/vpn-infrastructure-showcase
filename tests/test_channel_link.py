"""The public Telegram channel is linked from every page a customer lands on."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "pwa" / "static"
CHANNEL = "https://t.me/sov3r3ign_net"


def test_the_channel_is_linked_everywhere():
    for page in ("index.html", "landing.html", "about.html"):
        assert CHANNEL in (STATIC / page).read_text(encoding="utf-8"), page


def test_the_support_page_points_to_it_for_status():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    support = html[html.index('id="client-page-support"'):]
    assert CHANNEL in support[:2000]
