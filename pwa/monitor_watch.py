#!/usr/bin/env python3
"""
The dead man's switch for the monitor: a letter when sov-monitor's reports
stop reaching the portal, another when they come back
(services/monitor_watch.py says how).

Run every five minutes from cron, inside the application container, like the
expiry sweep: infrastructure/portal/pwa-monitor-watch is the cron file,
installed on the portal host as /etc/cron.d/pwa-monitor-watch; it logs to
/var/log/pwa/monitor-watch.log. Exit status 1 only when a letter could not be
sent (it is retried on the next run) or the check could not run at all.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("monitor-watch")


async def main() -> int:
    from db.base import SessionLocal
    from services.monitor_watch import watch

    async with SessionLocal() as db:
        result = await watch(db)
    # Quiet runs leave no line: twelve an hour would bury the ones that matter.
    if result not in ("quiet", "silent"):
        logger.info("monitor watch: %s", result)
    return 1 if result.endswith("-failed") else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception:
        logger.exception("monitor watch could not run")
        sys.exit(1)
