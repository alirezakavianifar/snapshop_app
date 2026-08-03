import sys
import os
import asyncio
import logging

# Ensure src package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.settings import settings
from src.telegram.bot import create_telegram_bot_app
from src.scheduler.job_runner import start_continuous_scheduler, run_sync_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(settings.DOWNLOADS_DIR / "bot_activity.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("SnapShopBot")


async def main():
    logger.info("Initializing SnappShop Smart Price Bot...")
    
    # Initialize Telegram Bot Application if configured
    telegram_app = create_telegram_bot_app()
    
    if telegram_app:
        logger.info("Starting Telegram Bot long-polling...")
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()

    # Trigger initial cycle on startup
    logger.info("Executing initial sync cycle...")
    await run_sync_cycle()

    # Start periodic scheduler task
    scheduler_task = asyncio.create_task(
        start_continuous_scheduler(interval_minutes=settings.CHECK_INTERVAL_MINUTES)
    )

    try:
        await scheduler_task
    except asyncio.CancelledError:
        logger.info("Shutdown signal received.")
    finally:
        if telegram_app:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
