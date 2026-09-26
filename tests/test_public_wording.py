"""
Vocabulary the site does not use, on any page the server hands out.

The wording line was a decision (2026-09-23): describe what the service does
for the customer, never what it works around. Naming the thing being worked
around puts the payment integration at risk, and a payment provider's
moderator reads the site before approving it.

The decision held on the pages that were reviewed and failed on the one that
was not. The portal's tariff cards said "Обфускация трафика под DPI" for
weeks: the HTML carried a neutral default, and the translation table in the
page's own script replaced it on load. A dead key beside it, rendered nowhere,
still read "Конфиг обхода белых списков" to anyone who opened the source.

So this reads source, not rendered text. Whatever a browser can fetch, a
moderator can read, including strings no screen ever shows.
"""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "pwa" / "static"

# Every file a browser can be served that carries prose. Globbed rather than
# listed so a new page is covered the day it is added.
SERVED = sorted(STATIC.glob("*.html")) + [STATIC / "icons" / "manifest.json"]

# Case-insensitive. Deliberately narrow: "заблокировать промокод" in the terms
# is ordinary language, and "VPN" is what the phone's own permission prompt
# says, so the setup guide has to use it.
BANNED = {
    "DPI": r"\bDPI\b",
    # \b because "необходимо" contains the letters.
    "обход": r"\bобход",
    "белые списки": r"бел\w*\s+спис",
    "блокировки": r"блокировк",
    "цензура": r"цензур",
    "РКН": r"роскомнадзор|\bРКН\b",
    "bypass": r"\bbypass",
    "allowlist / whitelist": r"\b(allow|white)[\s-]?list",
    "censorship": r"censor",
    "circumvent": r"circumvent",
}

# Inline images are base64; "+DpI/" is a perfectly good substring of one.
_DATA_URI = re.compile(r"data:[^\s\"')]+")


def _source(path: Path) -> str:
    return _DATA_URI.sub("", path.read_text(encoding="utf-8"))


def test_the_served_files_were_found():
    # A glob that matches nothing makes every test below pass vacuously.
    names = {p.name for p in SERVED}
    assert {"landing.html", "index.html", "offer.html", "privacy.html"} <= names
    assert all(p.exists() for p in SERVED)


@pytest.mark.parametrize("path", SERVED, ids=lambda p: p.name)
@pytest.mark.parametrize("label", BANNED)
def test_no_served_file_names_what_the_service_works_around(path, label):
    hits = [
        f"{n}: {line.strip()[:120]}"
        for n, line in enumerate(_source(path).splitlines(), 1)
        if re.search(BANNED[label], line, re.IGNORECASE)
    ]
    assert not hits, f"{path.name} says '{label}':\n" + "\n".join(hits)
