"""
The admin's peer list: every peer on the node named from what we know —
a portal account, the operator's label, or nothing (unknown).
"""
import base64
import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import clients  # noqa: E402
from db.models import Config, User  # noqa: E402
from services.net_manager import PeerStatus  # noqa: E402

ADMIN = {"sub": "admin", "role": "admin"}


def _key(n):
    return base64.b64encode(bytes([n]) * 32).decode()


@pytest.fixture
def node(monkeypatch):
    peers = []
    monkeypatch.setattr(clients, "get_bridge_status_data", lambda: (peers, None))
    return peers


def _account(db, username, key, name="device-1", kind="paid"):
    u = User(id=str(uuid.uuid4()), username=username, email=f"{username}@example.com", password_hash="x")
    db.add(u)
    db.add(Config(user_id=u.id, name=name, public_key=key, private_key="x", preshared_key="x",
                  peer_ip="10.88.88.9", kind=kind, is_active=True))
    db.run(db.commit())


def _list(db):
    return db.run(clients.get_clients(ADMIN, db))


def _label(db, key, label):
    return db.run(clients.set_label(clients.LabelRequest(public_key=key, label=label), ADMIN, db))


def test_each_peer_is_named_by_what_we_know(db, node):
    _account(db, "ivan_1", _key(1))
    _account(db, "petr_2", _key(2), name="trial", kind="trial")
    node += [PeerStatus(_key(1), handshake="Now"), PeerStatus(_key(2)), PeerStatus(_key(3)), PeerStatus(_key(4))]
    _label(db, _key(3), "Мама — iPhone")
    out = {c["key"]: c for c in _list(db)["clients"]}
    assert (out[_key(1)]["name"], out[_key(1)]["source"]) == ("ivan_1 · device-1", "portal")
    assert out[_key(2)]["source"] == "trial"
    assert (out[_key(3)]["name"], out[_key(3)]["source"]) == ("Мама — iPhone", "manual")
    assert (out[_key(4)]["name"], out[_key(4)]["source"]) == (_key(4)[:12], "unknown")
    assert _list(db)["sources"] == {"portal": 1, "trial": 1, "manual": 1, "unknown": 1}


def test_a_label_can_be_changed_and_removed(db, node):
    node.append(PeerStatus(_key(5)))
    _label(db, _key(5), "old")
    _label(db, _key(5), "new")
    assert _list(db)["clients"][0]["name"] == "new"
    _label(db, _key(5), "  ")
    assert _list(db)["clients"][0]["source"] == "unknown"


def test_a_portal_peer_cannot_be_relabelled(db, node):
    _account(db, "ivan_1", _key(1))
    with pytest.raises(HTTPException) as e:
        _label(db, _key(1), "x")
    assert e.value.status_code == 409


@pytest.mark.parametrize("key", ["", "abc", "not base64 at all!!", base64.b64encode(b"x" * 31).decode()])
def test_only_real_keys_can_be_labelled(db, key):
    with pytest.raises(HTTPException) as e:
        _label(db, key, "x")
    assert e.value.status_code == 422


def test_labels_are_drawn_escaped():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "pwa" / "static" / "index.html").read_text()
    assert "${escHtml(c.name)}" in html and "${escHtml(c.endpoint || '—')}" in html


def test_pages_are_revalidated_and_the_build_is_published(monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    # The app serves static/ relative to its own directory, as in the container.
    monkeypatch.chdir(Path(__file__).parent.parent / "pwa")
    import main
    tc = TestClient(main.app)
    for path in ("/", "/app", "/offer", "/privacy"):
        assert tc.get(path).headers["cache-control"] == "no-cache", path
    v = tc.get("/api/version").json()["version"]
    assert len(v) == 12 and v == main.APP_VERSION
