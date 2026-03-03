import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable, Optional

from scraper.models.account import AccountResult
from scraper.models.result import LoginResult, ScrapingResult

logger = logging.getLogger(__name__)


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
        self.on_otp_request: Optional[Callable[[], Awaitable[str]]] = None

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
        return ScrapingResult(
            success=False,
            error_type=error_type,
            error_message=f"Login failed with result: {result.value}",
        )
