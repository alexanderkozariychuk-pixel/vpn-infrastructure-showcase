"""
Hardening from the 2026-10-07 audit: short admin sessions, CORS limited to the
site, the container not running as root, SSH that never writes the read-only
key mount.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from jose import jwt  # noqa: E402

from auth import jwt as auth_jwt  # noqa: E402

PWA = Path(__file__).parent.parent / "pwa"


def _minutes_left(token):
    exp = jwt.get_unverified_claims(token)["exp"]
    return (exp - datetime.now(timezone.utc).timestamp()) / 60


def test_admin_tokens_are_short_and_client_tokens_are_not():
    admin = auth_jwt.create_token({"sub": "admin", "role": "admin"})
    client = auth_jwt.create_token({"sub": "ivan_1", "role": "client"})
    assert 110 < _minutes_left(admin) <= 120
    assert 23 * 60 < _minutes_left(client) <= 24 * 60


def test_an_expired_token_is_refused():
    import pytest
    from fastapi import HTTPException
    token = auth_jwt.create_token({"sub": "admin", "role": "admin"}, minutes=-1)
    with pytest.raises(HTTPException) as e:
        auth_jwt.decode_token(token)
    assert e.value.status_code == 401


def test_cors_allows_only_the_site(monkeypatch):
    from fastapi.middleware.cors import CORSMiddleware
    monkeypatch.chdir(PWA)
    import main
    cors = [m for m in main.app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS middleware missing"
    origins = cors[0].kwargs["allow_origins"]
    assert "*" not in origins


def test_the_container_does_not_run_as_root():
    dockerfile = (PWA / "Dockerfile").read_text()
    users = [l.split()[1] for l in dockerfile.splitlines() if l.startswith("USER ")]
    assert users and users[-1] not in ("root", "0")
    compose = (PWA / "docker-compose.yml").read_text()
    assert ":/root/.ssh" not in compose and "/home/app/.ssh:ro" in compose


def test_ssh_never_tries_to_write_the_key_mount():
    for name in ("provisioner.py", "net_manager.py"):
        src = (PWA / "services" / name).read_text()
        assert "UpdateHostKeys=no" in src, name
        assert "StrictHostKeyChecking=accept-new" not in src, name
        assert '"/root/.ssh' not in src.replace('os.getenv("PWA_SSH_DIR", "/root/.ssh")', ""), name


def test_admin_panel_signs_out_when_its_session_ends():
    html = (PWA / "static" / "index.html").read_text()
    assert "async function adminFetch(" in html
    for path in ("/api/clients", "/api/admin/grant", "/api/admin/notifications/broadcast", "/api/analyze"):
        assert f"adminFetch(`${{API}}{path}" in html, path


def test_escaping_covers_quotes():
    html = (PWA / "static" / "index.html").read_text()
    body = html[html.index("function escHtml("):html.index("async function adminFetch(")]
    assert "&quot;" in body and "&#39;" in body
