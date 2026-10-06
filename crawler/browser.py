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
