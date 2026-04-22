"""
AI handlers: /analyze and free-form chat via handle_message.
"""
import asyncio
import logging
import subprocess

from telegram import Update
from telegram.ext import ContextTypes

from config import AWG_SERVICE
from services.gemini import analyze_logs, chat
from utils.telegram import auth_filter, send_long_message

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# System data collector
# ----------------------------------------------------------------------

def _collect_system_data() -> tuple[str, str]:
    """
    Collect AWG journal logs and basic system metrics.
    Runs in executor — synchronous subprocess calls.
    """
    # Logs
    log_result = subprocess.run(
        [
            "sudo", "journalctl",
            "-u", AWG_SERVICE,
            "-n", "50",
            "--no-pager",
            "--output", "short-iso",
        ],
        capture_output=True, text=True, timeout=10,
    )
    logs = log_result.stdout.strip() if log_result.returncode == 0 else (
        f"journalctl error: {log_result.stderr.strip()}"
    )

    # Metrics
    metrics_result = subprocess.run(
        ["bash", "-c", "uptime && free -m && df -h /"],
        capture_output=True, text=True, timeout=5,
    )
    metrics = metrics_result.stdout.strip() if metrics_result.returncode == 0 else (
        f"metrics error: {metrics_result.stderr.strip()}"
    )

    return logs, metrics


# ----------------------------------------------------------------------
# Core analyze logic — from command and from menu_callback
# ----------------------------------------------------------------------

async def run_analyze(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Shared analyze logic. Works for both /analyze command
    and menu_analyze callback.
    """
    msg = (
        update.callback_query.message
        if update.callback_query
        else update.message
    )

    status_msg = await msg.reply_text("📡 Step 1/2: Collecting system data...")

    loop = asyncio.get_event_loop()

    try:
        logs, metrics = await loop.run_in_executor(None, _collect_system_data)
    except Exception as e:
        logger.error("_collect_system_data failed: %s", e)
        await status_msg.edit_text(f"❌ Failed to collect data: {e}")
        return

    await status_msg.edit_text("🧠 Step 2/2: Analyzing with Gemini...")

    answer = await analyze_logs(logs=logs, metrics=metrics)

    header = "🤖 *VPN Health Report*\n" + "—" * 20 + "\n"
    full_text = header + answer

    try:
        await status_msg.edit_text(full_text, parse_mode="Markdown")
    except Exception:
        # Markdown failed — send plain text
        await status_msg.edit_text(full_text)


# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------

async def analyze_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return
    await run_analyze(update, context)


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    user_text = update.message.text
    if not user_text:
        return

    try:
        answer = await chat(user_text)
    except Exception as e:
        logger.error("chat failed: %s", e)
        answer = "⚠️ AI service error. Please try again later."

    await send_long_message(update, answer)