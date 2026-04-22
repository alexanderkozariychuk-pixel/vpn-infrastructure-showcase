"""
Status and logs handlers: /status, /logs.
"""
import asyncio
import logging
import subprocess

from telegram import Update
from telegram.ext import ContextTypes

from config import AWG_SERVICE
from services.wireguard import parse_awg_show
from utils.telegram import auth_filter, send_long_message

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Text builders
# ----------------------------------------------------------------------

async def get_status_text() -> str:
    """
    Build status message using parse_awg_show().
    """
    loop = asyncio.get_event_loop()
    peers, err = await loop.run_in_executor(None, parse_awg_show)

    if err:
        return f"🔴 AmneziaWG error:\n```\n{err}\n```"

    if not peers:
        return "🔴 AmneziaWG is not running or no peers configured."

    # Count active peers — handshake not "never"
    active = sum(1 for p in peers if p.handshake != "never")
    total = len(peers)

    lines = [
        "🟢 *AmneziaWG is running*",
        f"Peers: {active}/{total} active\n",
    ]

    for i, peer in enumerate(peers, 1):
        pk_short = peer.public_key[:16] + "..."
        lines += [
            f"*{i}.* `{pk_short}`",
            f"   Endpoint: {peer.endpoint}",
            f"   Handshake: {peer.handshake}",
            f"   Transfer: {peer.transfer}",
            "",
        ]

    return "\n".join(lines)


async def get_logs_text(lines: int = 30) -> str:
    """
    Fetch recent journal logs for AWG service.
    Uses journalctl — more informative than dmesg for systemd services.
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
        return f"📜 *Logs ({lines} lines):*\n```\n{output}\n```"
    except Exception as e:
        logger.error("get_logs_text failed: %s", e)
        return f"⚠️ Error fetching logs: {e}"


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------

async def status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return
    text = await get_status_text()
    await update.message.reply_text(text, parse_mode="Markdown")


async def logs_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    # Optional argument: /logs 50
    args = context.args
    lines = 30
    if args and args[0].isdigit():
        lines = min(int(args[0]), 200)  # hard cap

    text = await get_logs_text(lines)
    await send_long_message(update, text)