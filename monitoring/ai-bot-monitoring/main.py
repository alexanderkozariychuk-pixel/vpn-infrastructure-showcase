# monitoring/ai-bot-monitoring/main.py
"""
Entry point. Wires everything together.
Nothing but initialization and handler registration lives here.
"""
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN, validate
from services import gemini
from handlers.system import (
    help_command,
    menu_callback,
    menu_command,
    restart_callback,
    restart_command,
    start,
)
from handlers.status import logs_command, status_command
from handlers.clients import addclient_command, clients_command, delclient_command
from handlers.ai import analyze_command, handle_message

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    # 1. Validate environment
    validate()

    # 2. Initialize Gemini
    gemini.init()

    # 3. Build application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 4. Register command handlers
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("help",       help_command))
    app.add_handler(CommandHandler("menu",       menu_command))
    app.add_handler(CommandHandler("status",     status_command))
    app.add_handler(CommandHandler("logs",       logs_command))
    app.add_handler(CommandHandler("clients",    clients_command))
    app.add_handler(CommandHandler("restart",    restart_command))
    app.add_handler(CommandHandler("addclient",  addclient_command))
    app.add_handler(CommandHandler("delclient",  delclient_command))
    app.add_handler(CommandHandler("analyze",    analyze_command))

    # 5. Register callback handlers
    app.add_handler(CallbackQueryHandler(menu_callback,    pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(restart_callback, pattern="^restart_"))

    # 6. Register message handler (free-form chat — must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()