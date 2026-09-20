"""
services/subscriptions.py — when a subscription is active, and what ends it.

Until this module existed, `subscribed_until` was written at payment time and
never read again. Access was gated on the `is_subscribed` boolean alone, and
nothing ever set that boolean back to False — no code anywhere removed a peer
from a node. A subscription therefore never ended: one payment bought
permanent access, and the difference between a one-month and a six-month plan
was decorative.

Two things fix that, and both are needed:

  * `has_active_subscription` — the gate now compares against the clock, so an
    expired account is refused even if the sweep has not run yet.
  * `expire_due_subscriptions` — the sweep, run from cron, which takes the
    peers off the node. Without it the account is locked out of the portal
    while the tunnel keeps carrying traffic.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, Config
from services.provisioner import _remove_peer_from_bridge

logger = logging.getLogger(__name__)


def has_active_subscription(user: User, now: datetime | None = None) -> bool:
    """
    True only when the flag is set *and* the paid period still covers now.

    A missing `subscribed_until` fails closed. Rows can reach that state
    through the admin assign-peer path, and "no end date recorded" must not
    read as "no end date exists" — that is how permanent free access gets
    granted by accident.
    """
    if not user.is_subscribed:
        return False
    if user.subscribed_until is None:
        return False
    return user.subscribed_until > (now or datetime.now(timezone.utc))


async def expire_due_subscriptions(db: AsyncSession, now: datetime | None = None) -> dict:
    """
    Revoke every subscription whose paid period has ended.

    For each expired user: remove each active peer from the entry node through
    the validated wrapper, mark the Config rows inactive, and clear the
    subscription flag.

    The database is only updated for peers the node confirmed it removed. If a
    wrapper call fails, that Config row stays active and the user stays
    subscribed, so the next run tries again — the alternative is a row marked
    revoked while the peer keeps carrying traffic, which is the state nobody
    would think to look for.

    Returns counts for the caller to log. Never raises on a single failure:
    one unreachable node must not stop the rest of the sweep.
    """
    now = now or datetime.now(timezone.utc)

    result = await db.execute(
        select(User).where(
            User.is_subscribed.is_(True),
            User.subscribed_until.is_not(None),
            User.subscribed_until < now,
        )
    )
    due = result.scalars().all()

    stats = {"users_due": len(due), "users_revoked": 0, "peers_removed": 0, "failures": 0}

    for user in due:
        configs = (
            await db.execute(
                select(Config).where(
                    Config.user_id == user.id,
                    Config.is_active.is_(True),
                )
            )
        ).scalars().all()

        all_removed = True
        for config in configs:
            # SSH is blocking; keep it off the event loop so this behaves the
            # same way when called from a request as it does from cron.
            ok, reason = await asyncio.get_event_loop().run_in_executor(
                None, _remove_peer_from_bridge, config.public_key
            )
            if ok:
                config.is_active = False
                stats["peers_removed"] += 1
            else:
                all_removed = False
                stats["failures"] += 1
                logger.error(
                    "Could not revoke peer %s for %s: %s",
                    config.peer_ip, user.username, reason,
                )

        if all_removed:
            user.is_subscribed = False
            stats["users_revoked"] += 1
            logger.info(
                "Subscription expired for %s (%d peers removed)",
                user.username, len(configs),
            )

    await db.commit()

    # Flagged rather than revoked: an active flag with no end date is a data
    # problem, not an expiry. Revoking on a guess would cut off a paying
    # customer; leaving it silent is how the original bug survived.
    undated = (
        await db.execute(
            select(User).where(
                User.is_subscribed.is_(True),
                User.subscribed_until.is_(None),
            )
        )
    ).scalars().all()
    if undated:
        stats["undated"] = [u.username for u in undated]
        logger.warning(
            "%d subscribed users have no end date and were not touched: %s",
            len(undated), ", ".join(u.username for u in undated),
        )

    return stats
