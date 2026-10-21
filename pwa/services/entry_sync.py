"""
services/entry_sync.py — keeping the standby entry's peers in step with the
primary's.

Clients reach the VPN through `n1.sov3r3ign.com`. If entry A is blocked, the
name is pointed at entry B, and B has to know every portal peer by then:
it accepts only keys on its own list and drops the rest without a word. So
each portal peer added to or removed from A is owed to B as well — removals
just as much as additions, or a customer whose period ended keeps working
through B after a switch.

How:
  * A is written in the request, synchronously, exactly as before this
    module existed. Nothing here talks to A, and nothing here runs in a
    request.
  * The same transaction that activates or ends a Config row writes a job
    for each standby entry (`enqueue`). A rolled-back request leaves no job;
    a committed change cannot lose its job.
  * pwa/entry_sync.py, from cron every minute, runs the jobs in the order
    they were written (`run`), so a removal reaches B before a later device
    takes over its address.
  * A job older than STALE_AFTER is a letter, once, and a line in the admin
    panel's history; another letter when the backlog has cleared (`watch`).

The wrappers on the node are not idempotent: adding a key that is already
there answers "peer exists (key)", removing one that is gone answers "peer
not found". A job is retried when the first attempt's answer was lost — the
SSH connection dropped after the node had done the work — so for B those two
answers mean the job is done. tools/peer_reconcile.py checks the result.

Addresses: B holds portal peers only, so what is taken on B is what the
database holds as active, plus whatever pending jobs still have to undo
there. `pending_ips` gives the second half to the address search
(provisioner._find_free_ip) — no question to B in the request path.

With ENTRY_B_IP unset there are no standby entries: `enqueue` writes nothing,
`run` and `watch` do nothing, and the portal behaves exactly as before.
"""
import asyncio
import logging
import os
import shlex
import subprocess
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Config, EntrySync, MonitorEvent, User

logger = logging.getLogger(__name__)

# A job this old means B no longer has the same peers as A.
STALE_AFTER = timedelta(hours=1)
# The admin history row for that; "portal:" keys are not closed by the
# monitor's reports (api/monitor.py).
STALE_KEY = "portal:entry-sync"

# The wrapper's own words for "already the way the job wants it".
_ADD_ALREADY = "peer exists (key)"
_REMOVE_ALREADY = "peer not found"


def standby_entries() -> dict[str, str]:
    """Standby entries by name → address. Read at call time, not import."""
    b = os.getenv("ENTRY_B_IP", "").strip()
    return {"b": b} if b else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── writing jobs ───────────────────────────────────────────────────────

def enqueue(db: AsyncSession, config: Config, action: str) -> int:
    """
    Owe `action` ("add" or "remove") for this config to every standby entry.

    Only adds to the session: the caller's commit is what makes the job real,
    together with the Config change it follows. Returns the number of jobs.
    """
    if action not in ("add", "remove"):
        raise ValueError(f"unknown action {action!r}")
    if not config.id:
        raise ValueError("config has no id yet")
    entries = standby_entries()
    for name in entries:
        db.add(EntrySync(entry=name, action=action, config_id=config.id,
                         public_key=config.public_key, peer_ip=config.peer_ip,
                         created_at=_now()))
    return len(entries)


async def pending_ips(db: AsyncSession) -> set[str]:
    """Addresses a pending job still holds on some standby entry."""
    rows = await db.execute(select(EntrySync.peer_ip).where(EntrySync.done_at.is_(None)))
    return {r[0] for r in rows.fetchall() if r[0]}


# ── talking to a standby entry ─────────────────────────────────────────

class Unreachable(Exception):
    """The entry could not be reached at all: stop this run for it."""


