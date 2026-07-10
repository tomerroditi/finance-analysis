"""Tests for scraper adapter 2FA (Two-Factor Authentication) functionality."""

import asyncio
import datetime
import threading
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

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

    def test_otp_callback_returns_immediately_for_pre_delivered_code(self):
        """A code set BEFORE the callback runs must not be lost.

        Regression test for the clear()-then-wait race: the service
        registers the adapter in ``_tfa_scrapers_waiting`` eagerly, before
        the scraper coroutine reaches ``await on_otp_request()``. If the
        user (or a client) calls ``set_otp_code`` in that gap, the old
        implementation's ``self._otp_event.clear()`` — which ran *after*
        the code was already set — would discard the delivered code and
        the event, and the scraper would then hang on
        ``await self._otp_event.wait()`` until the 5-minute scrape timeout.

        Guarding the wait with ``if self._otp_code is None`` means a
        pre-delivered code is returned immediately, with no wait at all.
        """
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )

        # Code delivered BEFORE _otp_callback is ever invoked.
        adapter.set_otp_code("111222")

        async def run():
            # A tight timeout: if the old clear()-then-wait bug were still
            # present, this would hang until the timeout fires and the
            # test would fail with asyncio.TimeoutError instead of hanging
            # forever — a fast, clear failure signal.
            return await asyncio.wait_for(adapter._otp_callback(), timeout=1.0)

        code = asyncio.run(run())
        assert code == "111222"

    def test_otp_callback_flips_status_to_waiting_for_2fa(self):
        """The status is flipped to WAITING_FOR_2FA when the scraper awaits an OTP.

        This is the "lazy 2FA prompt" behavior — the UI only sees
        WAITING_FOR_2FA once the scraper actually needs the code, not at
        the start of the scrape. Without this, providers like Hapoalim
        (which only sometimes need 2FA) would show a spurious 2FA prompt
        on every run.
        """
        adapter = ScraperAdapter(
            "banks", "hapoalim", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )

        mock_history_repo = MagicMock()
        mock_history_repo.WAITING_FOR_2FA = "waiting_for_2fa"

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        async def run():
            async def set_code():
                await asyncio.sleep(0.05)
                adapter.set_otp_code("12345")

            asyncio.create_task(set_code())
            return await adapter._otp_callback()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=fake_db_context,
        ), patch(
            "backend.scraper.adapter.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ):
            code = asyncio.run(run())

        assert code == "12345"
        mock_history_repo.update_status.assert_called_once_with(
            DUMMY_PROCESS_ID, "waiting_for_2fa"
        )

    def test_otp_callback_survives_status_update_failure(self):
        """OTP flow continues even if the WAITING_FOR_2FA status flip fails.

        The status update is best-effort UI signaling; a transient DB error
        shouldn't crash the OTP flow or the rest of the scrape.
        """
        adapter = ScraperAdapter(
            "banks", "hapoalim", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )

        async def run():
            async def set_code():
                await asyncio.sleep(0.05)
                adapter.set_otp_code("99999")

            asyncio.create_task(set_code())
            return await adapter._otp_callback()

        with patch(
            "backend.scraper.adapter.get_db_context",
            side_effect=RuntimeError("DB locked"),
        ):
            code = asyncio.run(run())

        assert code == "99999"

    def test_set_otp_code_wakes_parked_coroutine_from_another_thread(self):
        """set_otp_code from a worker thread wakes a scraper parked on the loop.

        In production ``run()`` executes on the server's main event loop while
        ``set_otp_code`` is called from a synchronous route in a threadpool
        worker thread. ``asyncio.Event`` is not thread-safe: a bare
        ``_otp_event.set()`` from a foreign thread schedules the waiter's
        wake-up with ``call_soon`` but never wakes the (idle) loop, so an
        already-parked ``await _otp_event.wait()`` hangs until the 5-minute
        scrape timeout. ``set_otp_code`` must marshal the set onto the loop via
        ``call_soon_threadsafe``. Regression test for that cross-thread wake.
        """
        adapter = ScraperAdapter(
            "banks", "onezero", DUMMY_ACCOUNT,
            DUMMY_CREDENTIALS, DUMMY_START_DATE, DUMMY_PROCESS_ID,
        )

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()
        # Simulate run() having captured the loop it executes on.
        adapter._loop = loop

        started = threading.Event()
        woke = threading.Event()

        async def park():
            started.set()
            await adapter._otp_event.wait()
            woke.set()
            return adapter._otp_code

        future = asyncio.run_coroutine_threadsafe(park(), loop)
        try:
            # Ensure the coroutine is actually parked on `await wait()` before
            # delivering the code — otherwise a set-before-wait would pass even
            # with the buggy foreign-thread set().
            assert started.wait(timeout=5)
            time.sleep(0.1)

            # Called from the main test thread — a different thread than the
            # one running the loop, exactly like the sync 2FA route.
            adapter.set_otp_code("654321")

            assert woke.wait(timeout=5), "parked coroutine was not woken across threads"
            assert future.result(timeout=5) == "654321"
        finally:
            loop.call_soon_threadsafe(loop.stop)
            loop_thread.join(timeout=5)
            loop.close()
