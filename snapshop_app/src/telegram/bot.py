import logging
from typing import Optional
from src.config.settings import settings

logger = logging.getLogger(__name__)

try:
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
    from src.telegram.handlers import (
        start_command,
        status_command,
        run_now_command,
        set_interval_command,
        handle_document,
        handle_message,
    )
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False


def create_telegram_bot_app(token: Optional[str] = None):
    """
    Build Telegram bot application instance with configured command handlers.
    """
    if not HAS_TELEGRAM:
        logger.warning("python-telegram-bot is not installed. Telegram bot features disabled.")
        return None

    bot_token = token or settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured. Telegram bot features disabled.")
        return None

    app = ApplicationBuilder().token(bot_token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("run_now", run_now_command))
    app.add_handler(CommandHandler("set_interval", set_interval_command))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
