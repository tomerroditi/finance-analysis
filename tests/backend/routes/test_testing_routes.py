"""Tests for the /api/testing utility endpoints."""


class TestToggleDemoModeVercelGuard:
    """Tests for the Vercel guard on the demo-mode toggle."""

    def test_toggle_is_noop_on_vercel(self, test_client, monkeypatch):
        """Verify the toggle refuses to change demo mode on the shared Vercel deployment."""
        monkeypatch.setenv("VERCEL", "1")
        from backend.config import AppConfig

        initial = AppConfig().is_demo_mode
        response = test_client.post(
            "/api/testing/toggle_demo_mode", json={"enabled": not initial}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["demo_mode"] == initial
        assert AppConfig().is_demo_mode == initial

    def test_demo_mode_status_reports_state(self, test_client):
        """Verify the status endpoint reports the current demo-mode flag."""
        from backend.config import AppConfig

        response = test_client.get("/api/testing/demo_mode_status")
        assert response.status_code == 200
        assert response.json()["demo_mode"] == AppConfig().is_demo_mode
