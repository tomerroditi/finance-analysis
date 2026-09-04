"""Tests that a scrape carries its launching client's demo mode."""

import asyncio
import datetime

from backend.config import AppConfig
from backend.scraper.adapter import ScraperAdapter


def _make_adapter() -> ScraperAdapter:
    """Build an adapter with throwaway arguments."""
    return ScraperAdapter(
        service_name="banks",
        provider_name="hapoalim",
        account_name="test",
        credentials={},
        start_date=datetime.date(2026, 1, 1),
        process_id=1,
    )


class TestAdapterCapturesDemoMode:
    """Tests for demo-mode capture at adapter construction."""

    def test_captures_demo_mode_at_construction(self):
        """Verify an adapter built in demo mode records that mode."""
        config = AppConfig()
        token = config.set_demo_mode(True)
        try:
            adapter = _make_adapter()
        finally:
            config.reset_demo_mode(token)

        assert adapter.demo_mode is True

    def test_captures_real_mode_at_construction(self):
        """Verify an adapter built in real mode records real mode."""
        adapter = _make_adapter()
        assert adapter.demo_mode is False

    def test_apply_demo_context_restores_on_exit(self):
        """Verify the scope helper sets the flag and then restores it."""
        adapter = _make_adapter()
        adapter.demo_mode = True

        assert AppConfig().is_demo_mode is False
        with adapter._apply_demo_context():
            assert AppConfig().is_demo_mode is True
        assert AppConfig().is_demo_mode is False

    def test_mode_survives_the_event_loop_hop(self):
        """Verify a coroutine run on another loop still sees demo mode.

        This is the actual regression: run_coroutine_threadsafe does not
        inherit the caller's context, so without the explicit hand-off a
        demo client's scrape would write to the real database.
        """
        adapter = _make_adapter()
        adapter.demo_mode = True
        observed: list[bool] = []

        async def body():
            with adapter._apply_demo_context():
                observed.append(AppConfig().is_demo_mode)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(body())
        finally:
            loop.close()

        assert observed == [True]
