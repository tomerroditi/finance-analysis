"""Tests for scraper adapter 2FA (Two-Factor Authentication) functionality."""

import asyncio
import datetime

from backend.scraper import ScraperAdapter


DUMMY_ACCOUNT = "test_account"
DUMMY_CREDENTIALS = {"email": "test@test.com", "password": "pass123"}
DUMMY_START_DATE = datetime.date(2025, 1, 1)
DUMMY_PROCESS_ID = 42


class TestAdapter2FA:
    """Tests for 2FA-related adapter methods."""

    def test_otp_event_initially_unset(self):
        """Verify that the OTP event starts in an unset state."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        assert not adapter._otp_event.is_set()

    def test_set_otp_code_sets_event(self):
        """Verify that set_otp_code triggers the OTP event."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        adapter.set_otp_code("123456")
        assert adapter._otp_event.is_set()

    def test_set_otp_code_stores_code(self):
        """Verify that the OTP code is stored on the adapter instance."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        adapter.set_otp_code("789012")
        assert adapter._otp_code == "789012"

    def test_cancel_sets_cancel_constant(self):
        """Verify that setting 'cancel' as OTP code triggers cancellation."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )
        adapter.set_otp_code("cancel")
        assert adapter._otp_code == adapter.CANCEL

    def test_otp_callback_returns_code(self):
        """Verify async OTP callback returns the set code."""
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )

        async def run():
            # Set code in a separate task
            async def set_code():
                await asyncio.sleep(0.05)
                adapter.set_otp_code("654321")

            asyncio.create_task(set_code())
            return await adapter._otp_callback()

        code = asyncio.run(run())
        assert code == "654321"
