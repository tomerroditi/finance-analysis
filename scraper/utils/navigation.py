import re
from typing import Optional

from playwright.async_api import Frame, Page

from scraper.utils.waiting import wait_until


async def wait_for_navigation(
    page_or_frame: Page | Frame, wait_until_event: str = "load"
) -> None:
    """Wait for a navigation event (page load)."""
    await page_or_frame.wait_for_load_state(wait_until_event)


async def get_current_url(
    page_or_frame: Page | Frame, client_side: bool = False
) -> str:
    """Get the current URL of the page or frame."""
    if client_side:
        return await page_or_frame.evaluate("() => window.location.href")
    return page_or_frame.url


async def wait_for_redirect(
    page_or_frame: Page | Frame,
    timeout: float = 20.0,
    client_side: bool = False,
    ignore_list: Optional[list[str]] = None,
) -> None:
    """Wait for the URL to change from its current value."""
    initial = await get_current_url(page_or_frame, client_side)
    _ignore = ignore_list or []

    async def check():
        current = await get_current_url(page_or_frame, client_side)
        return current != initial and current not in _ignore

    await wait_until(check, f"waiting for redirect from {initial}", timeout, 1.0)


async def wait_for_url(
    page_or_frame: Page | Frame,
    url: str | re.Pattern,
    timeout: float = 20.0,
    client_side: bool = False,
) -> None:
    """Wait for the URL to match a string or regex pattern."""

    async def check():
        current = await get_current_url(page_or_frame, client_side)
        if isinstance(url, re.Pattern):
            return url.search(current) is not None
        return current == url

    await wait_until(check, f"waiting for url to be {url}", timeout, 1.0)
