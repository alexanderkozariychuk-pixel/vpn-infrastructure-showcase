"""
Source address checks for incoming notifications.

The allowlist is only meaningful if the address it reads cannot be supplied by
the caller. Behind nginx that depends on a configuration line outside this
codebase, which these tests document but cannot enforce.
"""

from types import SimpleNamespace


def _request(headers=None, peer=None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=peer) if peer else None,
    )


def test_listed_address_is_allowed(fk):
    listed = next(iter(fk.NOTIFY_IPS))
    assert fk.ip_allowed(listed) is True


def test_unlisted_address_is_rejected(fk):
    assert fk.ip_allowed("203.0.113.10") is False


def test_empty_address_is_rejected(fk):
    assert fk.ip_allowed("") is False


def test_header_is_preferred_over_the_peer(fk):
    """
    Behind a proxy the peer is always the proxy. The header carries the real
    client — but only because nginx is configured to *set* it:

        proxy_set_header X-Real-IP $remote_addr;

    Without that, a caller sets the header themselves and this preference
    becomes the vulnerability rather than the fix.
    """
    req = _request(headers={"x-real-ip": "198.51.100.7"}, peer="172.18.0.1")
    assert fk.resolve_source_ip(req) == "198.51.100.7"


def test_falls_back_to_the_peer_without_the_header(fk):
    req = _request(peer="172.18.0.1")
    assert fk.resolve_source_ip(req) == "172.18.0.1"


def test_returns_empty_when_nothing_is_available(fk):
    assert fk.resolve_source_ip(_request()) == ""
