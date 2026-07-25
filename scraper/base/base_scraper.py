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


def describe_exception(exc: BaseException) -> str:
    """Render an exception as ``ClassName: message``, or the class name alone.

    ``str(exc)`` is ``""`` for an argument-less ``raise SomeError``, so storing it
    directly yields an error record indistinguishable from "nothing was
    recorded". The class name is often the whole diagnosis (``TimeoutError`` vs
    ``KeyError`` vs ``JSONDecodeError``), so it is always kept.

    Parameters
    ----------
    exc : BaseException
        The exception to describe.

    Returns
    -------
    str
        ``"ClassName: message"``, or just ``"ClassName"`` when the exception
        carries no message.
    """
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


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
        # Human-readable detail describing *why* login failed — the provider's
        # HTTP error body, the exception text, the unexpected landing URL. Set
        # it via `_fail_login`; `_login_result_to_scraping_result` folds it into
        # the recorded error message so the scraping-history row carries the
        # real reason rather than just the LoginResult label.
        self._login_error_detail: Optional[str] = None

    async def scrape(self) -> ScrapingResult:
        """Orchestrate the full scraping lifecycle.

        Returns
        -------
        ScrapingResult
            Result containing accounts data on success, or error info on failure.
        """
        # Each phase reports failures the same way: "<phase> failed: <detail>",
        # where the detail always names the exception class. Previously these
        # handlers stored a bare `str(e)`, so an argument-less exception recorded
        # an empty message and the phase it died in was only in the log.
        self._emit_progress("initializing")
        try:
            await self.initialize()
        except Exception as e:
            return self._phase_failure("initialize", "INIT_ERROR", e, terminate=False)

        self._emit_progress("logging in")
        try:
            login_result = await self.login()
        except asyncio.TimeoutError as e:
            return await self._phase_failure_async("login", "TIMEOUT", e)
        except ScraperError as e:
            return await self._phase_failure_async("login", e.error_type.value, e)
        except Exception as e:
            return await self._phase_failure_async("login", "GENERAL_ERROR", e)

        scraping_result = self._login_result_to_scraping_result(login_result)
        if scraping_result is not None:
            await self._safe_terminate(False)
            return scraping_result

        self._emit_progress("fetching data")
        try:
            accounts = await self.fetch_data()
        except asyncio.TimeoutError as e:
            return await self._phase_failure_async("fetch data", "TIMEOUT", e)
        except ScraperError as e:
            return await self._phase_failure_async(
                "fetch data", e.error_type.value, e
            )
        except Exception as e:
            return await self._phase_failure_async("fetch data", "GENERAL_ERROR", e)

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

    def _phase_failure(
        self,
        phase: str,
        error_type: str,
        exc: BaseException,
        terminate: bool = True,
    ) -> ScrapingResult:
        """Log and build the ScrapingResult for a failed lifecycle phase.

        Parameters
        ----------
        phase : str
            Which phase died — ``"initialize"``, ``"login"``, ``"fetch data"``.
            Recorded in the message so a failure is placed in the lifecycle
            without cross-referencing the log.
        error_type : str
            Failure category for the record.
        exc : BaseException
            The exception that ended the phase.
        terminate : bool, optional
            Unused here; see :meth:`_phase_failure_async`, which awaits cleanup.
            Present so both share one signature.

        Returns
        -------
        ScrapingResult
            A failed result carrying the category and a described exception.
        """
        del terminate  # cleanup is the async variant's job
        detail = describe_exception(exc)
        logger.error(
            "%s failed for %s: [%s] %s", phase, self.provider, error_type, detail
        )
        return ScrapingResult(
            success=False,
            error_type=error_type,
            error_message=f"{phase} failed: {detail}",
        )

    async def _phase_failure_async(
        self, phase: str, error_type: str, exc: BaseException
    ) -> ScrapingResult:
        """Terminate the scraper, then build the failed result for ``phase``.

        Parameters
        ----------
        phase : str
            Which phase died.
        error_type : str
            Failure category for the record.
        exc : BaseException
            The exception that ended the phase.

        Returns
        -------
        ScrapingResult
            A failed result carrying the category and a described exception.
        """
        result = self._phase_failure(phase, error_type, exc)
        await self._safe_terminate(False)
        return result

    def _fail_login(
        self, result: LoginResult, detail: str | BaseException
    ) -> LoginResult:
        """Record why login failed and return the result to hand back.

        Written to be used inline — ``return self._fail_login(
        LoginResult.UNKNOWN_ERROR, exc)`` — so attaching the real reason is a
        single expression at the failure site. Without this, most providers
        returned a bare ``LoginResult`` and the only record of the actual cause
        was a ``logger.error`` line in the uvicorn log; the scraping-history row
        the UI reads got the enum label and nothing else.

        Parameters
        ----------
        result : LoginResult
            The login outcome to return.
        detail : str or BaseException
            The real reason. Exceptions are rendered as
            ``ClassName: message`` so an empty-message exception still says
            something useful.

        Returns
        -------
        LoginResult
            ``result``, unchanged.
        """
        if isinstance(detail, BaseException):
            detail = describe_exception(detail)
        self._login_error_detail = detail or None
        return result

    def _login_result_to_scraping_result(
        self, result: LoginResult
    ) -> ScrapingResult | None:
        """Map a failed LoginResult to a ScrapingResult.

        The message always leads with the ``LoginResult`` label and appends the
        recorded detail, so the stored text is both classifiable and actually
        diagnostic. When a provider reported no detail we say so explicitly
        rather than implying the label *was* the provider's message — that
        ambiguity is what made a bare "Login failed with result: unknown_error"
        look like it came from the bank when it was entirely ours.

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
        detail = (self._login_error_detail or "").strip()
        error_message = (
            f"login {result.value}: {detail}"
            if detail
            else f"login {result.value}: no detail reported by the "
            f"{self.provider} scraper"
        )
        return ScrapingResult(
            success=False,
            error_type=error_type,
            error_message=error_message,
        )
