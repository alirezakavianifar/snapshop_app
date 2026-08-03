import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
from src.config.settings import settings
from src.core.browser import get_browser_context
from src.core.auth import login_to_seller_panel
from src.core.scraper import download_inventory_excel, upload_inventory_excel, scrape_storefront_buybox
from src.core.pricing import process_inventory_and_generate_update
from src.core.database import DatabaseManager
from src.telegram.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


async def run_sync_cycle(notifier: Optional[TelegramNotifier] = None) -> bool:
    """
    Execute complete end-to-end SnappShop price monitoring & update cycle.
    """
    logger.info("==================================================")
    logger.info("Starting SnappShop Price Monitoring & Sync Cycle")
    logger.info("==================================================")

    db_manager = DatabaseManager(settings.DATABASE_PATH)
    notifier = notifier or TelegramNotifier()

    try:
        is_headless = os.environ.get("HEADLESS", "true").lower() in ("true", "1", "yes")
        async with get_browser_context(session_file=settings.SESSION_STATE_FILE, headless=is_headless) as context:
            # Step 1: Authentication & Session Verification
            authenticated = await login_to_seller_panel(
                context=context,
                phone_number=settings.SNAPSHOP_PHONE_NUMBER,
                password=settings.SNAPSHOP_PASSWORD,
                otp_callback=notifier.send_otp_request if settings.SNAPSHOP_PHONE_NUMBER else None,
            )

            if not authenticated:
                err = "Failed to authenticate with SnappShop seller panel."
                logger.error(err)
                await notifier.send_error_alert(err)
                return False

            # Step 2: Download Inventory Excel
            excel_path = await download_inventory_excel(context, settings.DOWNLOADS_DIR)
            if not excel_path or not excel_path.exists():
                err = "Failed to download inventory Excel file."
                logger.error(err)
                await notifier.send_error_alert(err)
                return False

            # Step 3: Scrape Competitor Buybox Details
            competitors_data = await scrape_storefront_buybox(
                context=context,
                store_url=settings.SNAPSHOP_STORE_URL,
                company_name=settings.SNAPSHOP_COMPANY_NAME,
            )

            # Step 4: Process Pricing Bounds & Generate Update Excel (01.xlsx)
            output_excel = settings.DOWNLOADS_DIR / "01.xlsx"
            result = process_inventory_and_generate_update(
                excel_path=excel_path,
                competitors_data=competitors_data,
                output_path=output_excel,
                db_manager=db_manager,
            )

            # Step 5: Upload Updated Excel to Seller Panel
            if result["updated_count"] > 0:
                upload_success = await upload_inventory_excel(context, output_excel)
                if not upload_success:
                    await notifier.send_error_alert("Failed to upload updated 01.xlsx to seller panel.")

            # Step 6: Send Report to Telegram
            await notifier.send_status_report(
                updated_count=result["updated_count"],
                skipped_count=result["skipped_count"],
                changes=result["price_changes"],
            )

            logger.info("Cycle completed successfully.")
            return True

    except Exception as e:
        error_msg = f"Unexpected error during sync cycle: {e}"
        logger.exception(error_msg)
        await notifier.send_error_alert(error_msg)
        return False


async def start_continuous_scheduler(interval_minutes: int = 20):
    """Run sync cycle continuously at specified minute intervals."""
    logger.info(f"Starting continuous scheduler loop every {interval_minutes} minutes.")
    while True:
        try:
            await run_sync_cycle()
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}")
        
        logger.info(f"Sleeping for {interval_minutes} minutes...")
        await asyncio.sleep(interval_minutes * 60)
