"""Integration test: the scrape-launch route works through the real threadpool.

``POST /api/scraping/start`` is a synchronous FastAPI route, so Starlette runs
it in a threadpool worker thread with no running event loop. Launching the
scraper there with ``asyncio.create_task`` raised ``RuntimeError: no running
event loop`` and silently dropped the scrape (the ``coroutine 'ScraperAdapter.
run' was never awaited`` RuntimeWarning seen on a real OneZero scrape).

Unlike ``test_scraping_routes.py`` — which mocks ``ScrapingService`` wholesale
and so never exercises the launch — this test drives the real route and the
real ``ScrapingService.start_scraping_single`` through the ASGI stack, mocking
only the deep dependencies, and asserts the adapter's ``run()`` coroutine
actually executes on the captured main loop.
"""

import asyncio
import threading
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import backend.services.scraping_service as ss


@pytest.fixture
def main_loop():
    """Register a real background event loop as the app's main loop.

    Route tests don't run the FastAPI lifespan (which normally captures the
    loop via ``set_main_loop``), so we register one explicitly for the test
    and tear it down afterwards.
    """
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    ss.set_main_loop(loop)
    yield loop
    ss.set_main_loop(None)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


class TestScrapeLaunchRouteThroughThreadpool:
    """The synchronous launch route must schedule the scraper on the main loop."""

    def test_post_start_launches_scraper_from_sync_route(self, test_client, main_loop):
        """POST /api/scraping/start runs adapter.run() with no event-loop error."""
        ran = threading.Event()

        async def fake_run():
            ran.set()

        mock_adapter = MagicMock()
        mock_adapter.process_id = 42
        mock_adapter.run = fake_run

        mock_creds_repo = MagicMock()
        mock_creds_repo.get_credentials.return_value = {"user": "x"}

        mock_history_repo = MagicMock()
        mock_history_repo.IN_PROGRESS = "in_progress"
        mock_history_repo.record_scrape_start.return_value = 42

        @contextmanager
        def fake_db_context():
            yield MagicMock()

        with patch(
            "backend.services.scraping_service.CredentialsRepository",
            return_value=mock_creds_repo,
        ), patch(
            "backend.services.scraping_service.ScrapingHistoryRepository",
            return_value=mock_history_repo,
        ), patch(
            "backend.services.scraping_service.create_adapter",
            return_value=mock_adapter,
        ), patch(
            "backend.services.scraping_service.is_2fa_required",
            return_value=False,
        ), patch(
            "backend.services.scraping_service.get_db_context",
            side_effect=fake_db_context,
        ):
            response = test_client.post(
                "/api/scraping/start",
                json={
                    "service": "banks",
                    "provider": "onezero",
                    "account": "Acc",
                    # Pass a period so the start date is computed directly and
                    # the (mocked) history lookup isn't needed.
                    "scraping_period_days": 30,
                },
            )

        assert response.status_code == 200
        assert response.json() == 42
        assert ran.wait(timeout=5), "adapter.run() never executed via the route"
