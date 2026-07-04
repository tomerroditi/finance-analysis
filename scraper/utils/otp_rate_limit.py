"""Rate limiting for OTP ``/otp/prepare`` requests.

OneZero's OTP flow does ``/otp/prepare`` (sends an SMS and mints an
``otpContext``) then ``/otp/verify``. Firing several prepares in quick
succession for the same phone number trips the SMS provider's (Twilio)
fraud filter, which temporarily blocks the phone-number prefix — and each
new prepare supersedes the previous one, invalidating any code already in
flight to the user.

This module enforces two independent limits per phone number:

- A minimum interval between consecutive prepares
  (``OTP_PREPARE_MIN_INTERVAL_SECONDS``).
- A maximum number of prepares within a rolling window
  (``OTP_PREPARE_MAX_PER_WINDOW`` per ``OTP_PREPARE_WINDOW_SECONDS``).
"""

import time
from typing import Callable

OTP_PREPARE_MIN_INTERVAL_SECONDS = 60
OTP_PREPARE_MAX_PER_WINDOW = 3
OTP_PREPARE_WINDOW_SECONDS = 900


class OtpRateLimitError(Exception):
    """Raised when an OTP prepare request violates the rate limit."""


class OtpPrepareRateLimiter:
    """Tracks OTP prepare timestamps per phone number and enforces limits.

    Parameters
    ----------
    clock : Callable[[], float], optional
        Zero-argument callable returning the current time in seconds.
        Defaults to :func:`time.monotonic`. Tests inject a fake clock to
        deterministically advance time without real sleeps.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._history: dict[str, list[float]] = {}

    def check_and_record(self, phone_number: str) -> None:
        """Validate a prepare request for ``phone_number`` and record it.

        Enforces both the minimum-interval and window-cap rules. On
        violation, raises :class:`OtpRateLimitError` without recording a
        new timestamp — only genuinely accepted prepares count toward
        either limit. On success, prunes timestamps older than the
        rolling window and records the current one.

        Parameters
        ----------
        phone_number : str
            The phone number the prepare request targets. Used as the
            rate-limit bucket key.

        Raises
        ------
        OtpRateLimitError
            If a prepare was recorded for this phone within
            ``OTP_PREPARE_MIN_INTERVAL_SECONDS``, or if
            ``OTP_PREPARE_MAX_PER_WINDOW`` prepares already occurred within
            ``OTP_PREPARE_WINDOW_SECONDS``.
        """
        now = self._clock()
        timestamps = self._history.get(phone_number, [])

        # Prune stale entries before evaluating the window cap so an old
        # burst can't keep blocking forever.
        window_start = now - OTP_PREPARE_WINDOW_SECONDS
        timestamps = [ts for ts in timestamps if ts > window_start]

        if timestamps:
            seconds_since_last = now - timestamps[-1]
            if seconds_since_last < OTP_PREPARE_MIN_INTERVAL_SECONDS:
                raise OtpRateLimitError(
                    "Too many verification-code requests for this number. "
                    "Wait about a minute before requesting another code."
                )

        if len(timestamps) >= OTP_PREPARE_MAX_PER_WINDOW:
            raise OtpRateLimitError(
                "Too many verification-code requests for this number. "
                "Please wait a while before trying again."
            )

        timestamps.append(now)
        self._history[phone_number] = timestamps

    def reset(self) -> None:
        """Clear all recorded prepare history for every phone number."""
        self._history.clear()


otp_prepare_rate_limiter = OtpPrepareRateLimiter()
