"""
System handlers: /start, /help, /menu, /restart and related callbacks.
"""
import logging

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from utils.telegram import auth_filter
from services.wireguard import restart_wireguard

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Keyboards
# ----------------------------------------------------------------------

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Status",     callback_data="menu_status")],
        [InlineKeyboardButton("👥 Clients",    callback_data="menu_clients")],
        [InlineKeyboardButton("📜 Logs",       callback_data="menu_logs")],
        [InlineKeyboardButton("🔍 Analyze",    callback_data="menu_analyze")],
        [InlineKeyboardButton("🔄 Restart",    callback_data="menu_restart")],
    ])

def _confirm_restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, restart", callback_data="restart_confirm")],
        [InlineKeyboardButton("❌ No",           callback_data="restart_cancel")],
    ])

# ----------------------------------------------------------------------
# /start, /help, /menu
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await auth_filter(update, context):
        return
    await update.message.reply_text(
        "Bot is active. Choose an option:",
        reply_markup=_main_menu_keyboard(),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)

# ----------------------------------------------------------------------
# /restart
# ----------------------------------------------------------------------

async def restart_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return
    context.user_data["pending_restart"] = True
    await update.message.reply_text(
        "⚠️ Are you sure you want to restart AmneziaWG?\n"
        "This will briefly interrupt the VPN.",
        reply_markup=_confirm_restart_keyboard(),
    )

async def restart_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    query = update.callback_query
    await query.answer()

    if query.data == "restart_confirm":
        if not context.user_data.get("pending_restart"):
            await query.edit_message_text("⚠️ No pending restart request.")
            return

        context.user_data.pop("pending_restart", None)
        await query.edit_message_text("⏳ Restarting AmneziaWG...")

        success = restart_wireguard()
        if success:
            await query.edit_message_text("✅ AmneziaWG restarted successfully.")
        else:
            await query.edit_message_text(
                "❌ Failed to restart. Check logs for details."
            )

    elif query.data == "restart_cancel":
        context.user_data.pop("pending_restart", None)
        await query.edit_message_text("Restart cancelled.")

# ----------------------------------------------------------------------
# menu_callback
# ----------------------------------------------------------------------

async def menu_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await auth_filter(update, context):
        return

    query = update.callback_query
    await query.answer()

    # Импорты здесь — избегаем circular imports
    from handlers.status import get_status_text, get_logs_text
    from handlers.clients import get_clients_text
    from handlers.ai import run_analyze

    match query.data:
        case "menu_status":
            text = await get_status_text()
            await query.edit_message_text(text, parse_mode="Markdown")

        case "menu_clients":
            text = await get_clients_text()
            await query.edit_message_text(text, parse_mode="Markdown")

        case "menu_logs":
            text = await get_logs_text(lines=20)
            await query.edit_message_text(text, parse_mode="Markdown")

        case "menu_analyze":
            await run_analyze(update, context)

        case "menu_restart":
            context.user_data["pending_restart"] = True
            await query.edit_message_text(
                "⚠️ Are you sure you want to restart AmneziaWG?\n"
                "This will briefly interrupt the VPN.",
                reply_markup=_confirm_restart_keyboard(),
            )