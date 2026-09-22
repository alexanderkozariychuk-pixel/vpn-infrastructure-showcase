"""
The clause numbers on the legal pages must be the numbers they claim.

This is not pedantry. Both documents refer to their own clauses — "по пункту
13", "действует пункт 12" — and a reader who cannot find clause 13 has no way
to know what the sentence promises them.

The numbering was rendered by a CSS counter reset on every <ol>, with a
hand-written rule per `start` value to put it back. Those rules went stale the
first time a clause was inserted, and every section on the live page was
rendering from 1. — the `start` attributes said one thing and the page showed
another, silently, because nothing checked.

Two things are checked here:

  * the `start` attributes run continuously, so the document numbers every
    clause exactly once;
  * no per-`start` counter rule has come back, since that is the construct
    that made the page and its markup disagree without anyone noticing.
"""

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "pwa" / "static"
PAGES = ["offer.html", "privacy.html"]


def _lists(html: str) -> list[tuple[int, int]]:
    """(declared start, number of clauses) for each list, in document order."""
    out = []
    for match in re.finditer(r"<ol(?P<attrs>[^>]*)>(?P<body>.*?)</ol>", html, re.S):
        start = re.search(r'start="(\d+)"', match.group("attrs"))
        out.append((int(start.group(1)) if start else 1,
                    len(re.findall(r"<li[ >]", match.group("body")))))
    return out


@pytest.mark.parametrize("page", PAGES)
def test_clause_numbers_run_continuously(page):
    lists = _lists((STATIC / page).read_text(encoding="utf-8"))
    assert lists, f"{page} has no numbered lists"

    expected = 1
    for start, count in lists:
        assert start == expected, (
            f"{page}: a list declares start={start} where the previous section "
            f"ended at {expected - 1} — a clause is numbered twice or skipped"
        )
        expected += count


@pytest.mark.parametrize("page", PAGES)
def test_the_counter_is_not_reset_per_list(page):
    """
    The construct that broke it. A counter reset inside a list makes the
    rendered number independent of the `start` attribute, so the test above
    can pass while the page shows 1.
    """
    css = (STATIC / page).read_text(encoding="utf-8")
    assert not re.search(r"ol\[start=", css), (
        f"{page} is back to hand-written per-start counter rules; these go "
        f"stale the moment a clause is inserted"
    )
    assert not re.search(r"\bol\s*\{[^}]*counter-reset", css), (
        f"{page} resets the clause counter on every <ol>, which restarts the "
        f"numbering in each section regardless of its start attribute"
    )


@pytest.mark.parametrize("page", PAGES)
def test_every_cross_reference_points_at_a_clause_that_exists(page):
    html = (STATIC / page).read_text(encoding="utf-8")
    lists = _lists(html)
    total = sum(count for _, count in lists)

    text = re.sub(r"<[^>]+>", " ", html)
    for number in re.findall(r"пункт[ауеом]{0,2}\s+(\d+)", text):
        assert 1 <= int(number) <= total, (
            f"{page} refers to clause {number}, but the document has {total}"
        )
