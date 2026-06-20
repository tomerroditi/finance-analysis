"""Tests for scraper adapter, factory function, and 2FA requirement checks."""



from scraper.base.base_scraper import BaseScraper, ScraperOptions
from scraper.models.result import LoginResult, ScrapingResult
from scraper.models.account import AccountResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType

from backend.scraper import ScraperAdapter, is_2fa_required


class _StubScraper(BaseScraper):
    """Minimal concrete BaseScraper used to exercise base-class behavior."""

    async def initialize(self) -> None:
        """No-op initialization."""

    async def login(self) -> LoginResult:
        """Report success; individual tests drive the mapping helper directly."""
        return LoginResult.SUCCESS

    async def fetch_data(self) -> list:
        """Return no accounts."""
        return []


DUMMY_ACCOUNT = "test_account"
DUMMY_CREDENTIALS = {"username": "test", "password": "pass123"}
DUMMY_START_DATE = __import__("datetime").date(2025, 1, 1)
DUMMY_PROCESS_ID = 42


class TestIs2FARequired:
    """Tests for the is_2fa_required helper function."""

    def test_onezero_requires_2fa(self):
        """Verify onezero bank provider requires 2FA."""
        assert is_2fa_required("banks", "onezero") is True

    def test_hapoalim_requires_2fa(self):
        """Hapoalim is 2FA-capable: the bank sometimes asks for an SMS code.

        The scraper resolves dynamically whether 2FA is needed for a given
        run; the registry just needs to know an OTP *may* be requested.
        """
        assert is_2fa_required("banks", "hapoalim") is True

    def test_max_no_2fa(self):
        """Verify max credit card provider does not require 2FA."""
        assert is_2fa_required("credit_cards", "max") is False

    def test_unknown_provider_no_2fa(self):
        """Verify unknown provider returns False."""
        assert is_2fa_required("banks", "nonexistent") is False


class TestScraperAdapterAttributes:
    """Tests for ScraperAdapter initialization and attributes."""

    def test_adapter_init(self):
        """Verify adapter initializes with correct attributes."""
        adapter = ScraperAdapter(
            "banks", "hapoalim", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        assert adapter.service_name == "banks"
        assert adapter.provider_name == "hapoalim"
        assert adapter.account_name == DUMMY_ACCOUNT
        assert adapter.credentials == DUMMY_CREDENTIALS
        assert adapter.process_id == DUMMY_PROCESS_ID

    def test_cancel_constant(self):
        """Verify the CANCEL constant is set to 'cancel'."""
        assert ScraperAdapter.CANCEL == "cancel"

    def test_set_otp_code_signals_event(self):
        """Verify set_otp_code stores the code and signals the event."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        assert not adapter._otp_event.is_set()
        adapter.set_otp_code("123456")
        assert adapter._otp_code == "123456"
        assert adapter._otp_event.is_set()

    def test_set_otp_cancel(self):
        """Verify setting cancel code works correctly."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        adapter.set_otp_code("cancel")
        assert adapter._otp_code == ScraperAdapter.CANCEL


class TestScraperAdapterDataConversion:
    """Tests for ScraperAdapter result-to-DataFrame conversion."""

    def test_result_to_dataframe_empty(self):
        """Verify empty result produces empty DataFrame."""
        adapter = ScraperAdapter(
            "banks", "hapoalim", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        result = ScrapingResult(success=True, accounts=[])
        df = adapter._result_to_dataframe(result, "banks")
        assert df.empty

    def test_result_to_dataframe_with_transactions(self):
        """Verify transactions are correctly mapped to DataFrame columns."""
        txn = Transaction(
            type=TransactionType.NORMAL,
            status=TransactionStatus.COMPLETED,
            date="2025-01-15",
            processed_date="2025-01-15",
            original_amount=-100.0,
            original_currency="ILS",
            charged_amount=-100.0,
            description="Test Transaction",
            identifier="txn_001",
        )
        account = AccountResult(
            account_number="12345",
            transactions=[txn],
            balance=5000.0,
        )
        result = ScrapingResult(success=True, accounts=[account])

        adapter = ScraperAdapter(
            "banks", "hapoalim", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        df = adapter._result_to_dataframe(result, "banks")

        assert len(df) == 1
        row = df.iloc[0]
        assert row["id"] == "txn_001"
        assert row["date"] == "2025-01-15"
        assert row["amount"] == -100.0
        assert row["description"] == "Test Transaction"
        assert row["account_number"] == "12345"
        assert row["provider"] == "hapoalim"
        assert row["account_name"] == DUMMY_ACCOUNT
        assert row["source"] == "bank_transactions"


class TestLoginErrorDetail:
    """Tests for surfacing the login error detail in the scraping result."""

    def _scraper(self) -> _StubScraper:
        """Build a stub scraper for mapping tests."""
        return _StubScraper("onezero", DUMMY_CREDENTIALS, ScraperOptions())

    def test_general_error_uses_login_detail_when_set(self):
        """A general/unknown failure surfaces the detail as the error message."""
        scraper = self._scraper()
        scraper._login_error_detail = "HTTP 503 /otp/prepare — body: blocked prefix"
        result = scraper._login_result_to_scraping_result(LoginResult.UNKNOWN_ERROR)
        assert result.error_type == "GENERAL_ERROR"
        assert result.error_message == "HTTP 503 /otp/prepare — body: blocked prefix"

    def test_general_error_falls_back_to_generic_when_no_detail(self):
        """Without a recorded detail, the generic message is used."""
        scraper = self._scraper()
        result = scraper._login_result_to_scraping_result(LoginResult.UNKNOWN_ERROR)
        assert result.error_message == "Login failed with result: unknown_error"

    def test_known_error_type_keeps_generic_message(self):
        """A known failure type keeps its generic message even if a detail is set."""
        scraper = self._scraper()
        scraper._login_error_detail = "some noisy detail"
        result = scraper._login_result_to_scraping_result(LoginResult.INVALID_PASSWORD)
        assert result.error_type == "INVALID_PASSWORD"
        assert result.error_message == "Login failed with result: invalid_password"

    def test_success_returns_none(self):
        """A successful login maps to None so the caller proceeds to fetch."""
        scraper = self._scraper()
        assert scraper._login_result_to_scraping_result(LoginResult.SUCCESS) is None
