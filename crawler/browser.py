"""
Playwright browser lifecycle and launching utilities.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Browser

logger = logging.getLogger("wikipedia_crawler.browser")


async def launch_playwright_browser(playwright_instance: Any, headless: bool = True) -> Any:
    """
    Launch a Chromium-based browser with robust channel fallbacks:
    attempts Microsoft Edge first, then Google Chrome, then bundled Chromium.
    """
    for channel in ["msedge", "chrome", None]:
        try:
            kwargs: dict[str, Any] = {"headless": headless}
            if channel:
                kwargs["channel"] = channel
            browser = await playwright_instance.chromium.launch(**kwargs)
            logger.info(f"Successfully launched browser with channel={channel}")
            return browser
        except Exception as e:
            logger.warning(f"Could not launch browser with channel={channel}: {e}")
            continue
    raise RuntimeError("Could not launch any browser (msedge, chrome, or chromium).")


async def capture_page_screenshot(lang: str, title: str, headless: bool = True) -> str:
    """
    Open a single Wikipedia article in a fresh Playwright browser and return a
    JPEG screenshot as a base64 data URI (same format the crawler produces).
    """
    import base64
    import urllib.parse

    from playwright.async_api import async_playwright

    slug = urllib.parse.quote(title.strip().replace(" ", "_"), safe="()_,'!*-.~:")
    url = f"https://{lang}.wikipedia.org/wiki/{slug}"
    async with async_playwright() as pw:
        browser = await launch_playwright_browser(pw, headless=headless)
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            data = await page.screenshot(type="jpeg", quality=45)
            return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")
        finally:
            await browser.close()
