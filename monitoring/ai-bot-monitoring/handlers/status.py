"""
Status and logs builders for SRE-monitoring.
"""
import asyncio
import logging
import subprocess

from config import AWG_SERVICE
from services.net_manager import parse_awg_status

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Text builders
# ----------------------------------------------------------------------

async def get_status_text() -> str:
    """
    Build status message using parse_awg_status() from net_manager.
    """
    loop = asyncio.get_event_loop()
    # Исправлено: вызываем правильную функцию parse_awg_status
    peers, err = await loop.run_in_executor(None, parse_awg_status)

    if err:
        return f"🔴 **AmneziaWG error:**\n```\n{err}\n```"

    if not peers:
        return "🔴 **AmneziaWG is not running or no peers configured.**"

    # Считаем активных пиров
    active = sum(1 for p in peers if p.handshake != "0" and p.handshake != "never")
    total = len(peers)

    lines = [
        "🟢 *AmneziaWG Status*",
        f"Peers: {active}/{total} active\n",
    ]

    # Показываем статус пиров (ограничим до 10, чтобы не спамить)
    for i, peer in enumerate(peers[:10], 1):
        pk_short = peer.public_key[:12] + "..."
        lines += [
            f"*{i}.* `{pk_short}`",
            f"   Handshake: {peer.handshake}",
            f"   Transfer: {peer.transfer}",
            "",
        ]
    
    if len(peers) > 10:
        lines.append(f"...and {len(peers) - 10} more.")

    return "\n".join(lines)


async def get_logs_text(lines: int = 20) -> str:
    """
    Fetch recent journal logs for AWG service.
    """
    loop = asyncio.get_event_loop()

    def _fetch() -> str:
        result = subprocess.run(
            [
                "sudo", "journalctl",
                "-u", AWG_SERVICE,
                "-n", str(lines),
                "--no-pager",
                "--output", "short-iso",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return f"❌ journalctl error:\n{result.stderr.strip()}"
        return result.stdout.strip() or "ℹ️ No log entries found."

    try:
        output = await loop.run_in_executor(None, _fetch)
        # Ограничиваем длину сообщения для Telegram (макс 4096 символов)
        if len(output) > 3500:
            output = output[-3500:]
        return f"📜 *Logs ({lines} lines):*\n```\n{output}\n```"
    except Exception as e:
        logger.error("get_logs_text failed: %s", e)
        return f"⚠️ Error fetching logs: {e}"