def _ssh(host: str, cmd: str, timeout: int = 15) -> tuple[str, str]:
    """
    One wrapper call on a standby entry, as pwa-provisioner, with the same key
    and known_hosts as entry A (services/provisioner.py). Raises Unreachable
    when ssh itself failed (exit 255) or timed out.
    """
    from services import provisioner as p
    try:
        r = subprocess.run(
            ["ssh", "-i", p.PWA_SSH_KEY,
             "-o", "StrictHostKeyChecking=yes",
             "-o", f"UserKnownHostsFile={p.PWA_SSH_DIR}/known_hosts",
             "-o", "UpdateHostKeys=no",
             "-o", "ConnectTimeout=5",
             "-o", "BatchMode=yes",
             f"{p.PWA_SSH_USER}@{host}", cmd],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise Unreachable(f"timeout after {timeout} s") from e
    if r.returncode == 255:
        raise Unreachable((r.stderr or "ssh failed").strip()[:200])
    return r.stdout.strip(), r.stderr.strip()


def _client_name(config: Config, user: User) -> str:
    # The same label provisioner.issue_config gives the peer on A.
    return (f"trial-{user.username}" if config.kind == "trial" else f"auto-{user.username}")[:32]


def _add(host: str, config: Config, user: User) -> tuple[bool, str]:
    from services.provisioner import _decrypt
    args = " ".join(shlex.quote(a) for a in (
        config.public_key, _decrypt(config.preshared_key),
        f"{config.peer_ip}/32", _client_name(config, user)))
    out, err = _ssh(host, f"sudo pwa-add-peer {args}")
    said = (out + " " + err).strip()
    if out.startswith("ok:"):
        return True, "ok"
    if _ADD_ALREADY in said:
        return True, "already there"
    return False, said


def _remove(host: str, public_key: str) -> tuple[bool, str]:
    out, err = _ssh(host, f"sudo pwa-del-peer {shlex.quote(public_key)}")
    said = (out + " " + err).strip()
    if out.startswith("ok:"):
        return True, "ok"
    if _REMOVE_ALREADY in said:
        return True, "already gone"
    return False, said


def peers_on(host: str) -> dict[str, str]:
    """The entry's awg0 peers: public key → first allowed address."""
    out, err = _ssh(host, "sudo pwa-awg-show awg0 allowed-ips")
    if not out and err:
        raise RuntimeError(f"pwa-awg-show: {err[:200]}")
    peers = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            peers[parts[0]] = parts[1].split(",")[0].split("/")[0]
    return peers


# ── filling a new standby ──────────────────────────────────────────────

async def fill(db: AsyncSession, name: str, dry_run: bool = True) -> dict:
    """
    Owe a standby entry every active portal peer it does not have yet.

    For a new standby, or one that missed changes made before ENTRY_B_IP was
    set. Reads the entry's peers once, then writes an "add" job for each
    active Config whose key is not there and has no pending job; the jobs run
    like any other (`run`). Removes nothing: a peer on the entry the database
    does not know is reported, and a person decides (runbook §9).
    """
    host = standby_entries().get(name)
    if not host:
        raise ValueError(f"entry {name!r} is not a configured standby (ENTRY_B_IP)")
    on_entry = await asyncio.get_event_loop().run_in_executor(None, peers_on, host)
    active = (await db.execute(
        select(Config, User).join(User, User.id == Config.user_id)
        .where(Config.is_active.is_(True)).order_by(Config.peer_ip))).all()
    pending = {r[0] for r in (await db.execute(
        select(EntrySync.config_id).where(EntrySync.entry == name, EntrySync.done_at.is_(None)))).fetchall()}

    missing = [(c, u) for c, u in active if c.public_key not in on_entry and c.id not in pending]
    known = {c.public_key for c, _ in active}
    mismatched = [(c, on_entry[c.public_key]) for c, _ in active
                  if c.public_key in on_entry and on_entry[c.public_key] != c.peer_ip]
    report = {
        "entry": name,
        "on_entry": len(on_entry),
        "active_in_db": len(active),
        "already_pending": sum(1 for c, _ in active if c.id in pending),
        "to_add": [f"{c.peer_ip} {c.public_key[:8]} {c.kind} {u.username}" for c, u in missing],
        "address_differs": [f"{c.public_key[:8]} db {c.peer_ip} entry {ip}" for c, ip in mismatched],
        "unknown_on_entry": sorted(f"{ip} {k[:8]}" for k, ip in on_entry.items() if k not in known),
    }
    if not dry_run:
        for c, _ in missing:
            db.add(EntrySync(entry=name, action="add", config_id=c.id, public_key=c.public_key,
                             peer_ip=c.peer_ip, created_at=_now()))
        await db.commit()
    return report


# ── running jobs ───────────────────────────────────────────────────────

async def run(db: AsyncSession, now: datetime | None = None) -> dict:
    """
    One pass over the pending jobs, oldest first, entry by entry. An entry
    that cannot be reached is left for the next run; one that refuses a job
    moves on to the next job, so one bad row does not hold the rest back.
    """
    now = now or _now()
    stats = {"done": 0, "skipped": 0, "failed": 0, "unreachable": []}
    entries = standby_entries()
    if not entries:
        return stats
    loop = asyncio.get_event_loop()

    for name, host in entries.items():
        jobs = (await db.execute(
            select(EntrySync).where(EntrySync.entry == name, EntrySync.done_at.is_(None))
            .order_by(EntrySync.id)
        )).scalars().all()
        for job in jobs:
            if job.done_at is not None:     # closed by an earlier job in this pass
                continue
            row = (await db.execute(
                select(Config, User).join(User, User.id == Config.user_id)
                .where(Config.id == job.config_id))).first()
            config, user = row if row else (None, None)

            if job.action == "add" and (config is None or not config.is_active):
                # Ended before B ever heard of it. If no attempt was made, the
                # peer was never on B: close the matching removal too. If one
                # was (its answer may have been lost), let the removal run.
                job.done_at, job.last_error = now, "skipped: config no longer active"
                stats["skipped"] += 1
                if job.attempts == 0:
                    for other in jobs:
                        if (other.done_at is None and other.action == "remove"
                                and other.config_id == job.config_id and other.id > job.id):
                            other.done_at, other.last_error = now, "skipped: never added"
                            stats["skipped"] += 1
                await db.commit()
                continue

            job.attempts += 1
            try:
                if job.action == "add":
                    ok, said = await loop.run_in_executor(None, _add, host, config, user)
                else:
                    ok, said = await loop.run_in_executor(None, _remove, host, job.public_key)
            except Unreachable as e:
                job.last_error = f"unreachable: {e}"[:300]
                await db.commit()
                stats["unreachable"].append(name)
                logger.warning("entry %s unreachable, %d job(s) wait: %s",
                               name, sum(1 for j in jobs if j.done_at is None), e)
                break
            except Exception as e:  # never let one job stop the sweep
                ok, said = False, f"{type(e).__name__}: {e}"

            if ok:
                job.done_at, job.last_error = now, None if said == "ok" else said
                stats["done"] += 1
                logger.info("entry %s: %s %s (%s) — %s", name, job.action,
                            job.peer_ip, job.public_key[:8], said)
            else:
                job.last_error = said[:300]
                stats["failed"] += 1
                logger.error("entry %s refused %s %s (%s): %s", name, job.action,
                             job.peer_ip, job.public_key[:8], said)
            await db.commit()
    return stats


# ── the backlog, for people ────────────────────────────────────────────

async def backlog(db: AsyncSession, now: datetime | None = None) -> dict:
    """Pending jobs per entry: count, oldest, last error — for the admin panel."""
    now = now or _now()
    out = {}
    for name in standby_entries():
        jobs = (await db.execute(
            select(EntrySync).where(EntrySync.entry == name, EntrySync.done_at.is_(None))
            .order_by(EntrySync.id))).scalars().all()
        oldest = _aware(jobs[0].created_at) if jobs else None
        out[name] = {
            "pending": len(jobs),
            "oldest_s": int((now - oldest).total_seconds()) if oldest else None,
            "stale": sum(1 for j in jobs if now - _aware(j.created_at) > STALE_AFTER),
            "last_error": next((j.last_error for j in reversed(jobs) if j.last_error), None),
        }
    return out


def _letter(subject: str, lines: list[str]) -> tuple[str, str, str]:
    return subject, "".join(f"<p>{escape(x)}</p>" for x in lines), "\n".join(lines)


async def watch(db: AsyncSession, now: datetime | None = None) -> str:
    """
    A letter when jobs have waited longer than STALE_AFTER, one when they
    have cleared. State is one MonitorEvent row (STALE_KEY), opened only after
    the alert went out and closed only after the all-clear did, so a letter
    that failed is tried again on the next run. Returns what it did.
    """
    from services import mailer
    from services.monitor_watch import alert_address
    from services.monitor_view import duration

    now = now or _now()
    if not standby_entries():
        return "off"
    stale = {n: b for n, b in (await backlog(db, now)).items() if b["stale"]}
    open_event = (await db.execute(select(MonitorEvent).where(
        MonitorEvent.key == STALE_KEY, MonitorEvent.ended_at.is_(None)))).scalars().first()

    if stale:
        if open_event is not None:
            return "stale"
        count = sum(b["stale"] for b in stale.values())
        names = ", ".join(name.upper() for name in stale)
        oldest = max(b["oldest_s"] for b in stale.values())
        err = next((b["last_error"] for b in stale.values() if b["last_error"]), "нет")
        subject, html, text = _letter(
            f"Sovereign: резервный вход {names} отстаёт",
            [(f"На резервный вход {names} не дошли изменения пиров: {count} шт., "
              f"самое старое ждёт {duration(oldest)}."),
             ("Пока они не дошли, набор пиров на B не совпадает с A: при переключении "
              "кто-то не подключится, а у кого-то, чей доступ закончился, туннель будет работать."),
             f"Последняя ошибка: {err}",
             ("Что проверить: доступен ли B по SSH с портала, лог /var/log/pwa/entry-sync.log, "
              "раздел «Состояние» в админке."),
             "Когда очередь разойдётся, придёт письмо «резервный вход догнал»."])
        if not await mailer.send_email(alert_address(), subject, html, text):
            return "alert-failed"
        db.add(MonitorEvent(key=STALE_KEY, level="bad",
                            text=f"Резервный вход {names}: изменения пиров не доходят",
                            started_at=now - timedelta(seconds=oldest)))
        await db.commit()
        logger.warning("entry sync stale (%d jobs), alert sent", count)
        return "alerted"

    if open_event is None:
        return "quiet"
    subject, html, text = _letter(
        "Sovereign: резервный вход догнал",
        ["Изменения пиров, которые ждали больше часа, дошли до резервного входа.",
         "Проверить совпадение можно сверкой (tools/peer_reconcile.py, runbook §9)."])
    if not await mailer.send_email(alert_address(), subject, html, text):
        return "recovery-failed"
    open_event.ended_at = now
    await db.commit()
    logger.info("entry sync caught up, all-clear sent")
    return "recovered"
