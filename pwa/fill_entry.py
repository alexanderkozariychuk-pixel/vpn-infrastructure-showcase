#!/usr/bin/env python3
"""
Owe a standby entry every active portal peer it does not have yet
(services/entry_sync.fill). Run once when a standby is first connected, and
whenever tools/peer_reconcile.py shows it missing portal peers.

    docker compose exec -T pwa python fill_entry.py --entry b --dry-run
    docker compose exec -T pwa python fill_entry.py --entry b

Without --dry-run it writes the jobs; pwa/entry_sync.py (cron) carries them
out within a minute. It never removes anything: peers on the entry that the
database does not know are listed for a person to decide (runbook §9).
Prints addresses and the first 8 characters of each key, nothing secret.
"""

import argparse
import asyncio
import sys


async def main(entry: str, dry_run: bool) -> int:
    from db.base import SessionLocal
    from services import entry_sync

    async with SessionLocal() as db:
        r = await entry_sync.fill(db, entry, dry_run=dry_run)
    print(f"entry {r['entry']}: {r['on_entry']} peers on the node, "
          f"{r['active_in_db']} active in the database, {r['already_pending']} already pending")
    print(f"to add: {len(r['to_add'])}" + (" (dry run, nothing written)" if dry_run else " (jobs written)"))
    for line in r["to_add"]:
        print(f"  + {line}")
    for title, key in (("address differs", "address_differs"), ("on the node, not in the database", "unknown_on_entry")):
        if r[key]:
            print(f"{title}: {len(r[key])}")
            for line in r[key]:
                print(f"  ? {line}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--entry", required=True, choices=["b"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.entry, args.dry_run)))
