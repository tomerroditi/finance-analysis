"""Tests for the X-FAD-Demo request header middleware."""

import pytest

from backend.config import AppConfig


@pytest.fixture(autouse=True)
def _clear_forced_mode():
    """Ensure no test leaks a process-wide demo pin into its neighbours."""
    AppConfig._forced_mode = None
    yield
    AppConfig._forced_mode = None


class TestDemoModeHeader:
    """Tests that the header drives per-request mode resolution."""

    def test_absent_header_is_real_mode(self, test_client):
        """Verify a request with no header reports real mode."""
        response = test_client.get("/api/testing/demo_mode_status")
        assert response.status_code == 200
        assert response.json()["demo_mode"] is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "True"])
    def test_truthy_values_enable_demo(self, test_client, value):
        """Verify accepted truthy header values resolve to demo mode."""
        response = test_client.get(
            "/api/testing/demo_mode_status", headers={"X-FAD-Demo": value}
        )
        assert response.json()["demo_mode"] is True

    @pytest.mark.parametrize("value", ["0", "false", "", "yes", "banana", "2"])
    def test_other_values_are_real_mode(self, test_client, value):
        """Verify anything else — including malformed input — fails to real mode.

        Failing toward real mode is deliberate: a client that wants demo data
        always controls its own header, but a corrupted header must never
        silently surface real financial data to something that did not ask.
        """
        response = test_client.get(
            "/api/testing/demo_mode_status", headers={"X-FAD-Demo": value}
        )
        assert response.json()["demo_mode"] is False

    def test_mode_does_not_leak_between_requests(self, test_client):
        """Verify a demo request does not leave the worker thread in demo mode."""
        test_client.get(
            "/api/testing/demo_mode_status", headers={"X-FAD-Demo": "1"}
        )
        response = test_client.get("/api/testing/demo_mode_status")
        assert response.json()["demo_mode"] is False

    def test_forced_mode_ignores_the_header(self, test_client):
        """Verify a pinned deployment refuses a client's opt-out."""
        AppConfig._forced_mode = True
        response = test_client.get(
            "/api/testing/demo_mode_status", headers={"X-FAD-Demo": "0"}
        )
        assert response.json()["demo_mode"] is True
