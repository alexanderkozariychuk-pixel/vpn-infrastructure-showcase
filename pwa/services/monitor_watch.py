"""
services/monitor_watch.py — the dead man's switch for the monitor itself.

sov-monitor on the backup host checks everything and posts a report here every
two minutes. If the backup host dies, or loses its network, or its reports are
refused, the monitoring simply stops — and nothing would say so: the alerts it
sends come from that same host. The admin panel shows "Мониторинг молчит", but
only to someone who opens it.

So the portal watches the reports and writes a letter when they stop
(pwa/monitor_watch.py, from cron every few minutes). A different host, a
different provider and a different channel from the monitor's Telegram: mail
through Resend, which the portal already uses and which reaches Gmail.

State is one row in monitor_events with the key SILENT_KEY: open while the
monitor is silent, closed when it is back. That row is also what the admin
page's history shows. It is opened only after the alert went out and closed
only after the all-clear went out, so a letter that failed is sent again on
the next run instead of being lost.

A portal that never received a report (monitoring not set up) says nothing:
silence only counts after the monitor has spoken.
"""
import logging
import os
from datetime import datetime, timezone
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import MonitorEvent, MonitorReport
from services import mailer
from services.monitor_view import STALE_AFTER_S, aware, duration, when

logger = logging.getLogger(__name__)

# The monitor's own reports close every open event they do not carry
# (api/monitor.py); this key is the portal's and is left alone there.
SILENT_KEY = "portal:monitor-silent"


def alert_address() -> str:
    return os.getenv("MONITOR_ALERT_EMAIL", "").strip() or mailer.SUPPORT_INBOX


def _letter(subject: str, lines: list[str]) -> tuple[str, str, str]:
    text = "\n".join(lines)
    html = "".join(f"<p>{escape(line)}</p>" for line in lines)
    return subject, html, text


async def watch(db: AsyncSession, now: datetime | None = None) -> str:
    """One check. Returns what it did: quiet, silent, alerted, recovered, or a
    failure to send ('alert-failed', 'recovery-failed')."""
    now = now or datetime.now(timezone.utc)
    row = await db.get(MonitorReport, 1)
    if row is None:
        return "no-reports"
    last = aware(row.received_at)
    silent_for = (now - last).total_seconds()
    open_event = (await db.execute(select(MonitorEvent).where(
        MonitorEvent.key == SILENT_KEY, MonitorEvent.ended_at.is_(None)))).scalars().first()

    if silent_for > STALE_AFTER_S:
        if open_event is not None:
            return "silent"
        subject, html, text = _letter(
            "Sovereign: мониторинг молчит",
            [f"Последний отчёт от монитора (am1) пришёл {when(last, now)} МСК — "
             f"{duration(silent_for)} назад.",
             "Пока он молчит, о сбоях на серверах никто не сообщит.",
             "Что проверить: жив ли am1 (ssh am1), запускается ли таймер sov-monitor, "
             "доходят ли его отчёты до портала.",
             "Когда отчёты вернутся, придёт письмо «мониторинг снова на связи»."])
        if not await mailer.send_email(alert_address(), subject, html, text):
            return "alert-failed"
        # The silence began with the last report, not when the threshold was
        # crossed: the history shows how long nothing was watched.
        db.add(MonitorEvent(key=SILENT_KEY, level="bad", text="Мониторинг (am1) молчит",
                            started_at=last))
        await db.commit()
        logger.warning("monitor silent since %s, alert sent", last.isoformat())
        return "alerted"

    if open_event is None:
        return "quiet"
    # From the last report before the silence to the first one after it.
    gap = (last - aware(open_event.started_at)).total_seconds()
    subject, html, text = _letter(
        "Sovereign: мониторинг снова на связи",
        [f"Отчёты от монитора (am1) снова приходят: последний — {when(last, now)} МСК.",
         f"Перерыв длился около {duration(gap)}. Сбои за это время монитор пришлёт "
         "сам, если они ещё не прошли; историю видно в админке, «Состояние»."])
    if not await mailer.send_email(alert_address(), subject, html, text):
        return "recovery-failed"
    open_event.ended_at = now
    await db.commit()
    logger.info("monitor back, all-clear sent")
    return "recovered"
