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

It also acts as a circuit breaker once the provider itself has blocked a
number: callers observing that block (see
``scraper.providers.banks.onezero._is_sms_provider_block``) call
``record_provider_block`` to arm a per-phone cooldown
(``OTP_BLOCK_COOLDOWN_SECONDS``), so we stop attempting ``/otp/prepare``
for that number until the cooldown elapses — hammering an already-blocked
number can prolong the provider-side block.
"""

import re
import time
from typing import Callable

OTP_PREPARE_MIN_INTERVAL_SECONDS = 60
OTP_PREPARE_MAX_PER_WINDOW = 3
OTP_PREPARE_WINDOW_SECONDS = 900
OTP_BLOCK_COOLDOWN_SECONDS = 3600

OTP_PROVIDER_BLOCKED_MESSAGE = (
    "Your phone number is temporarily blocked by the bank's "
    "SMS provider (too many code requests). Please try "
    "again later."
)


def _normalize_phone(phone: str) -> str:
    """Normalize a phone number for use as a rate-limit bucket key.

    Strips whitespace, dashes, and parentheses so the same physical phone
    number stored with different formatting (e.g. ``"+1 555-123 4567"`` vs
    ``"+15551234567"``) collapses onto the same bucket — otherwise the
    per-phone caps split across buckets and the intended joint cap is
    weakened. Keeps the leading ``+`` and all digits, which is all that's
    needed to distinguish genuinely different numbers.

    This is purely an internal keying transform for ``_history`` /
    ``_blocked_until``: it must never be used for the value sent to the
    SMS provider, which needs the original, unmodified phone string.

    Parameters
    ----------
    phone : str
        The raw phone number as supplied by the caller.

    Returns
    -------
    str
        The phone number with whitespace, dashes, and parentheses removed.
    """
    return re.sub(r"[\s\-()]", "", phone)


class OtpRateLimitError(Exception):
    """Raised when an OTP prepare request violates the rate limit."""


class OtpProviderBlockedError(OtpRateLimitError):
    """Raised when the SMS provider itself has blocked the phone number.

    A subclass of :class:`OtpRateLimitError` so every existing
    ``except OtpRateLimitError`` handler (the resend route's
    ``BadRequestException`` mapping, ``login()``'s error surfacing) already
    handles it with no new wiring.
    """


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
        # NOTE: plain in-process dicts backing the module-level singleton
        # below — correct only within a single event loop / uvicorn worker
        # (see ``build/app_entry.py``). A multi-worker deployment would need
        # this moved to shared state (DB row, Redis) for the caps to hold.
        self._history: dict[str, list[float]] = {}
        self._blocked_until: dict[str, float] = {}

    def check_and_record(self, phone_number: str) -> None:
        """Validate a prepare request for ``phone_number`` and record it.

        First checks whether the provider itself has blocked this number
        (see :meth:`record_provider_block`); if so, raises
        :class:`OtpProviderBlockedError` immediately without touching the
        min-interval/window history. Otherwise enforces both the
        minimum-interval and window-cap rules. On violation, raises
        :class:`OtpRateLimitError` without recording a new timestamp —
        only genuinely accepted prepares count toward either limit. On
        success, prunes timestamps older than the rolling window and
        records the current one.

        Parameters
        ----------
        phone_number : str
            The phone number the prepare request targets. Used as the
            rate-limit bucket key.

        Raises
        ------
        OtpProviderBlockedError
            If the provider has blocked this phone number and the cooldown
            (``OTP_BLOCK_COOLDOWN_SECONDS``) has not yet elapsed.
        OtpRateLimitError
            If a prepare was recorded for this phone within
            ``OTP_PREPARE_MIN_INTERVAL_SECONDS``, or if
            ``OTP_PREPARE_MAX_PER_WINDOW`` prepares already occurred within
            ``OTP_PREPARE_WINDOW_SECONDS``.
        """
        # Normalize only for use as the internal dict key below — the
        # original, unmodified ``phone_number`` the caller passed in is
        # never touched or returned; callers still send that raw value to
        # the SMS provider.
        phone_number = _normalize_phone(phone_number)
        now = self._clock()

        blocked_until = self._blocked_until.get(phone_number)
        if blocked_until is not None:
            if blocked_until > now:
                raise OtpProviderBlockedError(OTP_PROVIDER_BLOCKED_MESSAGE)
            # Cooldown elapsed — prune the stale block entry.
            del self._blocked_until[phone_number]

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

    def record_provider_block(self, phone_number: str) -> None:
        """Arm a cooldown after the SMS provider blocks ``phone_number``.

        Called when the caller detects the provider itself has rejected
        the request (e.g. a Twilio SMS-block response), as opposed to our
        own min-interval/window limits. While the cooldown is active,
        :meth:`check_and_record` raises :class:`OtpProviderBlockedError`
        immediately, without consuming a min-interval/window slot.

        Parameters
        ----------
        phone_number : str
            The phone number the provider has blocked.
        """
        # Same internal-key-only normalization as check_and_record — must
        # land in the same bucket regardless of how this phone number is
        # formatted elsewhere.
        phone_number = _normalize_phone(phone_number)
        self._blocked_until[phone_number] = self._clock() + OTP_BLOCK_COOLDOWN_SECONDS

    def reset(self) -> None:
        """Clear all recorded prepare history and provider blocks."""
        self._history.clear()
        self._blocked_until.clear()


otp_prepare_rate_limiter = OtpPrepareRateLimiter()
