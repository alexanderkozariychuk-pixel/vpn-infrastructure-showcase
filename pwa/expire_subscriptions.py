#!/usr/bin/env python3
"""
Sweep expired subscriptions. Run from cron, inside the application container:

    0 * * * * docker compose -f /opt/pwa/<app>/docker-compose.yml \
        exec -T pwa python expire_subscriptions.py >> /var/log/pwa-expiry.log 2>&1

Hourly rather than daily on purpose: a day's granularity means a subscription
that ends at 09:00 keeps carrying traffic until midnight, and six of those a
month is a free week nobody agreed to give away.

Runs inside the container because that is where the provisioner's SSH key is
mounted and where DATABASE_URL points at the right host. Exit status is 0 when
the sweep completed — including when it found nothing to do — and 1 when it
could not run at all, so cron mail means something went wrong rather than
arriving every hour.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("expiry")


async def main() -> int:
    from db.base import SessionLocal
    from services.subscriptions import expire_due_subscriptions

    started = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        stats = await expire_due_subscriptions(db)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info(
        "sweep finished in %.1fs: %d due, %d revoked, %d peers removed, %d failures",
        elapsed,
        stats["users_due"],
        stats["users_revoked"],
        stats["peers_removed"],
        stats["failures"],
    )

    # A failure here is not a reason to exit non-zero: the row stays active and
    # the next hourly run retries. The log line above is the signal, and an
    # alert on it belongs in Alertmanager, not in this script's exit status.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        logger.exception("sweep could not run")
        sys.exit(1)
