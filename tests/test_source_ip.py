"""
Where a request really came from, behind nginx.

Moved from the FreeKassa tests when that gateway was removed: the helper
outlived it, because the Platega callback logs the address of a request that
fails its secret check. The allowlist tests went with FreeKassa — nothing
decides access by address any more.
"""

from types import SimpleNamespace

from services import net


def _request(headers=None, peer=None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=peer) if peer else None,
    )


def test_header_is_preferred_over_the_peer():
    """
    Behind a proxy the peer is always the proxy. The header carries the real
    client — but only because nginx is configured to *set* it:

        proxy_set_header X-Real-IP $remote_addr;

    Without that, a caller sets the header themselves. Harmless while the
    value is only logged; a vulnerability the day it decides access.
    """
    req = _request(headers={"x-real-ip": "198.51.100.7"}, peer="172.18.0.1")
    assert net.resolve_source_ip(req) == "198.51.100.7"


def test_falls_back_to_the_peer_without_the_header():
    req = _request(peer="172.18.0.1")
    assert net.resolve_source_ip(req) == "172.18.0.1"


def test_returns_empty_when_nothing_is_available():
    assert net.resolve_source_ip(_request()) == ""
