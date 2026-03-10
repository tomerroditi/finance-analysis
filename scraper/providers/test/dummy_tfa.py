import asyncio

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
            return LoginResult.UNKNOWN_ERROR

        self._emit_progress("Waiting for OTP code")
        otp_code = await self.on_otp_request()

        if otp_code == "cancel":
            return LoginResult.UNKNOWN_ERROR

        return LoginResult.SUCCESS
