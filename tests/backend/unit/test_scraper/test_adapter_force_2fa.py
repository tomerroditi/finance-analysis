"""Tests for long-term OTP token persistence in ScraperAdapter."""

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
    """Persist a fresh long-term token whenever a scrape produces one."""

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

    def test_persists_on_a_first_connect_too(self):
        """An unforced run that mints a token still persists it.

        A first connect has no stored token and no ``force_2fa``, so the
        scraper runs the interactive SMS flow and produces one. This method is
        the only writer of ``otpLongTermToken`` — the credential form has no
        such field — so skipping the write here meant every subsequent scrape
        re-sent an SMS.
        """
        adapter = _adapter(force_2fa=False)
        scraper = SimpleNamespace(refreshed_otp_long_term_token="NEW")
        mock_repo = MagicMock()
        with patch(
            "backend.scraper.adapter.CredentialsRepository", return_value=mock_repo
        ), patch("backend.scraper.adapter.get_db_context") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = MagicMock()
            adapter._persist_refreshed_otp_token(scraper)

        assert mock_repo.save_credentials.call_args.args[3]["otpLongTermToken"] == "NEW"

    def test_no_persist_when_the_token_is_unchanged(self):
        """A token identical to the stored one skips the Keyring write."""
        adapter = ScraperAdapter(
            "banks", "onezero", "Acc",
            {"email": "e", "password": "p", "otpLongTermToken": "SAME"},
            date.today(), 1, force_2fa=False,
        )
        scraper = SimpleNamespace(refreshed_otp_long_term_token="SAME")
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


class TestTokenSurvivesAFailedScrape:
    """A token minted at login is kept even when the scrape later fails."""

    def test_persist_runs_from_the_finally_block(self):
        """The call sits in `finally`, not behind `if result.success`.

        Login mints the token; fetch_data can fail afterwards for reasons that
        have nothing to do with authentication (a provider 500, the 5-minute
        timeout). Discarding the token there cost the user another SMS on the
        next run, and every wasted SMS walks them toward the provider's own
        rate limit.
        """
        import inspect

        source = inspect.getsource(ScraperAdapter.run)
        finally_body = source.split("finally:", 1)[1]

        assert "_persist_refreshed_otp_token" in finally_body, (
            "token persistence must run in the finally block so it survives a "
            "failed or timed-out scrape"
        )
        # And nowhere else — a second call behind the success branch would
        # reintroduce the coupling this guards against.
        assert source.count("self._persist_refreshed_otp_token") == 1
