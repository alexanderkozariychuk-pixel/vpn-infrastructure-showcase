"""
The APK on the portal: offered only while its description matches the file.

The description is written by a release script and the file is copied next
to it; a half-finished copy or a typo must end in "nothing offered", never in
a download the phone refuses or an update banner that leads nowhere.
"""

import hashlib
import json

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import android

PWA = Path(__file__).resolve().parents[1] / "pwa"

APK = b"PK\x03\x04 not really an apk, but bytes with a hash"


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_DOWNLOADS_DIR", str(tmp_path))
    return tmp_path


def _release(base, **over):
    (base / android.APK_NAME).write_bytes(APK)
    meta = {"version_code": 2, "version_name": "1.1",
            "sha256": hashlib.sha256(APK).hexdigest(), "size": len(APK)}
    meta.update(over)
    (base / android.META_NAME).write_text(json.dumps(meta), encoding="utf-8")
    return meta


@pytest.fixture
def client():
    # The router alone: main.py needs the whole environment to import.
    app = FastAPI()
    app.include_router(android.router)
    return TestClient(app)


def test_the_portal_serves_the_router():
    assert "app.include_router(android_router)" in (PWA / "main.py").read_text()


def test_nothing_put_there_offers_nothing(downloads, client):
    assert client.get("/api/public/android").json() == {"available": False}
    assert client.get("/download/android").status_code == 404


def test_a_release_is_described_and_downloadable(downloads, client):
    meta = _release(downloads)
    r = client.get("/api/public/android")
    assert r.status_code == 200
    assert r.json() == {"available": True, **meta, "url": "/download/android"}

    d = client.get("/download/android")
    assert d.status_code == 200
    assert d.content == APK
    assert d.headers["content-type"] == "application/vnd.android.package-archive"
    assert 'filename="sovereign-1.1.apk"' in d.headers["content-disposition"]
    assert d.headers["cache-control"] == "no-cache"


def test_no_token_is_needed(downloads, client):
    # The app asks before anyone signs in, and the site links it for strangers.
    _release(downloads)
    assert client.get("/api/public/android", headers={"Authorization": "Bearer nonsense"}).status_code == 200


@pytest.mark.parametrize("over", [
    {"size": len(APK) + 1},          # copy not finished, or the wrong file
    {"version_code": 0},
    {"version_code": "2"},
    {"version_code": True},
    {"version_name": ""},
    {"version_name": "1.1<script>"},
    {"sha256": "abc"},
    {"sha256": "A" * 64},
])
def test_a_description_that_does_not_hold_offers_nothing(downloads, client, over):
    _release(downloads, **over)
    assert client.get("/api/public/android").json() == {"available": False}
    assert client.get("/download/android").status_code == 404


def test_a_description_without_its_apk_offers_nothing(downloads, client):
    _release(downloads)
    (downloads / android.APK_NAME).unlink()
    assert client.get("/api/public/android").json() == {"available": False}


def test_an_unreadable_description_offers_nothing(downloads, client):
    _release(downloads)
    (downloads / android.META_NAME).write_text("{not json", encoding="utf-8")
    assert client.get("/api/public/android").json() == {"available": False}
    (downloads / android.META_NAME).write_text("[1, 2]", encoding="utf-8")
    assert client.get("/api/public/android").json() == {"available": False}


def test_the_container_mounts_the_downloads_read_only():
    compose = (PWA / "docker-compose.yml").read_text()
    assert "/opt/pwa/downloads:/app/downloads:ro" in compose
