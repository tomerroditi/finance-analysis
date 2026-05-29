"""Tests for scraper utility helpers (waiting/polling)."""

import asyncio

import pytest

from scraper.exceptions import TimeoutError
from scraper.utils.waiting import wait_until


class TestWaitUntil:
    """Tests for the wait_until polling helper."""

    def test_returns_truthy_result_immediately(self):
        """Verify the polled value is returned as soon as it is truthy."""

        async def run():
            calls = {"n": 0}

            async def test():
                calls["n"] += 1
                return "ready" if calls["n"] >= 2 else None

            result = await wait_until(test, timeout=1.0, interval=0.01)
            return result, calls["n"]

        result, calls = asyncio.run(run())
        assert result == "ready"
        assert calls == 2

    def test_raises_timeout_when_never_truthy(self):
        """Verify TimeoutError is raised when the test never succeeds."""

        async def run():
            async def test():
                return None

            with pytest.raises(TimeoutError):
                await wait_until(test, description="never", timeout=0.05, interval=0.01)

        asyncio.run(run())

    def test_timeout_accounts_for_time_inside_async_test(self):
        """Verify the timeout is measured against wall-clock time.

        Regression: the previous implementation only accumulated the sleep
        ``interval`` between polls, ignoring the time spent inside
        ``async_test`` itself. A slow probe could therefore run far longer
        than the requested timeout. With a wall-clock deadline, a test that
        sleeps ~0.05s per call exhausts a 0.1s budget in only a couple of
        calls — not ``timeout / interval`` (10) of them.
        """

        async def run():
            calls = {"n": 0}

            async def slow_false():
                calls["n"] += 1
                await asyncio.sleep(0.05)
                return False

            with pytest.raises(TimeoutError):
                await wait_until(slow_false, timeout=0.1, interval=0.01)
            return calls["n"]

        calls = asyncio.run(run())
        # Wall-clock deadline: ~0.06s per iteration against a 0.1s budget.
        assert calls <= 4
