"""Tests that a scrape carries its launching client's demo mode."""

import asyncio
import datetime
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


@contextmanager
def _fake_db():
    """Yield a MagicMock session in place of a real DB context.

    Same idiom as ``test_adapter_dedup_and_status.py`` — ``run()``'s
    ``finally`` block always calls ``_record_scraping_attempt``, which we
    don't want touching a real database in this test.
    """
    yield MagicMock()


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

    def test_mode_survives_the_event_loop_hop(self, tmp_path):
        """A scrape launched via run_coroutine_threadsafe still sees demo mode.

        This is the actual regression: ``scraping_service._launch_adapter``
        submits ``adapter.run()`` to the server's main event loop — which
        runs on its OWN OS thread, distinct from the threadpool worker
        thread handling the synchronous route — via
        ``asyncio.run_coroutine_threadsafe``. That hand-off does not carry
        the caller's context, so without ``run()``'s own
        ``with self._apply_demo_context():`` a demo client's scrape would
        silently write to the real database.

        A same-thread ``loop.run_until_complete`` does not reproduce this:
        a Task created on the calling thread inherits that thread's context
        via ``contextvars.copy_context()`` regardless of which loop object
        runs it, so the gap only shows up once the coroutine actually starts
        on a different thread's loop. This test starts a real second
        thread with its own running loop and submits across that boundary,
        exactly as production does, and drives the real ``run()`` method
        (not just the ``_apply_demo_context()`` helper in isolation) so a
        refactor that moves or drops that ``with`` block inside ``run()``
        is caught.

        Non-vacuity was verified manually: temporarily dedenting ``run()``'s
        ``with self._apply_demo_context():`` block in
        ``backend/scraper/adapter.py`` (removing the context hand-off) made
        this test fail with ``observed["is_demo_mode"] is False`` — the
        background thread's ContextVar defaulted to real mode, exactly the
        data-loss scenario this test guards against. Restoring the ``with``
        block makes it pass again.
        """
        config = AppConfig()
        # Hermetic: never touch ~/.finance-analysis/, even via the
        # os.makedirs in set_demo_mode(True) that _apply_demo_context()
        # triggers on the background thread.
        config._base_user_dir = str(tmp_path)
        try:
            adapter = _make_adapter()
            adapter.demo_mode = True
            observed: dict[str, object] = {}

            async def fake_scrape():
                # Recorded from *inside* run()'s own
                # `with self._apply_demo_context():` block — this is the
                # exact call site the regression protects.
                observed["is_demo_mode"] = AppConfig().is_demo_mode
                observed["db_path"] = AppConfig().get_db_path()
                return SimpleNamespace(
                    success=False,
                    error_type="TEST",
                    error_message="stub — no real scraping performed",
                )

            # Skip real provider/browser work entirely; only the demo-mode
            # plumbing around it is under test.
            adapter._create_scraper = lambda *_args, **_kwargs: SimpleNamespace(
                scrape=fake_scrape
            )

            assert AppConfig().is_demo_mode is False, (
                "the submitting (main) thread must start in real mode"
            )

            bg_loop = asyncio.new_event_loop()
            bg_thread = threading.Thread(
                target=bg_loop.run_forever, daemon=True
            )
            bg_thread.start()
            try:
                with (
                    patch("backend.scraper.adapter.get_db_context", _fake_db),
                    patch("backend.scraper.adapter.ScrapingHistoryRepository"),
                ):
                    future = asyncio.run_coroutine_threadsafe(
                        adapter.run(), bg_loop
                    )
                    future.result(timeout=10)
            finally:
                bg_loop.call_soon_threadsafe(bg_loop.stop)
                bg_thread.join(timeout=5)
                bg_loop.close()

            assert observed["is_demo_mode"] is True
            assert observed["db_path"].endswith("demo_data.db")
            # The submitting thread's own context must be untouched by the
            # background thread's demo-mode context — mode is context-local,
            # not process-global.
            assert AppConfig().is_demo_mode is False
        finally:
            config._base_user_dir = None
