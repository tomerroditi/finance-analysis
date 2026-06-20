"""Tests for force-2FA token persistence in ScraperAdapter."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.scraper.adapter import ScraperAdapter


def _adapter(force_2fa: bool) -> ScraperAdapter:
    """Build an adapter with representative OneZero credentials."""
    return ScraperAdapter(
        "banks", "onezero", "Acc",
        {"email": "e", "password": "p", "phoneNumber": "+1"},
        date.today(), 1, force_2fa=force_2fa,
    )


class TestPersistRefreshedOtpToken:
    """Persist the fresh long-term token only on a forced run that produced one."""

    def test_persists_merged_credentials_on_forced_run(self):
        """Forced run + fresh token → save_credentials with the merged creds."""
        adapter = _adapter(force_2fa=True)
        scraper = SimpleNamespace(refreshed_otp_long_term_token="NEW")
        mock_repo = MagicMock()
        with patch(
            "backend.scraper.adapter.CredentialsRepository", return_value=mock_repo
        ), patch("backend.scraper.adapter.get_db_context") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            adapter._persist_refreshed_otp_token(scraper)

        mock_repo.save_credentials.assert_called_once()
        args = mock_repo.save_credentials.call_args.args
        assert args[0:3] == ("banks", "onezero", "Acc")
        saved = args[3]
        assert saved["otpLongTermToken"] == "NEW"
        assert saved["email"] == "e"  # original fields preserved (not wiped)

    def test_no_persist_when_not_forced(self):
        """A non-forced run never persists, even if a token was produced."""
        adapter = _adapter(force_2fa=False)
        scraper = SimpleNamespace(refreshed_otp_long_term_token="NEW")
        with patch("backend.scraper.adapter.CredentialsRepository") as MockRepo:
            adapter._persist_refreshed_otp_token(scraper)
        MockRepo.assert_not_called()

    def test_no_persist_when_no_token(self):
        """A forced run with no fresh token does nothing."""
        adapter = _adapter(force_2fa=True)
        scraper = SimpleNamespace(refreshed_otp_long_term_token=None)
        with patch("backend.scraper.adapter.CredentialsRepository") as MockRepo:
            adapter._persist_refreshed_otp_token(scraper)
        MockRepo.assert_not_called()

    def test_persist_failure_is_swallowed(self):
        """A persistence error must not propagate (scrape result is unaffected)."""
        adapter = _adapter(force_2fa=True)
        scraper = SimpleNamespace(refreshed_otp_long_term_token="NEW")
        with patch(
            "backend.scraper.adapter.CredentialsRepository",
            side_effect=Exception("boom"),
        ), patch("backend.scraper.adapter.get_db_context"):
            adapter._persist_refreshed_otp_token(scraper)  # must not raise
