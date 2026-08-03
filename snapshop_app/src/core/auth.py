import asyncio
import logging
from typing import Callable, Optional, Awaitable
from playwright.async_api import BrowserContext, Page
from src.config.settings import settings
from src.core.browser import random_delay

logger = logging.getLogger(__name__)

OTPCallback = Callable[[str], Awaitable[str]]


async def check_is_logged_in(page: Page) -> bool:
    """Verify if currently logged into seller panel."""
    try:
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=15000)
        await page.wait_for_load_state("networkidle", timeout=10000)
        # Check if redirected to login page
        if "login" in page.url or await page.query_selector("#phone-number-input"):
            return False
        return True
    except Exception as e:
        logger.warning(f"Session check error: {e}")
        return False


async def login_to_seller_panel(
    context: BrowserContext,
    phone_number: str,
    password: Optional[str] = None,
    otp_callback: Optional[OTPCallback] = None,
) -> bool:
    """
    Log in to seller panel using password or OTP prompt callback.
    """
    page = await context.new_page()
    try:
        await page.goto("https://seller.snappshop.ir/", timeout=20000)
        await random_delay(1, 2)

        if await check_is_logged_in(page):
            logger.info("Existing session is valid. Skipping login.")
            return True

        logger.info(f"Initiating login for phone: {phone_number}")
        await page.fill("#phone-number-input", phone_number)
        await page.click("//button[contains(text(), 'تایید و ادامه')]")
        await random_delay(1, 2)

        if password:
            logger.info("Attempting password authentication...")
            password_input = await page.wait_for_selector("input[name='password']", timeout=10000)
            if password_input:
                await password_input.fill(password)
                await page.click("//button[contains(text(), 'ورود به حساب کاربری')]")
                await random_delay(3, 5)

        if not await check_is_logged_in(page):
            # Fallback to OTP entry
            logger.info("OTP verification required.")
            if otp_callback:
                otp_code = await otp_callback(phone_number)
                if otp_code:
                    logger.info("Submitting received OTP code...")
                    # Assuming 6 individual inputs or single input box for OTP
                    otp_inputs = await page.query_selector_all("input[type='text'], input[type='number']")
                    if len(otp_inputs) == 1:
                        await otp_inputs[0].fill(otp_code)
                    elif len(otp_inputs) >= len(otp_code):
                        for i, char in enumerate(otp_code):
                            await otp_inputs[i].fill(char)
                    await random_delay(2, 4)

        success = await check_is_logged_in(page)
        if success:
            logger.info("Login successful. Session updated.")
        else:
            logger.error("Login failed.")
        return success
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False
    finally:
        await page.close()
