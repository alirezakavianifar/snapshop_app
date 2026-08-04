import asyncio
import logging
from typing import Callable, Optional, Awaitable
from src.config.settings import settings
from src.core.browser import random_delay

logger = logging.getLogger(__name__)

OTPCallback = Callable[[str], Awaitable[str]]


async def check_is_logged_in_passive(page) -> bool:
    """Passively check if page navigated to authenticated route without triggering page.goto navigation."""
    try:
        current_url = page.url.rstrip("/")
        if "inventory" in current_url.lower() or "dashboard" in current_url.lower():
            return True
        return False
    except Exception:
        return False


async def check_is_logged_in(page) -> bool:
    """Verify if currently logged into seller panel."""
    try:
        current_url = page.url.rstrip("/")
        # Fast-check if already on authenticated route
        if "inventory" in current_url.lower() or "dashboard" in current_url.lower():
            return True

        # Navigate to bulk-update to verify session
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=20000)
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
        await random_delay(1.5, 3.0)
        current_url = page.url.rstrip("/")

        if "inventory" in current_url.lower() or "dashboard" in current_url.lower():
            return True

        # Check if page presented a login/phone input form
        login_input = await page.query_selector(
            "#phone-number-input, input[name='cellphone'], input[name='mobile'], input[name='username'], input[type='tel']"
        )
        if login_input:
            return False

        if any(sub in current_url.lower() for sub in ["login", "otp", "auth", "verify"]):
            return False

        return True
    except Exception as e:
        logger.warning(f"Session check error: {e}")
        return False


async def login_to_seller_panel(
    context,
    phone_number: str,
    password: Optional[str] = None,
    otp_callback: Optional[OTPCallback] = None,
) -> bool:
    """
    Log in to seller panel using password or OTP prompt callback.
    Saves storage state upon successful login.
    """
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        if await check_is_logged_in(page):
            logger.info("Existing session is valid. Skipping login.")
            return True

        logger.info("Session expired or missing. Navigating to seller login page...")
        await page.goto("https://seller.snappshop.ir/", timeout=20000)
        await random_delay(1, 2)

        phone = phone_number or settings.SNAPSHOP_PHONE_NUMBER or "09207051391"
        logger.info(f"Initiating login for phone: {phone}")
        
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

        pwd = password or settings.SNAPSHOP_PASSWORD or "Roya9084@"
        if pwd:
            logger.info("Attempting password authentication...")
            try:
                password_input = await page.wait_for_selector(
                    "input[type='password'], input[name='password']",
                    timeout=10000,
                )
                if password_input:
                    await password_input.fill(pwd)
                    await random_delay(0.5, 1.0)
                    
                    # 1. Native Enter keypress submit
                    logger.info("Submitting password via Enter key...")
                    await password_input.press("Enter")
                    await random_delay(1.5, 2.5)

                    # 2. Resilient Fallback: Click 'ورود' button explicitly with force & JS click if still visible
                    login_btn = await page.query_selector(
                        "button[type='submit'], xpath=//button[contains(text(), 'ورود')]"
                    )
                    if login_btn and await login_btn.is_visible():
                        logger.info("Clicking 'ورود' submit button directly...")
                        try:
                            await login_btn.click(force=True)
                        except Exception:
                            await page.evaluate("el => el.click()", login_btn)
                    
                    await random_delay(3, 5)
            except Exception as pass_err:
                logger.warning(f"Could not auto-fill password: {pass_err}")

        if await check_is_logged_in_passive(page):
            logger.info("✅ Login successful! Session restored.")
            return True

        # Fallback to OTP entry with automatic "دریافت مجدد کد" resend loop
        max_otp_attempts = 3
        for attempt in range(1, max_otp_attempts + 1):
            logger.info(f"OTP verification attempt {attempt}/{max_otp_attempts}. Waiting 2 minutes (120s)...")
            if otp_callback:
                try:
                    await otp_callback(phone_number)
                except Exception as cb_err:
                    logger.warning(f"Could not trigger OTP notification callback: {cb_err}")

            otp_future = asyncio.get_event_loop().create_future()
            try:
                from src.telegram.handlers import set_otp_future
                set_otp_future(otp_future)
            except Exception:
                pass

            logged_in = False
            for _ in range(80):
                await asyncio.sleep(1.5)
                if await check_is_logged_in_passive(page):
                    logger.info("✅ Detected successful OTP login redirect in browser!")
                    logged_in = True
                    break

                if otp_future.done() and not otp_future.cancelled():
                    try:
                        telegram_code = otp_future.result()
                        if telegram_code:
                            logger.info(f"Submitting OTP code received via Telegram: {telegram_code}")
                            otp_inputs = await page.query_selector_all("input[type='text'], input[type='number']")
                            if len(otp_inputs) == 1:
                                await otp_inputs[0].fill(telegram_code)
                            elif len(otp_inputs) >= len(telegram_code):
                                for i, char in enumerate(telegram_code):
                                    await otp_inputs[i].fill(char)
                            await random_delay(1.5, 3.0)
                            submit_btn = await page.query_selector("button[type='submit'], xpath=//button[contains(text(), 'تایید') or contains(text(), 'ادامه')]")
                            if submit_btn and await submit_btn.is_visible():
                                await submit_btn.click(force=True)
                            await random_delay(2.0, 4.0)
                            if await check_is_logged_in_passive(page) or await check_is_logged_in(page):
                                logged_in = True
                                break
                    except Exception as t_err:
                        logger.warning(f"Error handling Telegram OTP result: {t_err}")

            if logged_in or await check_is_logged_in_passive(page):
                break

            # If 2 minutes passed without OTP entry, click "دریافت مجدد کد" and reset timer for next attempt
            if attempt < max_otp_attempts:
                logger.info("⏱ 2 minutes elapsed without OTP entry. Clicking 'دریافت مجدد کد' (Resend Code)...")
                resend_btn = await page.query_selector(
                    "xpath=//button[contains(text(), 'دریافت مجدد') or contains(text(), 'مجدد') or contains(text(), 'ارسال مجدد')]"
                )
                if resend_btn and await resend_btn.is_visible():
                    try:
                        await resend_btn.click(force=True)
                    except Exception:
                        await page.evaluate("el => el.click()", resend_btn)
                    logger.info("✅ Clicked 'دریافت مجدد کد'. Resetting timer for 2 more minutes.")
                    await random_delay(3.0, 5.0)
                else:
                    logger.warning("Could not find 'دریافت مجدد کد' button. Retrying wait loop...")

        success = await check_is_logged_in_passive(page) or await check_is_logged_in(page)
        if success:
            current_url = page.url.rstrip("/")
            if "inventory" in current_url.lower() or "dashboard" in current_url.lower():
                logger.info("Login verified with full seller permissions. Updating storage_state...")
                if settings.SESSION_STATE_FILE:
                    try:
                        settings.SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                        await context.storage_state(path=str(settings.SESSION_STATE_FILE))
                        logger.info(f"Saved verified seller session state to {settings.SESSION_STATE_FILE}")
                    except Exception as save_err:
                        logger.warning(f"Could not save storage state: {save_err}")
                return True
            else:
                logger.warning("Not inside dashboard/inventory. Skipping storage_state save.")
                return False
        else:
            logger.error("Login failed.")
        return success
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False
    finally:
        await page.close()

