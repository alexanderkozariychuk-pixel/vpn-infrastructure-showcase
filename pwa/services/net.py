"""
services/net.py — where a request really came from.

Lived in the FreeKassa module, which used it for that gateway's source-address
allowlist. FreeKassa is gone; the Platega callback still logs the address of a
request that fails its secret check, so the helper outlived the gateway.
"""


def resolve_source_ip(request) -> str:
    """
    Real source address behind nginx.

    Only correct if nginx *sets* the header rather than passing through what
    the client sent:

        proxy_set_header X-Real-IP $remote_addr;

    Without that line a caller supplies the header themselves. Today the value
    is only logged, so the worst case is a misleading log line — but anything
    that ever uses it to decide access must first verify that line in the live
    nginx config.
    """
    return (
        request.headers.get("x-real-ip")
        or (request.client.host if request.client else "")
    )
