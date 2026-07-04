"""Tests for the OTP prepare rate limiter.

Guards against duplicate ``/otp/prepare`` bursts that trip the provider's
(Twilio) fraud filter — see ``.claude/rules`` and
``docs/superpowers/plans/onezero-otp-hardening.md`` for the incident this
hardens against.
"""

import pytest

from scraper.utils.otp_rate_limit import (
    OTP_BLOCK_COOLDOWN_SECONDS,
    OTP_PREPARE_MAX_PER_WINDOW,
    OTP_PREPARE_MIN_INTERVAL_SECONDS,
    OTP_PREPARE_WINDOW_SECONDS,
    OtpPrepareRateLimiter,
    OtpProviderBlockedError,
    OtpRateLimitError,
    otp_prepare_rate_limiter,
)


class FakeClock:
    """A manually-advanced clock for deterministic rate-limiter tests."""

    def __init__(self, start: float = 0.0):
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds``."""
        self._now += seconds


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the module-level singleton so tests never leak state."""
    otp_prepare_rate_limiter.reset()
    yield
    otp_prepare_rate_limiter.reset()


class TestMinIntervalEnforcement:
    """Enforces a minimum spacing between two prepares for the same phone."""

    def test_second_prepare_within_min_interval_is_blocked(self):
        """A 2nd prepare inside 60s for the same phone raises OtpRateLimitError."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.check_and_record(phone)
        clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS - 1)

        with pytest.raises(OtpRateLimitError):
            limiter.check_and_record(phone)

    def test_prepare_allowed_again_after_min_interval_elapses(self):
        """Advancing the clock past the min interval allows another prepare."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.check_and_record(phone)
        clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS)

        # Must not raise.
        limiter.check_and_record(phone)

    def test_blocked_call_does_not_reset_the_interval_timer(self):
        """A blocked call must not record a timestamp of its own.

        Otherwise a rejected call would itself become the new "last prepare"
        and extend the block window each time it's retried.
        """
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.check_and_record(phone)  # t=0, recorded
        clock.advance(1)
        with pytest.raises(OtpRateLimitError):
            limiter.check_and_record(phone)  # t=1, blocked, NOT recorded

        # If the blocked call had reset the timer to t=1, we'd still be
        # blocked at t=60. Since it didn't, t=60 is >= 60s since the t=0
        # timestamp and must be allowed.
        clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS - 1)
        limiter.check_and_record(phone)  # t=60, must succeed


class TestWindowCap:
    """Enforces a maximum number of prepares within a rolling window."""

    def test_up_to_max_per_window_are_allowed(self):
        """The first OTP_PREPARE_MAX_PER_WINDOW prepares (spaced past the
        min interval) all succeed."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        for _ in range(OTP_PREPARE_MAX_PER_WINDOW):
            limiter.check_and_record(phone)
            clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS)

    def test_exceeding_max_per_window_is_blocked(self):
        """The (N+1)th prepare within the window raises OtpRateLimitError."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        for _ in range(OTP_PREPARE_MAX_PER_WINDOW):
            limiter.check_and_record(phone)
            clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS)

        with pytest.raises(OtpRateLimitError):
            limiter.check_and_record(phone)

    def test_blocked_call_does_not_consume_a_window_slot(self):
        """A rejected prepare must not count toward the window cap.

        Retry after retry of a blocked call should never itself become the
        reason for being blocked — only genuinely accepted prepares count.
        """
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        for _ in range(OTP_PREPARE_MAX_PER_WINDOW):
            limiter.check_and_record(phone)
            clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS)

        # This is over the cap and must be rejected without consuming a slot.
        for _ in range(5):
            with pytest.raises(OtpRateLimitError):
                limiter.check_and_record(phone)

        # Advance past the window so the original recorded timestamps expire,
        # then confirm we're not somehow further capped by the repeated
        # blocked attempts above.
        clock.advance(OTP_PREPARE_WINDOW_SECONDS)
        limiter.check_and_record(phone)  # must succeed — window has rolled over

    def test_entries_older_than_window_are_pruned(self):
        """Prepares older than the rolling window no longer count against the cap."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        # Fill up to the cap, spacing calls past the min-interval so each
        # one is accepted on its own merits (isolating the window-pruning
        # behavior from the min-interval rule).
        for _ in range(OTP_PREPARE_MAX_PER_WINDOW):
            limiter.check_and_record(phone)
            clock.advance(OTP_PREPARE_MIN_INTERVAL_SECONDS)

        # Jump past the window so all prior entries are stale.
        clock.advance(OTP_PREPARE_WINDOW_SECONDS)

        # Must succeed: min-interval has elapsed and the window reset.
        limiter.check_and_record(phone)


class TestPerPhoneIsolation:
    """Rate limiting is tracked independently per phone number."""

    def test_separate_phone_numbers_do_not_interfere(self):
        """Blocking one phone number must not affect another phone's state."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone_a = "+15551234567"
        phone_b = "+15557654321"

        limiter.check_and_record(phone_a)
        with pytest.raises(OtpRateLimitError):
            limiter.check_and_record(phone_a)

        # phone_b has never been recorded, so it must be allowed immediately.
        limiter.check_and_record(phone_b)


