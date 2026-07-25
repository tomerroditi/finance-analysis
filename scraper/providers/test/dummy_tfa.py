import asyncio

from scraper.base import OTP_CANCEL_SENTINEL
from scraper.models.result import LoginResult
from scraper.providers.test.dummy_regular import DummyRegularScraper


class DummyTFAScraper(DummyRegularScraper):
    """Test scraper that simulates two-factor authentication via OTP.

    Requires an ``on_otp_request`` callback to be set before scraping.
    Accepts any OTP code except "cancel", which triggers an error.
    """

    async def login(self) -> LoginResult:
        """Simulate login with OTP two-factor authentication.

        Returns
        -------
        LoginResult
            SUCCESS if a valid OTP code is provided, UNKNOWN_ERROR otherwise.
        """
        await asyncio.sleep(1)

        if self.on_otp_request is None:
            return self._fail_login(
                LoginResult.UNKNOWN_ERROR,
                "no code prompt was available (on_otp_request callback not set)",
            )

        self._emit_progress("Waiting for OTP code")
        otp_code = await self.on_otp_request()

        if otp_code == OTP_CANCEL_SENTINEL:
            return self._fail_login(
                LoginResult.UNKNOWN_ERROR,
                "two-factor authentication canceled by the user",
            )

        return LoginResult.SUCCESS

    async def resend_otp(self) -> None:
        """Simulate an in-place OTP resend (no-op).

        Overrides the base ``ResendNotSupportedError`` so demo-mode e2e can
        exercise the "resend in place" path. No real SMS is sent and no
        state changes — the dummy login accepts any subsequently submitted
        code.
        """
        self._emit_progress("Resent OTP code")
