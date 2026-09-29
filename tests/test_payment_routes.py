"""
Which gateways the server answers for — a decision, pinned.

2026-09-29: FreeKassa removed once Platega had taken a live payment. Heleket
kept on the server as a fallback, though the portal no longer offers it. A
route coming back, or the fallback quietly disappearing in a cleanup, should
be a deliberate change that fails here first.
"""

from api import payment


def _paths():
    # The payment router, where every gateway's routes have lived. Importing
    # the whole app would need the production-only admin password set.
    return {getattr(r, "path", "") for r in payment.router.routes}


def test_freekassa_is_gone():
    assert not [p for p in _paths() if "freekassa" in p.lower()]


def test_platega_answers():
    paths = _paths()
    assert "/api/payment/platega/create" in paths
    assert "/api/payment/platega/callback" in paths


def test_heleket_is_kept_as_the_fallback():
    paths = _paths()
    assert "/api/payment/create" in paths
    assert "/api/payment/webhook" in paths
