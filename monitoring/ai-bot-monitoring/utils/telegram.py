"""
Shared Telegram utilities: authorization and message helpers.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ALLOWED_USER_ID

logger = logging.getLogger(__name__)

# Telegram hard limit per message
_MAX_MSG_LEN = 4096
# Safe chunk size — leaves room for split markers
_CHUNK_SIZE = 4000


def _split_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """
    Split long text into chunks without breaking code blocks.
    Tries to split on newlines first. Falls back to hard split.
    """
    if len(text) <= chunk_size:
        return [text]

    parts = []
    while text:
        if len(text) <= chunk_size:
            parts.append(text)
            break

        # Try to find a newline to split on
        split_at = text.rfind("\n", 0, chunk_size)
        if split_at == -1:
            # No newline found — hard split
            split_at = chunk_size

        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return parts


async def auth_filter(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    Returns True if the user is allowed.
    Logs and notifies on unauthorized access.
    """
    user = update.effective_user
    if not user:
        return False

    if user.id == ALLOWED_USER_ID:
        return True

    # Unauthorized — log and notify
    logger.warning(
        "Unauthorized access attempt | user=%s | id=%d | via=%s",
        user.first_name,
        user.id,
        "callback" if update.callback_query else "message",
    )

    if update.callback_query:
        await update.callback_query.answer(
            "⛔ Access denied.", show_alert=True
        )
    elif update.message:
        await update.message.reply_text(
            "⛔ Access restricted. This is a private bot."
        )
    return False


async def send_long_message(
    update: Update,
    text: str,
    parse_mode: str = "Markdown",
) -> None:
    """
    Send text that may exceed Telegram's 4096-char limit.
    Splits on newlines where possible to preserve formatting.
    Falls back to plain text if Markdown parsing fails.
    """
    parts = _split_text(text)
    total = len(parts)

    for i, part in enumerate(parts, 1):
        # Add part marker only if there are multiple parts
        content = f"{part}\n\n`{i}/{total}`" if total > 1 else part

        try:
            await update.message.reply_text(content, parse_mode=parse_mode)
        except Exception as e:
            logger.warning("Markdown failed on part %d/%d: %s", i, total, e)
            # Strip the marker from plain text fallback
            await update.message.reply_text(part)