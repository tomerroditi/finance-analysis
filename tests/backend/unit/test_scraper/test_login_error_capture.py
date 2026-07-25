"""Tests for capturing why a browser-driven login failed.

A browser provider signals failure by the page it lands on and the error box it
renders — Max detects its unknown-error case by locating the very element that
holds Max's message. That text was read to decide the outcome and then thrown
away, so the recorded failure was a bare enum label with no trace of what the
bank actually said.
"""

import asyncio

from scraper.base.base_scraper import describe_exception
from scraper.base.browser_scraper import _redact_url
from scraper.models.result import LoginResult


class _FakePage:
    """Minimal Playwright page stand-in for login-result detection."""

    def __init__(self, url: str, error_texts: list[str] | None = None,
                 raises: bool = False):
        self.url = url
        self._error_texts = error_texts or []
        self._raises = raises

    async def evaluate(self, _script, *_args, **_kwargs):
        """Return the stubbed error-container texts."""
        if self._raises:
            raise RuntimeError("Execution context was destroyed")
        return list(self._error_texts)


def _scraper(page: _FakePage):
    """Build a BrowserScraper with its page swapped for a fake.

    BrowserScraper.__init__ builds no Playwright state, so assigning `page` is
    enough to exercise `_detect_login_result` without launching a browser.
    """
    from scraper.base.browser_scraper import BrowserScraper

    class _Concrete(BrowserScraper):
        async def login(self):
            return LoginResult.SUCCESS

        async def fetch_data(self):
            return []

    scraper = _Concrete("max", {}, None)
    scraper.page = page
    return scraper


def _detect(scraper, possible_results):
    """Run the async detection helper synchronously."""
    return asyncio.run(scraper._detect_login_result(possible_results))


class TestDescribeException:
    """Tests for the shared exception renderer used by every failure path."""

    def test_message_is_prefixed_with_the_class(self):
        """The class name is kept — it is often the whole diagnosis."""
        assert describe_exception(ValueError("bad json")) == "ValueError: bad json"

    def test_empty_message_yields_the_class_name_alone(self):
        """A bare `raise SomeError` must not render as an empty string.

        `str(exc)` is "" there, so storing it directly produced an error record
        indistinguishable from "nothing was recorded".
        """
        assert describe_exception(KeyError()) == "KeyError"

    def test_whitespace_only_message_is_treated_as_empty(self):
        """A message of blanks is no more informative than none."""
        assert describe_exception(RuntimeError("   ")) == "RuntimeError"


class TestPhaseFailures:
    """Tests for how a failed lifecycle phase is recorded.

    `scrape()`'s init and fetch handlers stored a bare `str(e)`, so the phase a
    scrape died in lived only in the log, and an argument-less exception was
    recorded as an empty message.
    """

    def _scraper(self, **kwargs):
        """Build a stub scraper whose lifecycle methods can be made to raise."""
        from scraper.base.base_scraper import BaseScraper

        class _Stub(BaseScraper):
            async def initialize(self):
                if "init" in kwargs:
                    raise kwargs["init"]

            async def login(self):
                if "login" in kwargs:
                    raise kwargs["login"]
                return LoginResult.SUCCESS

            async def fetch_data(self):
                if "fetch" in kwargs:
                    raise kwargs["fetch"]
                return []

        return _Stub("onezero", {}, None)

    def test_fetch_failure_names_the_phase_and_the_exception_class(self):
        """A fetch-stage crash says both where it died and what was raised."""
        result = asyncio.run(self._scraper(fetch=ValueError("bad payload")).scrape())

        assert result.success is False
        assert result.error_type == "GENERAL_ERROR"
        assert result.error_message == "fetch data failed: ValueError: bad payload"

    def test_fetch_failure_with_no_message_still_records_the_class(self):
        """An argument-less exception no longer records an empty message."""
        result = asyncio.run(self._scraper(fetch=KeyError()).scrape())

        assert result.error_message == "fetch data failed: KeyError"

    def test_init_failure_is_attributed_to_initialize(self):
        """An init crash is distinguishable from a login or fetch crash."""
        result = asyncio.run(self._scraper(init=OSError("no browser")).scrape())

        assert result.error_type == "INIT_ERROR"
        assert result.error_message == "initialize failed: OSError: no browser"

    def test_login_crash_is_attributed_to_login(self):
        """A login crash (raised, not returned) names the login phase."""
        result = asyncio.run(self._scraper(login=RuntimeError("boom")).scrape())

        assert result.error_type == "GENERAL_ERROR"
        assert result.error_message == "login failed: RuntimeError: boom"

    def test_timeout_keeps_its_own_category(self):
        """A timeout is categorised as TIMEOUT, not folded into GENERAL_ERROR."""
        result = asyncio.run(self._scraper(fetch=asyncio.TimeoutError()).scrape())

        assert result.error_type == "TIMEOUT"
        assert "fetch data failed" in result.error_message

    def test_scraper_error_keeps_its_declared_category(self):
        """A typed ScraperError's own category survives."""
        from scraper.exceptions import CredentialsError

        result = asyncio.run(
            self._scraper(login=CredentialsError("rejected")).scrape()
        )

        assert result.error_type == "INVALID_PASSWORD"
        assert "rejected" in result.error_message


