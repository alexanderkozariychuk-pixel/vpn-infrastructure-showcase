"""
Two locations: Germany (entry A, AmneziaWG 1.0) and the Netherlands (entry B,
AmneziaWG 3.x), each its own chain (services/locations.py).

What must hold:
  * the Netherlands exists only when every NL_* setting is present, so a
    portal deployed before its .env is filled in behaves as before;
  * a device's file carries its own location's key, endpoint, MTU and
    obfuscation — and a device whose location is gone gets no file at all
    rather than a wrong one;
  * the plan's limit counts in each location separately;
  * every node operation (add, remove, the free-address lookup) goes to the
    device's own entry, and Germany keeps going through its old helpers;
  * a trial is Germany's only.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api import config as config_api
from db.models import Config, User
from services import locations, provisioner, subscriptions

NL_PARAMS = {
    "Jc": "5", "Jmin": "60", "Jmax": "300",
    "S1": "40", "S2": "77", "S3": "30", "S4": "8",
    "H1": "100000000-100100000", "H2": "200000000-200200000",
    "H3": "300000000-300300000", "H4": "400000000-400400000",
    "I1": "<b 0xc30000000108><r 8><b 0x000044b0><r 1000><r 200>",
}
NL_HOST = "192.0.2.50"
NL_PUB = "TkxOTE5MTkxOTE5MTkxOTE5MTkxOTE5MTkxOTE5MTk="


@pytest.fixture
def nl(monkeypatch):
    monkeypatch.setenv("NL_ENTRY_IP", NL_HOST)
    monkeypatch.setenv("NL_PUBLIC_KEY", NL_PUB)
    monkeypatch.setenv("NL_ENDPOINT", "n2.example.test:8443")
    monkeypatch.setenv("NL_AWG_PARAMS", json.dumps(NL_PARAMS))
    monkeypatch.delenv("NL_MTU", raising=False)


@pytest.fixture
def no_nl(monkeypatch):
    for k in ("NL_ENTRY_IP", "NL_PUBLIC_KEY", "NL_ENDPOINT", "NL_AWG_PARAMS"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def nodes(monkeypatch):
    """Both entries, faked: what each was asked to add and remove."""
    calls = SimpleNamespace(de_add=[], de_remove=[], nl_add=[], nl_remove=[], peers={"de": {}, "nl": {}})
    counter = iter(range(1, 10_000))

    def de_add(pub, psk, ip, name):
        calls.de_add.append(ip)
        calls.peers["de"][pub] = ip
        return True, "ok"

    def de_remove(pub):
        calls.de_remove.append(pub)
        return True, "ok"

    def at_add(host, pub, psk, ip, name):
        assert host == NL_HOST
        calls.nl_add.append(ip)
        calls.peers["nl"][pub] = ip
        return True, "ok"

    def at_remove(host, pub):
        assert host == NL_HOST
        calls.nl_remove.append(pub)
        return True, "ok"

    monkeypatch.setattr(provisioner, "_bridge_used_ips", lambda: set(calls.peers["de"].values()))
    monkeypatch.setattr(provisioner, "_entry_used_ips", lambda host: set(calls.peers["nl"].values()))
    monkeypatch.setattr(provisioner, "_add_peer_to_bridge", de_add)
    monkeypatch.setattr(provisioner, "_add_peer_at", at_add)
    monkeypatch.setattr(provisioner, "_remove_peer_at", at_remove)
    monkeypatch.setattr(provisioner, "_remove_peer_from_bridge", de_remove)
    monkeypatch.setattr(subscriptions, "_remove_peer_from_bridge", de_remove)
    monkeypatch.setattr(config_api, "_remove_peer_from_bridge", de_remove)
    monkeypatch.setattr(provisioner, "_awg_genkey", lambda: f"PRIV{next(counter)}")
    monkeypatch.setattr(provisioner, "_awg_pubkey", lambda priv: "PUB" + priv[4:])
    monkeypatch.setattr(provisioner, "_awg_genpsk", lambda: "PSK")
    return calls


def _subscriber(db, plan="basic-1m", **kw):
    u = User(
        id=str(uuid.uuid4()), username=f"u{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@x.test",
        password_hash="h", plan=plan, is_subscribed=True,
        subscribed_until=datetime.now(timezone.utc) + timedelta(days=30), **kw,
    )
    db.add(u)
    db.run(db.commit())
    return u


def _add(db, user, name, location=None):
    req = config_api.NewConfigRequest(name=name, **({"location": location} if location else {}))
    return db.run(config_api.add_config(req, db, {"sub": user.username}))


# ── the registry ────────────────────────────────────────────────────────────

def test_without_its_settings_the_netherlands_does_not_exist(no_nl):
    assert locations.keys() == ["de"]
    assert locations.get("nl") is None
    assert locations.recommended() == "de"


def test_with_its_settings_the_netherlands_comes_first_and_is_recommended(nl):
    assert locations.keys() == ["nl", "de"]
    assert locations.recommended() == "nl"
    loc = locations.get("nl")
    assert loc.host == NL_HOST and loc.mtu == 1280 and loc.params == NL_PARAMS


@pytest.mark.parametrize("raw", ["", "not json", "[]", "{}", json.dumps({"Jc": "5", "X9": "1"})])
def test_bad_obfuscation_settings_leave_the_netherlands_out(nl, monkeypatch, raw):
    monkeypatch.setenv("NL_AWG_PARAMS", raw)
    assert locations.get("nl") is None


def test_an_unknown_key_reads_as_missing():
    assert locations.get("xx") is None
    assert locations.get(None).key == "de"


# ── the file ────────────────────────────────────────────────────────────────

def test_a_dutch_file_carries_entry_b_and_its_3x_obfuscation(nl):
    text = provisioner._build_conf("PRIV", "PSK", "10.88.88.44", "nl")
    assert f"PublicKey = {NL_PUB}" in text
    assert "Endpoint = n2.example.test:8443" in text
    assert "MTU = 1280" in text
    for k, v in NL_PARAMS.items():
        assert f"{k} = {v}\n" in text
    assert "H1 = 1163059398" not in text


def test_a_german_file_is_what_it_always_was(nl):
    text = provisioner._build_conf("PRIV", "PSK", "10.88.88.44")
    assert "MTU = 1300" in text and f"PublicKey = {provisioner.BRIDGE_PUB}" in text
    for k, v in locations.DE_PARAMS.items():
        assert f"{k} = {v}\n" in text
    assert "S3 =" not in text and "I1 =" not in text


def test_no_file_for_a_device_whose_location_is_gone(no_nl):
    with pytest.raises(ValueError):
        provisioner._build_conf("PRIV", "PSK", "10.88.88.44", "nl")


def test_the_download_of_such_a_device_is_a_503_not_a_wrong_file(db, no_nl):
    user = _subscriber(db)
    c = Config(user_id=user.id, name="nlpho", peer_ip="10.88.88.44", private_key=provisioner._encrypt("P"),
               public_key="PUBX", preshared_key=provisioner._encrypt("S"), location="nl")
    db.add(c)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        db.run(config_api.config_raw(c.id, db, {"sub": user.username}))
    assert e.value.status_code == 503


# ── limits, per location ────────────────────────────────────────────────────

def test_the_plan_limit_holds_in_each_location_separately(db, nl, nodes):
    user = _subscriber(db)                     # basic: 2
    _add(db, user, "de1")
    _add(db, user, "de2")
    with pytest.raises(HTTPException) as e:
        _add(db, user, "de3")
    assert e.value.status_code == 409
    _add(db, user, "nl1", "nl")
    _add(db, user, "nl2", "nl")
    with pytest.raises(HTTPException) as e:
        _add(db, user, "nl3", "nl")
    assert e.value.status_code == 409
    assert len(nodes.de_add) == 2 and len(nodes.nl_add) == 2


def test_a_device_without_a_location_is_german_as_the_app_expects(db, nl, nodes):
    user = _subscriber(db)
    out = _add(db, user, "phone")
    assert out["config"]["location"] == "de" and nodes.de_add and not nodes.nl_add


def test_an_unconfigured_location_is_refused_before_anything_is_issued(db, no_nl, nodes):
    user = _subscriber(db)
    with pytest.raises(HTTPException) as e:
        _add(db, user, "phone", "nl")
    assert e.value.status_code == 422
    assert not nodes.de_add and not nodes.nl_add


def test_the_list_shows_each_location_with_its_own_count(db, nl, nodes):
    user = _subscriber(db, plan="ext-1m")      # extended: 5
    _add(db, user, "de1")
    _add(db, user, "nl1", "nl")
    _add(db, user, "nl2", "nl")
    out = db.run(config_api.list_configs(db, {"sub": user.username}))
    assert [s["key"] for s in out["locations"]] == ["nl", "de"]
    by = {s["key"]: s for s in out["locations"]}
    assert by["nl"] == {"key": "nl", "limit": 5, "used": 2, "recommended": True}
    assert by["de"] == {"key": "de", "limit": 5, "used": 1, "recommended": False}
    # What the Android app reads stays Germany's.
    assert out["limit"] == 5 and out["used"] == 1
    assert sorted(c["location"] for c in out["configs"]) == ["de", "nl", "nl"]


# ── the nodes ───────────────────────────────────────────────────────────────

def test_the_same_address_may_be_held_once_in_each_location(db, nl, nodes):
    user = _subscriber(db)
    a = _add(db, user, "de1")
    b = _add(db, user, "nl1", "nl")
    assert a["config"]["peer_ip"] == b["config"]["peer_ip"] == "10.88.88.42"


def test_deleting_a_dutch_device_removes_it_from_entry_b_only(db, nl, nodes):
    user = _subscriber(db)
    out = _add(db, user, "nl1", "nl")
    db.run(config_api.delete_config(out["config"]["id"], db, {"sub": user.username}))
    assert nodes.nl_remove and not nodes.de_remove


def test_expiry_takes_each_device_off_its_own_entry(db, nl, nodes):
    user = _subscriber(db)
    _add(db, user, "de1")
    _add(db, user, "nl1", "nl")
    user.subscribed_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.run(db.commit())
    stats = db.run(subscriptions.expire_due_subscriptions(db))
    assert stats["users_revoked"] == 1
    assert len(nodes.de_remove) == 1 and len(nodes.nl_remove) == 1


def test_expiry_keeps_a_device_whose_location_is_gone_and_retries(db, nl, nodes, monkeypatch):
    user = _subscriber(db)
    out = _add(db, user, "nl1", "nl")
    monkeypatch.delenv("NL_ENTRY_IP")
    user.subscribed_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.run(db.commit())
    stats = db.run(subscriptions.expire_due_subscriptions(db))
    assert stats["failures"] == 1 and stats["users_revoked"] == 0
    row = db.run(db.get(Config, out["config"]["id"]))
    assert row.is_active is True


def test_a_trial_is_issued_in_germany_whatever_is_asked(db, nl, nodes):
    user = _subscriber(db)
    c = db.run(provisioner.issue_config(user, db, name="trial", kind="trial", location="nl"))
    assert c.location == "de" and c.peer_ip.startswith("10.88.89.")
    assert nodes.de_add and not nodes.nl_add


def test_remove_peer_for_uses_the_callers_german_remover(nl):
    seen = []
    c = SimpleNamespace(location="de", public_key="PUBDE")
    ok, _ = provisioner.remove_peer_for(c, lambda pub: (seen.append(pub) or (True, "ok")))
    assert ok and seen == ["PUBDE"]
