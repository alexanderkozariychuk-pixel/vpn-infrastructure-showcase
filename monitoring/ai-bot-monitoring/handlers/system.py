"""
System handlers: /start, /menu and focused infrastructure fixes.
"""
import logging
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import ContextTypes

from utils.telegram import auth_filter
# Импортируем новые функции из переименованного сервиса
from services.net_manager import fix_ipip_bridge, fix_awg_interface

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Keyboards
# ----------------------------------------------------------------------

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 System Status", callback_data="menu_status")],
        [InlineKeyboardButton("🛠 Infrastructure Fix", callback_data="menu_fix")],
        [InlineKeyboardButton("📜 Recent Logs", callback_data="menu_logs")],
        [InlineKeyboardButton("🔍 AI Analysis", callback_data="menu_analyze")],
    ])

def _fix_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Reset IPIP Bridge", callback_data="fix_ipip")],
        [InlineKeyboardButton("🛡️ Reset AWG Interface", callback_data="fix_awg")],
        [InlineKeyboardButton("🧹 Clear Logs", callback_data="fix_logs")],
        [InlineKeyboardButton("« Back to Menu", callback_data="menu_back")],
    ])

# ----------------------------------------------------------------------
# Handlers
# ----------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await auth_filter(update, context):
        return
    await update.message.reply_text(
        "AIKVPN Monitoring Active. Choose option:",
        reply_markup=_main_menu_keyboard(),
    )

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await auth_filter(update, context):
        return

    query = update.callback_query
    await query.answer()

    # Динамические импорты для экономии памяти
    from handlers.status import get_status_text, get_logs_text
    from handlers.ai import run_analyze

    match query.data:
        case "menu_status":
            text = await get_status_text()
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_main_menu_keyboard())

        case "menu_fix":
            await query.edit_message_text("Select infrastructure component to reset:", reply_markup=_fix_menu_keyboard())

        case "menu_logs":
            text = await get_logs_text(lines=20)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_main_menu_keyboard())

        case "menu_analyze":
            await run_analyze(update, context)

        case "menu_back":
            await query.edit_message_text("Main menu:", reply_markup=_main_menu_keyboard())

        # --- Блок фиксов ---
        case "fix_ipip":
            await query.edit_message_text("⏳ Resetting IPIP Moldova-Bulgaria bridge...")
            success = fix_ipip_bridge()
            msg = "✅ IPIP Bridge restored" if success else "❌ IPIP Reset failed"
            await query.edit_message_text(msg, reply_markup=_main_menu_keyboard())

        case "fix_awg":
            await query.edit_message_text("⏳ Resetting AmneziaWG interface...")
            success = fix_awg_interface()
            msg = "✅ AWG Interface restarted" if success else "❌ AWG Reset failed"
            await query.edit_message_text(msg, reply_markup=_main_menu_keyboard())

        case "fix_logs":
            from services.net_manager import restart_full_service # или добавь очистку логов в net_manager
            # Можно вызвать напрямую subprocess здесь для очистки логов
            import subprocess
            subprocess.run(["sudo", "journalctl", "--vacuum-time=1d"])
            await query.edit_message_text("✅ Logs vacuumed (1 day kept).", reply_markup=_main_menu_keyboard())