class TestProviderBlockCircuitBreaker:
    """Once the SMS provider (Twilio) blocks a number, stop hammering it.

    ``record_provider_block`` arms a per-phone cooldown that short-circuits
    ``check_and_record`` immediately — no min-interval/window bookkeeping is
    consulted or mutated while the block is active.
    """

    def test_check_and_record_raises_while_blocked(self):
        """A blocked phone raises OtpProviderBlockedError on the very next call."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.record_provider_block(phone)

        with pytest.raises(OtpProviderBlockedError):
            limiter.check_and_record(phone)

    def test_allowed_again_after_cooldown_elapses(self):
        """Advancing the clock past OTP_BLOCK_COOLDOWN_SECONDS lifts the block."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.record_provider_block(phone)
        clock.advance(OTP_BLOCK_COOLDOWN_SECONDS)

        # Must not raise — the cooldown has fully elapsed.
        limiter.check_and_record(phone)

    def test_blocked_call_consumes_no_min_interval_or_window_slot(self):
        """Rejections from the block never count toward the other limits.

        Only a genuinely accepted prepare (post-block) should start the
        min-interval clock or occupy a window slot.
        """
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.record_provider_block(phone)
        for _ in range(5):
            with pytest.raises(OtpProviderBlockedError):
                limiter.check_and_record(phone)

        clock.advance(OTP_BLOCK_COOLDOWN_SECONDS)

        # The first post-cooldown call must succeed as if nothing had ever
        # been recorded — the repeated blocked attempts above left no trace.
        limiter.check_and_record(phone)

        # Immediately calling again must hit the (unrelated) min-interval
        # rule, proving exactly one timestamp was recorded by the call above.
        with pytest.raises(OtpRateLimitError):
            limiter.check_and_record(phone)

    def test_other_phones_are_unaffected_by_a_block(self):
        """Blocking one phone number must not block a different phone."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        blocked_phone = "+15551234567"
        other_phone = "+15557654321"

        limiter.record_provider_block(blocked_phone)

        # Must not raise — other_phone was never blocked.
        limiter.check_and_record(other_phone)

    def test_otp_provider_blocked_error_is_a_rate_limit_error_subclass(self):
        """Subclassing means existing `except OtpRateLimitError` handlers
        (resend route's BadRequestException mapping, login()'s error
        surfacing) already catch this with no new wiring."""
        assert issubclass(OtpProviderBlockedError, OtpRateLimitError)

    def test_reset_clears_the_block(self):
        """reset() lifts an active block, not just the timestamp history."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.record_provider_block(phone)
        limiter.reset()

        # Must not raise — reset() cleared blocked_until too.
        limiter.check_and_record(phone)


class TestErrorMessage:
    """The raised error carries a user-facing, actionable message."""

    def test_error_message_is_non_empty_string(self):
        """OtpRateLimitError.__str__ yields a readable, non-empty message."""
        clock = FakeClock()
        limiter = OtpPrepareRateLimiter(clock=clock)
        phone = "+15551234567"

        limiter.check_and_record(phone)
        try:
            limiter.check_and_record(phone)
        except OtpRateLimitError as exc:
            assert str(exc)
        else:
            pytest.fail("Expected OtpRateLimitError to be raised")

    def test_otp_rate_limit_error_is_an_exception_subclass(self):
        """OtpRateLimitError must be a plain Exception subclass (not more specific)."""
        assert issubclass(OtpRateLimitError, Exception)


class TestModuleLevelSingleton:
    """The module exposes a shared singleton instance and a reset() helper."""

    def test_singleton_uses_real_clock_by_default(self):
        """The singleton is usable without any test wiring (real time.monotonic)."""
        # Should not raise — first call for a fresh phone always succeeds.
        otp_prepare_rate_limiter.check_and_record("+15559999999")

    def test_reset_clears_all_recorded_state(self):
        """reset() wipes recorded timestamps so a blocked phone is allowed again."""
        phone = "+15551112222"
        otp_prepare_rate_limiter.check_and_record(phone)
        with pytest.raises(OtpRateLimitError):
            otp_prepare_rate_limiter.check_and_record(phone)

        otp_prepare_rate_limiter.reset()

        # Must not raise — state was cleared.
        otp_prepare_rate_limiter.check_and_record(phone)
