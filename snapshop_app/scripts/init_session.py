import sys
import os
import asyncio
import logging
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.config.settings import settings
from src.core.browser import get_browser_context, random_delay
from src.core.auth import check_is_logged_in

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("InitSession")


async def run_interactive_login():
    """
    Launch interactive non-headless browser to perform a one-time login
    and SMS OTP verification, then save the session state (storage_state.json).
    """
    logger.info("==========================================================")
    logger.info("  SnappShop Bot - One-Time Session Setup Utility          ")
    logger.info("==========================================================")
    logger.info(f"Target session state file: {settings.SESSION_STATE_FILE}")

    # Ensure downloads directory exists
    settings.SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Launch browser with headless=False so user can see and interact
    async with get_browser_context(
        session_file=settings.SESSION_STATE_FILE,
        headless=False
    ) as context:
        page = await context.new_page()
        
        logger.info("Navigating to SnappShop seller panel (https://seller.snappshop.ir/)...")
        await page.goto("https://seller.snappshop.ir/", timeout=30000)
        await random_delay(1, 2)

        if await check_is_logged_in(page):
            logger.info("✅ An active valid session was already found and restored!")
        else:
            phone = settings.SNAPSHOP_PHONE_NUMBER
            password = settings.SNAPSHOP_PASSWORD

            if phone:
                logger.info(f"Filling phone number from settings: {phone}")
                try:
                    await page.fill("#phone-number-input", phone)
                    await page.click("//button[contains(text(), 'تایید و ادامه')]")
                    await random_delay(1, 2)
                except Exception as fill_err:
                    logger.warning(f"Could not auto-fill phone number: {fill_err}")

            if password:
                logger.info("Attempting to fill password from settings...")
                try:
                    password_input = await page.wait_for_selector("input[name='password']", timeout=5000)
                    if password_input:
                        await password_input.fill(password)
                        await page.click("//button[contains(text(), 'ورود به حساب کاربری')]")
                        await random_delay(2, 3)
                except Exception as pass_err:
                    logger.warning(f"Could not auto-fill password: {pass_err}")

            logger.info("\n" + "=" * 60)
            logger.info(" ACTION REQUIRED:")
            logger.info(" Please enter the SMS code (OTP) in the open browser window.")
            logger.info(" Once you have logged in and see the seller panel dashboard,")
            logger.info(" return here and press ENTER to save the session state.")
            logger.info("=" * 60 + "\n")

            # Pause execution asynchronously so user can complete manual login
            await asyncio.get_event_loop().run_in_executor(None, input, "Press ENTER after login is complete... ")

        # Verify session state
        is_logged_in = await check_is_logged_in(page)
        if is_logged_in:
            await context.storage_state(path=str(settings.SESSION_STATE_FILE))
            logger.info("==========================================================")
            logger.info(" SUCCESS! Session state saved successfully.")
            logger.info(f" Saved to: {settings.SESSION_STATE_FILE}")
            logger.info(" Future bot cycles will reuse this session and bypass 2FA SMS.")
            logger.info("==========================================================")
            return True
        else:
            logger.error("❌ Session check failed. Please re-run this setup utility.")
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_interactive_login())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nSession setup cancelled by user.")
        sys.exit(1)
