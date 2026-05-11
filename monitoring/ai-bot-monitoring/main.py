"""
AIKVPN Entry Point. 
Focused on infrastructure monitoring and automated fixes.
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
from services import llm_engine
from handlers.system import start, menu_callback
from handlers.ai import handle_message

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

def main() -> None:
    # 1. Валидация конфига (токены и пути)
    validate()

    # 2. Инициализация Gemini (наш AI-монитор)
    llm_engine.init()

    # 3. Сборка приложения
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 4. Регистрация команд (минимум для управления)
    # Основной вход — через кнопки меню
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu",  start)) # /menu теперь делает то же самое

    # 5. Регистрация Callback-хендлеров (Сердце управления)
    # Все действия: фиксы, логи, статусы — летят сюда
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^(menu_|fix_)"))

    # 6. Обработка свободного ввода (Чат с AI-агентом)
    # Оставляем в конце для анализа нестандартных ситуаций
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("SRE-Bot started (Production Mode)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()