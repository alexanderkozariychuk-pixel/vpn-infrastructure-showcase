"""
The Android app, served from the portal.

The APK is not part of the repository or the image. A release puts two files
into a directory on the app server that the container mounts read-only
(docker-compose.yml): the APK and a small JSON that describes it. Replacing
them changes what is offered without a deploy, and the app itself never
writes there.

    android.json   {"version_code": 2, "version_name": "1.1",
                    "sha256": "<hex>", "size": <bytes>}
    sovereign.apk

The description is believed only while it matches the file next to it: a
size that differs means a release half-copied, and then nothing is offered
rather than a broken download.

/api/public/android is what the app asks to say «Доступна новая версия»
and what the portal's Android section shows; /download/android is the file.
Both public: the app is free to download, it is the account that is paid.
"""

import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter()

APK_NAME = "sovereign.apk"
META_NAME = "android.json"
APK_MEDIA_TYPE = "application/vnd.android.package-archive"

_VERSION_NAME = re.compile(r"^[0-9][0-9A-Za-z.\-]{0,31}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def downloads_dir() -> Path:
    """Read on every call, so a test can point it elsewhere."""
    return Path(os.getenv("ANDROID_DOWNLOADS_DIR", "/app/downloads"))


def current_release() -> dict | None:
    """
    The release on offer, or None. Every field is checked: this JSON is the
    only thing between a typo in a release script and a customer's phone.
    """
    base = downloads_dir()
    apk, meta = base / APK_NAME, base / META_NAME
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
        size = apk.stat().st_size
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning("Android release unreadable: %s", e)
        return None

    if not isinstance(data, dict):
        return None
    code, name, sha, declared = (data.get(k) for k in ("version_code", "version_name", "sha256", "size"))
    if (
        not isinstance(code, int) or isinstance(code, bool) or code < 1
        or not isinstance(name, str) or not _VERSION_NAME.match(name)
        or not isinstance(sha, str) or not _SHA256.match(sha)
        or not isinstance(declared, int) or declared != size
    ):
        logger.warning("Android release description does not match the APK; nothing offered")
        return None
    return {"version_code": code, "version_name": name, "sha256": sha, "size": size}


@router.get("/api/public/android")
async def android_release():
    release = current_release()
    if release is None:
        return {"available": False}
    return {"available": True, **release, "url": "/download/android"}


@router.get("/download/android")
async def android_download():
    release = current_release()
    if release is None:
        raise HTTPException(status_code=404, detail="Not available")
    return FileResponse(
        downloads_dir() / APK_NAME,
        media_type=APK_MEDIA_TYPE,
        filename=f"sovereign-{release['version_name']}.apk",
        # A new release reuses the URL: the browser must ask each time.
        headers={"Cache-Control": "no-cache"},
    )
