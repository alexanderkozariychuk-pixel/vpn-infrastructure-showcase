"""
api/monitor.py — the health page in the admin panel.

    POST /api/monitor/report   from sov-monitor on the backup host, every 2 min
    GET  /api/admin/monitor    the state in words + the history of problems

The report is not from a person, so it carries no JWT: it is authorised by
MONITOR_TOKEN (in the portal's .env and in a file on the backup host), compared
in constant time. Without that variable the route answers 503 and accepts
nothing. The portal never calls out to the monitor; it only receives.

The backup host decides what is a problem (its limits, two bad runs in a row);
the portal stores its last report, keeps a history of when each problem opened
and closed, and services/monitor_view.py says it in words.
"""
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_admin
from db.base import get_db
from db.models import MonitorEvent, MonitorReport
from services import monitor_view

logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_SIZE = 30
KEEP_DAYS = 90


class Problem(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=300)
    level: Literal["bad", "warn"]
    since: float


class Notice(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=300)
    at: float


class Report(BaseModel):
    sent_at: float
    hosts: dict[str, dict | None] = Field(max_length=20)
    errors: dict[str, str] = {}
    links: dict[str, list[str]] = {}
    clients: dict[str, list[str]] = {}
    web: dict = {}
    problems: list[Problem] = Field(default=[], max_length=200)
    notices: list[Notice] = Field(default=[], max_length=50)


def _authorised(authorization: str | None) -> None:
    token = os.getenv("MONITOR_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="Monitor is not configured")
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="Bad token")


def _ts(value: float, now: datetime) -> datetime:
    """A time from the backup host's clock, never later than ours."""
    try:
        return min(datetime.fromtimestamp(value, timezone.utc), now)
    except (OverflowError, OSError, ValueError):
        return now


@router.post("/api/monitor/report")
async def receive(report: Report, db: AsyncSession = Depends(get_db),
                  authorization: str | None = Header(default=None)):
    _authorised(authorization)
    now = datetime.now(timezone.utc)

    row = await db.get(MonitorReport, 1)
    payload = json.dumps(report.model_dump(), ensure_ascii=False)
    if row is None:
        db.add(MonitorReport(id=1, received_at=now, payload=payload))
    else:
        row.received_at, row.payload = now, payload

    open_rows = (await db.execute(select(MonitorEvent).where(MonitorEvent.ended_at.is_(None)))).scalars().all()
    open_by_key = {e.key: e for e in open_rows}
    current = {p.key: p for p in report.problems}
    for key, p in current.items():
        e = open_by_key.get(key)
        if e is None:
            db.add(MonitorEvent(key=key, level=p.level, text=p.text, started_at=_ts(p.since, now)))
        else:
            e.text, e.level = p.text, p.level
    for key, e in open_by_key.items():
        if key not in current:
            e.ended_at = now

    for n in report.notices:
        at = _ts(n.at, now)
        # A notice the monitor could not hand to Telegram comes again next
        # run; one row is enough.
        seen = (await db.execute(select(MonitorEvent.id).where(
            MonitorEvent.key == n.key, MonitorEvent.started_at >= at - timedelta(minutes=15)))).first()
        if not seen:
            db.add(MonitorEvent(key=n.key, level="info", text=n.text, started_at=at, ended_at=at))

    await db.execute(delete(MonitorEvent).where(
        MonitorEvent.ended_at.is_not(None), MonitorEvent.started_at < now - timedelta(days=KEEP_DAYS)
    ).execution_options(synchronize_session=False))
    await db.commit()
    return {"ok": True, "open": len(current)}


@router.get("/api/admin/monitor")
async def state(db: AsyncSession = Depends(get_db), _: dict = Depends(require_admin)):
    now = datetime.now(timezone.utc)
    row = await db.get(MonitorReport, 1)
    try:
        payload = json.loads(row.payload) if row else None
    except ValueError:
        payload = None
    view = monitor_view.build(payload, row.received_at if row else None, now)
    events = (await db.execute(
        select(MonitorEvent).order_by(MonitorEvent.started_at.desc(), MonitorEvent.id.desc()).limit(HISTORY_SIZE)
    )).scalars().all()
    view["history"] = [monitor_view.describe_event(e, now) for e in events]
    return view
