"""
Devices on an account: adding within the plan's limit, and renaming.

The portal now lets customers do both, so the rules the server enforces are
the ones that matter — the page only offers what these allow. Against a real
in-memory database; `issue_config` is stubbed because it talks to a node.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api import config as config_api
from db.models import Config, User
from services import provisioner


def _config(user, name, active=True):
    return Config(
        id=str(uuid.uuid4()), user_id=user.id, name=name,
        peer_ip=f"10.88.88.{uuid.uuid4().int % 200 + 10}",
        private_key="x", public_key=str(uuid.uuid4()), preshared_key="z", is_active=active,
    )


@pytest.fixture
def account(db, monkeypatch):
    """A subscribed basic-plan user (limit 2) holding the auto-issued first device."""
    issued = []

    async def _fake_issue(user, session, name="device", location="de"):
        c = _config(user, name)
        c.location = location
        session.add(c)
        await session.flush()
        issued.append(name)
        return c

    monkeypatch.setattr(config_api, "issue_config", _fake_issue)
    monkeypatch.setattr(provisioner, "issue_config", _fake_issue)

    user = User(
        id=str(uuid.uuid4()), username="test1", email="t@x.test", password_hash="h",
        plan="basic-1m", is_subscribed=True,
        subscribed_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    first = _config(user, "device-1")
    db.add(user)
    db.add(first)
    db.run(db.commit())
    return db, user, first, issued


def _payload(user):
    return {"sub": user.username}


# ── adding ───────────────────────────────────────────────────────────────────

def test_a_device_can_be_added_while_the_plan_has_room(account):
    db, user, first, issued = account
    out = db.run(config_api.add_config(config_api.NewConfigRequest(name="phone"), db, _payload(user)))
    assert out["used"] == 2 and out["limit"] == 2
    assert out["config"]["name"] == "phone"
    assert issued == ["phone"]


def test_a_device_past_the_plan_limit_is_refused_and_nothing_is_issued(account):
    db, user, first, issued = account
    db.run(config_api.add_config(config_api.NewConfigRequest(name="phone"), db, _payload(user)))
    with pytest.raises(HTTPException) as e:
        db.run(config_api.add_config(config_api.NewConfigRequest(name="laptop"), db, _payload(user)))
    assert e.value.status_code == 409
    assert issued == ["phone"], "a peer was issued past the limit"


# ── renaming ─────────────────────────────────────────────────────────────────

def test_the_auto_issued_device_can_be_given_its_own_name(account):
    db, user, first, _ = account
    keys_before = (first.public_key, first.peer_ip)

    out = db.run(config_api.rename_config(first.id, config_api.RenameConfigRequest(name=" mama "), db, _payload(user)))

    db.run(db.refresh(first))
    assert out["config"]["name"] == "mama" and first.name == "mama"
    assert (first.public_key, first.peer_ip) == keys_before, "renaming must not touch the tunnel"


def test_someone_elses_device_cannot_be_renamed_and_reads_as_missing(account):
    db, user, first, _ = account
    other = User(id=str(uuid.uuid4()), username="other", email="o@x.test", password_hash="h")
    theirs = _config(other, "theirs")
    db.add(other)
    db.add(theirs)
    db.run(db.commit())

    with pytest.raises(HTTPException) as e:
        db.run(config_api.rename_config(theirs.id, config_api.RenameConfigRequest(name="mine"), db, _payload(user)))
    assert e.value.status_code == 404
    db.run(db.refresh(theirs))
    assert theirs.name == "theirs"


def test_a_removed_device_cannot_be_renamed(account):
    db, user, first, _ = account
    gone = _config(user, "old", active=False)
    db.add(gone)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        db.run(config_api.rename_config(gone.id, config_api.RenameConfigRequest(name="new"), db, _payload(user)))
    assert e.value.status_code == 404


def test_a_blank_name_is_refused(account):
    db, user, first, _ = account
    with pytest.raises(HTTPException) as e:
        db.run(config_api.rename_config(first.id, config_api.RenameConfigRequest(name="   "), db, _payload(user)))
    assert e.value.status_code == 422
    db.run(db.refresh(first))
    assert first.name == "device-1"


def test_a_name_longer_than_six_is_refused_before_the_handler_runs():
    with pytest.raises(ValidationError):
        config_api.RenameConfigRequest(name="laptop1")
    with pytest.raises(ValidationError):
        config_api.RenameConfigRequest(name="")


# ── removing ─────────────────────────────────────────────────────────────────
#
# The portal's device list now has a delete button; until then only the
# Android app called this. What the customer relies on: the slot is freed
# only when the node confirmed the peer is gone, and no one else's device can
# be touched.

@pytest.fixture
def node(monkeypatch):
    """The entry node: records removals; .ok = False makes it refuse."""
    class Node:
        ok = True
        removed: list = []
    n = Node()
    n.removed = []

    def _remove(public_key):
        if not n.ok:
            return False, "node unreachable"
        n.removed.append(public_key)
        return True, ""

    monkeypatch.setattr(config_api, "_remove_peer_from_bridge", _remove)
    return n


def test_removing_a_device_frees_its_slot(account, node):
    db, user, first, issued = account
    second = db.run(config_api.add_config(config_api.NewConfigRequest(name="phone"), db, _payload(user)))
    db.run(config_api.delete_config(first.id, db, _payload(user)))
    db.run(db.refresh(first))
    assert first.is_active is False and node.removed == [first.public_key]
    listed = db.run(config_api.list_configs(db, _payload(user)))
    assert [c["id"] for c in listed["configs"]] == [second["config"]["id"]]
    # The freed slot can be filled again.
    db.run(config_api.add_config(config_api.NewConfigRequest(name="laptop"), db, _payload(user)))
    assert issued == ["phone", "laptop"]


def test_a_device_the_node_did_not_remove_keeps_its_slot(account, node):
    """Freeing the slot on an unconfirmed removal would trade one working
    tunnel for another and keep both."""
    db, user, first, _ = account
    node.ok = False
    with pytest.raises(HTTPException) as e:
        db.run(config_api.delete_config(first.id, db, _payload(user)))
    assert e.value.status_code == 503
    db.run(db.refresh(first))
    assert first.is_active is True


def test_someone_elses_device_reads_as_missing(account, node):
    db, user, first, _ = account
    other = User(id=str(uuid.uuid4()), username="test2", email="o@x.test", password_hash="h",
                 plan="basic-1m", is_subscribed=True,
                 subscribed_until=datetime.now(timezone.utc) + timedelta(days=30))
    db.add(other)
    db.run(db.commit())
    with pytest.raises(HTTPException) as e:
        db.run(config_api.delete_config(first.id, db, _payload(other)))
    assert e.value.status_code == 404 and node.removed == []
    db.run(db.refresh(first))
    assert first.is_active is True


def test_the_accounts_address_moves_to_a_device_that_remains(account, node):
    db, user, first, _ = account
    user.peer_ip = first.peer_ip
    db.run(db.commit())
    second = db.run(config_api.add_config(config_api.NewConfigRequest(name="phone"), db, _payload(user)))
    db.run(config_api.delete_config(first.id, db, _payload(user)))
    db.run(db.refresh(user))
    assert user.peer_ip == second["config"]["peer_ip"]
