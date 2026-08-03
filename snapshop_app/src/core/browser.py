import asyncio
import random
import logging
from pathlib import Path
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright, BrowserContext, Page, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    BrowserContext = Page = Playwright = None


async def random_delay(min_sec: float = 0.5, max_sec: float = 2.0):
    """Introduce human-like random pause."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def smooth_scroll_down(page, step: int = 400, pause: float = 0.3):
    """Smooth human-like scroll down to trigger lazy loading."""
    if not page:
        return
    current_scroll = 0
    total_height = await page.evaluate("document.body.scrollHeight")
    while current_scroll < total_height:
        current_scroll += step + random.randint(-50, 50)
        await page.evaluate(f"window.scrollTo(0, {current_scroll})")
        await asyncio.sleep(pause + random.uniform(0.05, 0.15))
        total_height = await page.evaluate("document.body.scrollHeight")


@asynccontextmanager
async def get_browser_context(
    session_file: Optional[Path] = None,
    headless: bool = True,
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
):
    """
    Async context manager for Playwright BrowserContext with session persistence and stealth parameters.
    """
    if not HAS_PLAYWRIGHT:
        logger.error("Playwright package is not installed. Install via `pip install playwright`.")
        raise RuntimeError("Playwright is required for browser context execution.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context_kwargs = {
            "user_agent": user_agent,
            "viewport": {"width": 1366, "height": 768},
            "locale": "fa-IR",
            "timezone_id": "Asia/Tehran",
            "ignore_https_errors": True,
        }

        if session_file and session_file.exists():
            logger.info(f"Loading persistent session state from {session_file}")
            context_kwargs["storage_state"] = str(session_file)

        context = await browser.new_context(**context_kwargs)
        
        # Apply anti-detection evasion scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        try:
            yield context
        finally:
            if session_file:
                try:
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    await context.storage_state(path=str(session_file))
                    logger.info(f"Saved session state to {session_file}")
                except Exception as err:
                    logger.warning(f"Could not save session state on close: {err}")
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass
