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

    # Support HEADLESS env var or default to False if interactive
    is_headless = os.environ.get("HEADLESS", "false").lower() in ("true", "1", "yes")

    # Launch browser context
    async with get_browser_context(
        session_file=settings.SESSION_STATE_FILE,
        headless=is_headless
    ) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        
        logger.info("Navigating to SnappShop seller panel (https://seller.snappshop.ir/)...")
        await page.goto("https://seller.snappshop.ir/", timeout=30000)
        await random_delay(1, 2)

        if await check_is_logged_in(page):
            logger.info("✅ An active valid session was already found and restored!")
        else:
            phone = settings.SNAPSHOP_PHONE_NUMBER or "09207051391"
            password = settings.SNAPSHOP_PASSWORD or "Roya9084@"

            if phone:
                logger.info(f"Filling phone number from settings: {phone}")
                try:
                    phone_input = await page.wait_for_selector(
                        "#phone-number-input, input[name='cellphone'], input[name='mobile'], input[name='username'], input[name='phone'], input[type='tel'], input[type='text']",
                        timeout=10000,
                    )
                    if phone_input:
                        await phone_input.fill(phone)

                    submit_btn = await page.wait_for_selector(
                        "xpath=//button[contains(text(), 'تایید و ادامه') or contains(text(), 'ادامه') or contains(text(), 'تایید') or @type='submit']",
                        timeout=5000,
                    )
                    if submit_btn:
                        await submit_btn.click()
                    await random_delay(2, 3)
                except Exception as fill_err:
                    logger.warning(f"Could not auto-fill phone number: {fill_err}")

            if password:
                logger.info("Attempting to fill password from settings...")
                try:
                    password_input = await page.wait_for_selector(
                        "input[type='password'], input[name='password']",
                        timeout=10000,
                    )
                    if password_input:
                        await password_input.fill(password)
                        login_btn = await page.wait_for_selector(
                            "xpath=//button[contains(text(), 'ورود') or @type='submit']",
                            timeout=5000,
                        )
                        if login_btn:
                            await login_btn.click()
                        await random_delay(4, 6)
                except Exception as pass_err:
                    logger.warning(f"Could not auto-fill password: {pass_err}")

            # Check if login completed after password entry
            if not await check_is_logged_in(page):
                logger.info("\n" + "=" * 60)
                logger.info(" ACTION REQUIRED:")
                logger.info(" SMS OTP code page reached. Waiting 2 minutes (120 seconds) for OTP entry...")
                logger.info(" Please enter the SMS OTP code received on phone.")
                logger.info("=" * 60 + "\n")

                # Wait 2 minutes (120s) checking for successful login every 5 seconds
                total_wait_seconds = 120
                poll_interval = 5
                for elapsed in range(0, total_wait_seconds, poll_interval):
                    await asyncio.sleep(poll_interval)
                    if await check_is_logged_in(page):
                        logger.info(f"✅ Login successfully detected after {elapsed + poll_interval} seconds!")
                        break

        # Final session verification
        is_logged_in = await check_is_logged_in(page)
        if is_logged_in:
            await context.storage_state(path=str(settings.SESSION_STATE_FILE))
            logger.info("==========================================================")
            logger.info(" SUCCESS! Session state saved successfully.")
            logger.info(f" Saved to: {settings.SESSION_STATE_FILE}")
            logger.info("==========================================================")
            return True
        else:
            logger.error("❌ Session check failed: User is not logged into SnappShop seller panel.")
            # Remove invalid session state file
            if settings.SESSION_STATE_FILE.exists():
                try:
                    settings.SESSION_STATE_FILE.unlink()
                except Exception:
                    pass
            return False


if __name__ == "__main__":
    try:
        success = asyncio.run(run_interactive_login())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\nSession setup cancelled by user.")
        sys.exit(1)