class TestRedactUrl:
    """Tests for stripping secrets out of a URL before it is recorded."""

    def test_query_string_is_dropped(self):
        """A login redirect's query can carry tokens — it must not be stored."""
        assert (
            _redact_url("https://bank.test/login?code=SECRET&state=abc")
            == "https://bank.test/login?…"
        )

    def test_fragment_is_dropped(self):
        """OAuth implicit flows put tokens in the fragment."""
        assert (
            _redact_url("https://bank.test/cb#access_token=SECRET")
            == "https://bank.test/cb?…"
        )

    def test_plain_url_is_untouched(self):
        """Without a query or fragment the URL passes through unchanged."""
        assert _redact_url("https://bank.test/login") == "https://bank.test/login"

    def test_non_url_input_is_returned_as_is(self):
        """A non-URL string is not mangled into a bogus scheme."""
        assert _redact_url("about:blank") == "about:blank"


class TestDetectedFailureCapturesContext:
    """A matched failure records where it happened and what the page said."""

    def test_matched_failure_captures_the_providers_message(self):
        """Max's own error text ends up in the recorded detail."""
        page = _FakePage(
            "https://max.test/login",
            ["Your card details are incorrect"],
        )
        scraper = _scraper(page)

        result = _detect(
            scraper,
            {LoginResult.INVALID_PASSWORD: ["max.test/login"]},
        )

        assert result is LoginResult.INVALID_PASSWORD
        assert "Your card details are incorrect" in scraper._login_error_detail

    def test_success_records_no_detail(self):
        """A successful login must not leave a stale failure detail behind."""
        page = _FakePage("https://max.test/home", ["ignored"])
        scraper = _scraper(page)

        result = _detect(scraper, {LoginResult.SUCCESS: ["max.test/home"]})

        assert result is LoginResult.SUCCESS
        assert scraper._login_error_detail is None

    def test_no_match_records_the_landing_url(self):
        """Every check missing is the classic contentless unknown_error."""
        page = _FakePage("https://max.test/somewhere-new?token=SECRET")
        scraper = _scraper(page)

        result = _detect(scraper, {LoginResult.SUCCESS: ["max.test/home"]})

        assert result is LoginResult.UNKNOWN_ERROR
        detail = scraper._login_error_detail
        assert "no login-result check matched" in detail
        assert "https://max.test/somewhere-new" in detail
        # The token must not be written to the DB along with the path.
        assert "SECRET" not in detail

    def test_duplicate_nested_error_text_is_collapsed(self):
        """Nested error containers repeat their child's text; report it once."""
        page = _FakePage(
            "https://max.test/login",
            ["Wrong password", "Wrong password", "  Wrong password  "],
        )
        scraper = _scraper(page)

        _detect(scraper, {LoginResult.INVALID_PASSWORD: ["login"]})

        assert scraper._login_error_detail.count("Wrong password") == 1

    def test_unreadable_page_still_records_the_url(self):
        """A page that can't be evaluated must not lose the URL too.

        `evaluate` raises when the context is destroyed by a navigation racing
        the check — that is exactly when a diagnostic is most wanted.
        """
        page = _FakePage("https://max.test/login", raises=True)
        scraper = _scraper(page)

        result = _detect(scraper, {LoginResult.SUCCESS: ["max.test/home"]})

        assert result is LoginResult.UNKNOWN_ERROR
        assert "https://max.test/login" in scraper._login_error_detail

    def test_recorded_detail_reaches_the_scraping_result(self):
        """The captured text is what a failed scrape ends up reporting."""
        page = _FakePage("https://max.test/login", ["Account locked"])
        scraper = _scraper(page)

        _detect(scraper, {LoginResult.ACCOUNT_BLOCKED: ["login"]})
        result = scraper._login_result_to_scraping_result(
            LoginResult.ACCOUNT_BLOCKED
        )

        assert result.error_type == "ACCOUNT_BLOCKED"
        assert "Account locked" in result.error_message
