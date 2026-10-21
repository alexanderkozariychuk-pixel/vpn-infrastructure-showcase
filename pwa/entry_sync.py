#!/usr/bin/env python3
"""
Runs the jobs owed to the standby entry, then checks the backlog
(services/entry_sync.py says how).

From cron every minute, inside the application container, like the expiry
sweep: infrastructure/portal/pwa-entry-sync is the cron file, installed on the
portal host as /etc/cron.d/pwa-entry-sync; it logs to
/var/log/pwa/entry-sync.log. With ENTRY_B_IP unset it does nothing.

Exit status 1 when the standby could not be reached, a job was refused, a
letter could not be sent, or the run failed as a whole — all retried next run.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("entry-sync")


async def main() -> int:
    from db.base import SessionLocal
    from services import entry_sync

    if not entry_sync.standby_entries():
        return 0
    async with SessionLocal() as db:
        stats = await entry_sync.run(db)
        watched = await entry_sync.watch(db)
    # Quiet runs leave no line: sixty an hour would bury the ones that matter.
    if stats["done"] or stats["skipped"] or stats["failed"] or stats["unreachable"]:
        logger.info("entry sync: %s", stats)
    if watched not in ("quiet", "stale", "off"):
        logger.info("entry sync watch: %s", watched)
    failed = stats["failed"] or stats["unreachable"] or watched.endswith("-failed")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        logger.exception("entry sync could not run")
        sys.exit(1)
