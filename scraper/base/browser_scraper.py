import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Union
from urllib.parse import urlparse

from playwright.async_api import Browser, Frame, Page, async_playwright

from scraper.base.base_scraper import BaseScraper
from scraper.models.result import LoginResult
from scraper.utils import (
    click_button,
    fetch_get_within_page,
    fetch_post_within_page,
    fill_input,
    get_current_url,
    wait_for_navigation,
    wait_until_element_found,
)

logger = logging.getLogger(__name__)

LoginResultCheck = Union[str, re.Pattern, Callable[..., Awaitable[bool]]]


@dataclass
class LoginOptions:
    """Configuration for the generic login flow."""

    login_url: str
    fields: list[dict[str, str]]
    submit_button_selector: Union[str, Callable[[], Awaitable[None]]]
    possible_results: dict[LoginResult, list[LoginResultCheck]]
    check_readiness: Optional[Callable[[], Awaitable[None]]] = None
    pre_action: Optional[Callable[[], Awaitable[Optional[Frame]]]] = None
    post_action: Optional[Callable[[], Awaitable[None]]] = None
    user_agent: Optional[str] = None
    wait_until: str = "load"


class BrowserScraper(BaseScraper):
    """Scraper using Playwright browser automation.

    Provides a generic login flow and browser-based fetch utilities.
    Subclasses must implement `get_login_options()` and `fetch_data()`.
    """

    page: Page
    browser: Browser

    # Real Chrome user agent to use in headless mode
    _DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # JS to patch common headless detection vectors
    _STEALTH_INIT_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['he-IL', 'he', 'en-US', 'en'] });
    window.chrome = { runtime: {} };
    """

    async def initialize(self) -> None:
        """Launch Playwright browser and create a page with stealth measures."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=not self.options.show_browser,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = await self.browser.new_context(
            user_agent=self._DEFAULT_USER_AGENT,
            viewport={"width": 1024, "height": 768},
            locale="he-IL",
        )
        await context.add_init_script(self._STEALTH_INIT_SCRIPT)
        self.page = await context.new_page()
        self.page.set_default_timeout(self.options.default_timeout)

    async def login(self) -> LoginResult:
        """Execute the generic login flow.

        Calls `get_login_options()` to obtain provider-specific configuration,
        then navigates to the login page, fills credentials, submits, and
        detects the login result.

        Returns
        -------
        LoginResult
            The outcome of the login attempt.
        """
        login_options = self.get_login_options(self.credentials)

        if login_options.user_agent:
            await self.page.set_extra_http_headers(
                {"User-Agent": login_options.user_agent}
            )

        self._emit_progress("navigating to login page")
        await self.navigate_to(login_options.login_url, login_options.wait_until)

        # Wait for readiness
        if login_options.check_readiness:
            await login_options.check_readiness()
        elif isinstance(login_options.submit_button_selector, str):
            await wait_until_element_found(
                self.page, login_options.submit_button_selector
            )

        # Execute pre-action (e.g., switch to iframe)
        active_frame: Page | Frame = self.page
        if login_options.pre_action:
            frame_result = await login_options.pre_action()
            if frame_result is not None:
                active_frame = frame_result

        # Fill input fields
        self._emit_progress("filling login credentials")
        for field_def in login_options.fields:
            await fill_input(active_frame, field_def["selector"], field_def["value"])

        # Submit
        self._emit_progress("submitting login form")
        if callable(login_options.submit_button_selector):
            await login_options.submit_button_selector()
        else:
            await click_button(active_frame, login_options.submit_button_selector)

        # Post-action or wait for navigation
        if login_options.post_action:
            await login_options.post_action()
        else:
            await wait_for_navigation(self.page)

        # Detect login result
        self._emit_progress("detecting login result")
        return await self._detect_login_result(
            login_options.possible_results
        )

    async def terminate(self, success: bool) -> None:
        """Take failure screenshot if configured, then close browser."""
        if not success and self.options.store_failure_screenshot_path:
            try:
                await self.page.screenshot(
                    path=self.options.store_failure_screenshot_path
                )
                logger.info(
                    "Failure screenshot saved to %s",
                    self.options.store_failure_screenshot_path,
                )
            except Exception as e:
                logger.warning("Failed to take failure screenshot: %s", e)

        try:
            await self.browser.close()
        except Exception:
            pass
        try:
            await self._playwright.stop()
        except Exception:
            pass

    def get_login_options(self, credentials: dict) -> LoginOptions:
        """Return provider-specific login configuration.

        Parameters
        ----------
        credentials : dict
            Provider credentials (keys vary by provider).

        Returns
        -------
        LoginOptions
            Login flow configuration.

        Raises
        ------
        NotImplementedError
            Subclasses must override this method.
        """
        raise NotImplementedError(
            "Subclasses must implement get_login_options()"
        )

    async def fetch_get(
        self, url: str, ignore_errors: bool = False
    ) -> Any:
        """Execute a GET request within the browser page context."""
        return await fetch_get_within_page(self.page, url, ignore_errors)

    async def fetch_post(
        self,
        url: str,
        data: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
        ignore_errors: bool = False,
    ) -> Any:
        """Execute a POST request within the browser page context."""
        return await fetch_post_within_page(
            self.page, url, data, extra_headers, ignore_errors
        )

    async def navigate_to(
        self, url: str, wait_until: str = "load"
    ) -> None:
        """Navigate the page to a URL.

        Parameters
        ----------
        url : str
            Target URL. Must use an ``http`` or ``https`` scheme — ``javascript:``,
            ``file:``, ``data:``, and other schemes are rejected so a compromised
            credential or provider config cannot pivot the browser into executing
            attacker-supplied scripts or reading local files.
        wait_until : str
            Playwright load state to wait for.
        """
        scheme = urlparse(url).scheme.lower()
        if scheme not in ("http", "https"):
            raise ValueError(
                f"Refusing to navigate to non-http(s) URL scheme: {scheme!r}"
            )
        response = await self.page.goto(url, wait_until=wait_until)
        if response and not response.ok:
            logger.warning(
                "Navigation to %s returned status %s", url, response.status
            )

    async def _human_delay(self, min_sec: float = 0.3, max_sec: float = 1.0) -> None:
        """Sleep for a random duration to mimic human timing."""
        from scraper.utils import sleep

        await sleep(random.uniform(min_sec, max_sec))

    async def _type_like_human(self, selector: str, text: str) -> None:
        """Type text character by character with random delays between keystrokes."""
        await self.page.evaluate(
            "(selector) => { const el = document.querySelector(selector); if (el) el.value = ''; }",
            selector,
        )
        for char in text:
            await self.page.type(selector, char, delay=random.randint(50, 150))
            await self._human_delay(0.02, 0.08)

    async def _human_mouse_move(self) -> None:
        """Move the mouse to a random position on the page."""
        await self.page.mouse.move(
            random.randint(300, 700), random.randint(200, 400)
        )

    async def _human_scroll(self) -> None:
        """Scroll the page a small random amount."""
        await self.page.mouse.wheel(0, random.randint(50, 150))

    async def _detect_login_result(
        self,
        possible_results: dict[LoginResult, list[LoginResultCheck]],
    ) -> LoginResult:
        """Check login page state against possible result conditions.

        Iterates through each LoginResult and its associated checks.
        Returns the first matching result.

        Parameters
        ----------
        possible_results : dict[LoginResult, list[LoginResultCheck]]
            Mapping of login results to lists of conditions to check.

        Returns
        -------
        LoginResult
            The detected login result, or UNKNOWN_ERROR if no match.
        """
        current_url = await get_current_url(self.page)

        for result, checks in possible_results.items():
            for check in checks:
                if isinstance(check, re.Pattern):
                    if check.search(current_url):
                        return result
                elif isinstance(check, str):
                    if check.lower() in current_url.lower():
                        return result
                elif callable(check):
                    try:
                        matched = await check(page=self.page, value=current_url)
                        if matched:
                            return result
                    except Exception as e:
                        logger.debug(
                            "Login result check callable raised: %s", e
                        )

        return LoginResult.UNKNOWN_ERROR
