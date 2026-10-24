"""
The admin's peer list per location: Germany through the old Bridge helper,
the Netherlands through its own entry's address, an unknown location refused.
"""
import base64
import json
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")

from api import clients  # noqa: E402
from services import net_manager  # noqa: E402
from services.net_manager import PeerStatus  # noqa: E402

ADMIN = {"sub": "admin", "role": "admin"}
NL_HOST = "192.0.2.50"


def _key(n):
    return base64.b64encode(bytes([n]) * 32).decode()


@pytest.fixture
def nl(monkeypatch):
    monkeypatch.setenv("NL_ENTRY_IP", NL_HOST)
    monkeypatch.setenv("NL_PUBLIC_KEY", _key(9))
    monkeypatch.setenv("NL_ENDPOINT", "n2.example.test:8443")
    monkeypatch.setenv("NL_AWG_PARAMS", json.dumps({"Jc": "5", "S1": "40"}))


@pytest.fixture
def entries(monkeypatch):
    asked = []
    monkeypatch.setattr(clients, "get_bridge_status_data",
                        lambda: (asked.append("de") or [PeerStatus(_key(1), allowed_ips="10.88.88.60/32")], None))
    monkeypatch.setattr(clients, "get_entry_status_data",
                        lambda host: (asked.append(host) or [PeerStatus(_key(2), allowed_ips="10.88.88.42/32")], None))
    return asked


def test_germany_is_read_from_bridge_as_before(db, nl, entries):
    out = db.run(clients.get_clients(ADMIN, db))
    assert entries == ["de"] and out["location"] == "de"
    assert out["locations"] == ["nl", "de"]
    assert [c["number"] for c in out["clients"]] == ["60"]


def test_the_netherlands_is_read_from_its_own_entry(db, nl, entries):
    out = db.run(clients.get_clients(ADMIN, db, location="nl"))
    assert entries == [NL_HOST] and out["location"] == "nl"
    assert [c["number"] for c in out["clients"]] == ["42"]


def test_an_unknown_or_unconfigured_location_is_refused(db, entries, monkeypatch):
    monkeypatch.delenv("NL_ENTRY_IP", raising=False)
    with pytest.raises(HTTPException) as e:
        db.run(clients.get_clients(ADMIN, db, location="nl"))
    assert e.value.status_code == 422 and entries == []


def test_the_entry_listing_goes_to_the_given_host(monkeypatch):
    seen = []
    monkeypatch.setattr(net_manager, "_ssh_bridge",
                        lambda cmd, *a, **k: (seen.append(k.get("host")) or ("interface: awg0\n", "")))
    net_manager.get_entry_status_data(NL_HOST)
    net_manager.get_bridge_status_data()
    assert seen == [NL_HOST, None]
