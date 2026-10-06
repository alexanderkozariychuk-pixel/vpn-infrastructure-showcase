"""
api/trial.py — starting the free trial.

The rules and the reasons for them are in services/trial.py. Every refusal
carries a fixed code in `detail`, which the portal turns into a sentence:

    403 trial_off            trials are switched off (TRIAL_ENABLED)
    403 email_not_verified   confirm the address first
    403 trial_unavailable    throwaway-mailbox domain
    409 trial_active         already running
    409 trial_used           this account, or this mailbox, has had one,
                             or the account has already paid
    429                      too many from this address (Retry-After)
    503 trial_busy           today's ceiling reached, or no device could
                             be issued — try later
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.jwt import require_auth
from db.base import get_db
from db.models import TrialGrant, User
from services import ratelimit
from services.net import resolve_source_ip
from services import provisioner
from services.trial import (
    TRIAL_DAILY_CAP, TRIAL_DAYS, is_disposable, normalise_email, trial_active, trial_enabled, trial_end,
)
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/public/trial")
async def trial_offer():
    """Whether to show the trial on the landing page, and for how long."""
    return {"enabled": trial_enabled(), "days": TRIAL_DAYS}


@router.post("/api/client/trial", status_code=201)
async def start_trial(
    request: Request,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(require_auth),
):
    user = (await db.execute(select(User).where(User.username == payload.get("sub")))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not trial_enabled():
        raise HTTPException(status_code=403, detail="trial_off")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="email_not_verified")
    if trial_active(user):
        raise HTTPException(status_code=409, detail="trial_active")
    # Anyone who has had a paid period (subscribed_until is written by every
    # activation and by the admin grant) is past the point a trial is for.
    if user.trial_until is not None or user.subscribed_until is not None:
        raise HTTPException(status_code=409, detail="trial_used")
    if is_disposable(user.email):
        raise HTTPException(status_code=403, detail="trial_unavailable")

    ip = resolve_source_ip(request)
    ratelimit.take(ratelimit.TRIAL_PER_IP, ip)

    norm = normalise_email(user.email)
    if (await db.execute(select(TrialGrant.id).where(TrialGrant.email_norm == norm))).first():
        raise HTTPException(status_code=409, detail="trial_used")

    since = datetime.now(timezone.utc) - timedelta(days=1)
    today = (await db.execute(
        select(func.count()).select_from(TrialGrant).where(TrialGrant.granted_at >= since)
    )).scalar_one()
    if today >= TRIAL_DAILY_CAP:
        logger.warning("Trial daily ceiling reached (%d); refused %s", today, user.username)
        raise HTTPException(status_code=503, detail="trial_busy")

    # The grant is written before the peer exists. Its unique constraints are
    # what turn two simultaneous requests — same account, or two accounts on
    # one mailbox — into one trial: the second insert fails here, before any
    # device is issued.
    user.trial_until = trial_end()
    db.add(TrialGrant(email_norm=norm, user_id=user.id, source_ip=ip[:64] or None))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="trial_used")

    config = await provisioner.issue_config(user, db, name="trial", kind="trial")
    if config is None:
        # Nothing on the node, so nothing is kept: the grant goes too, and the
        # customer can try again rather than having spent their trial.
        await db.rollback()
        raise HTTPException(status_code=503, detail="trial_busy")

    await db.commit()
    logger.info("Trial started for %s until %s (%s)", user.username, user.trial_until, config.peer_ip)
    return {
        "ok": True,
        "trial_until": user.trial_until,
        "config": {"id": config.id, "name": config.name, "peer_ip": config.peer_ip, "kind": config.kind},
    }
