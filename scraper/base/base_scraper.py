import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Optional

from scraper.exceptions import ScraperError
from scraper.models.account import AccountResult
from scraper.models.result import LoginResult, ScrapingResult

logger = logging.getLogger(__name__)

# Sentinel value the OTP callback (``on_otp_request``) returns to signal that
# the user aborted two-factor authentication. A scraper that receives this
# value MUST short-circuit its login and MUST NOT forward it to the provider
# as an OTP code. Kept in sync with ``ScraperAdapter.CANCEL``.
OTP_CANCEL_SENTINEL = "cancel"


class OtpCanceledError(Exception):
    """Raised when the user cancels the interactive OTP flow.

    A clean, user-initiated abort of two-factor authentication — distinct from
    an OTP verification failure — so ``login`` can end without contacting the
    provider's verify endpoint.
    """


class ResendNotSupportedError(Exception):
    """Raised when a scraper cannot re-issue its OTP in place.

    Interactive SMS providers (e.g. OneZero) override ``resend_otp`` to
    re-request the code without restarting login. Browser-driven providers
    that can't re-issue mid-flow leave the base implementation, which raises
    this so the backend falls back to aborting and relaunching the scrape.
    """


@dataclass
class ScraperOptions:
    """Configuration options for a scraper run."""

    show_browser: bool = False
    default_timeout: float = 30000
    start_date: date = field(default_factory=date.today)
    future_months_to_scrape: int = 0
    combine_installments: bool = False
    store_failure_screenshot_path: Optional[str] = None
    verbose: bool = False


class BaseScraper(ABC):
    """Abstract base class for all financial institution scrapers.

    Provides lifecycle orchestration: initialize -> login -> fetch_data -> terminate.
    Subclasses implement the abstract methods for provider-specific logic.
    """

    def __init__(
        self,
        provider: str,
        credentials: dict,
        options: ScraperOptions | None = None,
    ):
        self.provider = provider
        self.credentials = credentials
        self.options = options or ScraperOptions()
        self.on_progress: Optional[Callable[[str], None]] = None
        # Async callback returning the OTP code entered by the user. Returning
        # ``OTP_CANCEL_SENTINEL`` signals a user cancellation — the scraper must
        # abort without forwarding it to the provider (raise ``OtpCanceledError``).
        self.on_otp_request: Optional[Callable[[], Awaitable[str]]] = None
        # Optional human-readable detail a subclass can set when login fails, so
        # a general/unknown login failure surfaces the real reason (e.g. the
        # provider's HTTP error body) instead of a generic message.
        self._login_error_detail: Optional[str] = None

    async def scrape(self) -> ScrapingResult:
        """Orchestrate the full scraping lifecycle.

        Returns
        -------
        ScrapingResult
            Result containing accounts data on success, or error info on failure.
        """
        self._emit_progress("initializing")
        try:
            await self.initialize()
        except Exception as e:
            logger.error("Failed to initialize scraper for %s: %s", self.provider, e)
            return ScrapingResult(
                success=False,
                error_type="INIT_ERROR",
                error_message=str(e),
            )

        self._emit_progress("logging in")
        try:
            login_result = await self.login()
        except asyncio.TimeoutError:
            logger.error("Login timed out for %s", self.provider)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type="TIMEOUT",
                error_message=f"Login timed out for {self.provider}",
            )
        except ScraperError as e:
            logger.error("Login failed for %s: %s", self.provider, e)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type=e.error_type.value,
                error_message=str(e) or f"Login failed for {self.provider}",
            )
        except Exception as e:
            logger.error("Login failed for %s: %s", self.provider, e)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type="GENERAL_ERROR",
                error_message=str(e),
            )

        scraping_result = self._login_result_to_scraping_result(login_result)
        if scraping_result is not None:
            await self._safe_terminate(False)
            return scraping_result

        self._emit_progress("fetching data")
        try:
            accounts = await self.fetch_data()
        except asyncio.TimeoutError:
            logger.error("Data fetch timed out for %s", self.provider)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type="TIMEOUT",
                error_message=f"Data fetch timed out for {self.provider}",
            )
        except ScraperError as e:
            logger.error("Data fetch failed for %s: %s", self.provider, e)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type=e.error_type.value,
                error_message=str(e) or f"Data fetch failed for {self.provider}",
            )
        except Exception as e:
            logger.error("Data fetch failed for %s: %s", self.provider, e)
            await self._safe_terminate(False)
            return ScrapingResult(
                success=False,
                error_type="GENERAL_ERROR",
                error_message=str(e),
            )

        await self._safe_terminate(True)
        self._emit_progress("done")
        return ScrapingResult(success=True, accounts=accounts)

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize scraper resources (browser, HTTP client, etc.)."""

    @abstractmethod
    async def login(self) -> LoginResult:
        """Authenticate with the financial institution.

        Returns
        -------
        LoginResult
            The outcome of the login attempt.
        """

    @abstractmethod
    async def fetch_data(self) -> list[AccountResult]:
        """Fetch transaction data after successful login.

        Returns
        -------
        list[AccountResult]
            Account data with transactions.
        """

    async def terminate(self, success: bool) -> None:
        """Clean up resources. Override in subclasses for custom cleanup.

        Parameters
        ----------
        success : bool
            Whether the scraping completed successfully.
        """

    async def _safe_terminate(self, success: bool) -> None:
        """Call terminate with exception suppression."""
        try:
            await self.terminate(success)
        except Exception as e:
            logger.warning(
                "Error during terminate for %s: %s", self.provider, e
            )

    async def resend_otp(self) -> None:
        """Re-issue the OTP for a scraper currently awaiting one.

        The default implementation raises :class:`ResendNotSupportedError`.
        Providers whose OTP can be re-sent without restarting login (an
        interactive SMS flow like OneZero) override this to re-request the
        code, updating any provider-side OTP context in place. Browser-driven
        providers leave this default, and the backend falls back to aborting
        and relaunching the scrape.

        Raises
        ------
        ResendNotSupportedError
            Always, unless a subclass overrides this method.
        """
        raise ResendNotSupportedError(
            f"{self.provider} does not support resending the OTP in place"
        )

    def _emit_progress(self, message: str) -> None:
        """Call the progress callback if one is set."""
        if self.on_progress is not None:
            self.on_progress(message)

    def _login_result_to_scraping_result(
        self, result: LoginResult
    ) -> ScrapingResult | None:
        """Map a failed LoginResult to a ScrapingResult.

        Returns None if login was successful (caller should proceed to fetch).
        """
        if result == LoginResult.SUCCESS:
            return None

        error_mapping = {
            LoginResult.INVALID_PASSWORD: "INVALID_PASSWORD",
            LoginResult.CHANGE_PASSWORD: "CHANGE_PASSWORD",
            LoginResult.ACCOUNT_BLOCKED: "ACCOUNT_BLOCKED",
            LoginResult.UNKNOWN_ERROR: "GENERAL_ERROR",
        }
        error_type = error_mapping.get(result, "GENERAL_ERROR")
        if error_type == "GENERAL_ERROR" and self._login_error_detail:
            error_message = self._login_error_detail
        else:
            error_message = f"Login failed with result: {result.value}"
        return ScrapingResult(
            success=False,
            error_type=error_type,
            error_message=error_message,
        )
