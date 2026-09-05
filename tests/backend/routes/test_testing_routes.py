"""Tests for the /api/testing utility endpoints."""

import pytest

from backend.config import AppConfig
from backend.database import get_engine
from backend.models.base import Base


@pytest.fixture(autouse=True)
def _clear_forced_mode():
    """Ensure no test leaks a process-wide demo pin into its neighbours."""
    AppConfig._forced_mode = None
    yield
    AppConfig._forced_mode = None


def _isolate_demo_user_dir(tmp_path, monkeypatch) -> None:
    """Point ``FAD_USER_DIR`` at a throwaway directory for this test.

    ``_build_demo_database`` forces real demo context and opens a session
    against whatever path ``AppConfig`` resolves — outside this isolation
    that is the developer's *actual* ``~/.finance-analysis/demo_env``, which
    a test must never touch. ``prepare_demo_database`` is mocked away in
    these tests (it is the thing under test's orchestration, not its own
    file-copy logic), so nothing else creates the schema the seeding step
    queries; pre-create it here to stand in for that mocked-out call.
    """
    monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
    config = AppConfig()
    token = config.set_demo_mode(True)
    try:
        Base.metadata.create_all(get_engine())
    finally:
        config.reset_demo_mode(token)


class TestDemoModeStatus:
    """Tests for the demo-mode status endpoint."""

    def test_reports_header_derived_mode(self, test_client):
        """Verify the status echoes the mode resolved for this request."""
        response = test_client.get(
            "/api/testing/demo_mode_status", headers={"X-FAD-Demo": "1"}
        )
        assert response.status_code == 200
        assert response.json() == {"demo_mode": True, "forced": False}

    def test_reports_forced_when_pinned(self, test_client):
        """Verify a pinned deployment advertises that clients cannot opt out."""
        AppConfig._forced_mode = True
        response = test_client.get("/api/testing/demo_mode_status")
        assert response.json() == {"demo_mode": True, "forced": True}


class TestDemoPrepare:
    """Tests for the idempotent demo-database prepare endpoint."""

    def test_builds_when_missing(self, test_client, tmp_path, monkeypatch):
        """Verify a first call creates the demo database."""
        _isolate_demo_user_dir(tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(
            "backend.routes.testing.prepare_demo_database",
            lambda: calls.append("built"),
        )
        monkeypatch.setattr(
            "backend.routes.testing._demo_db_exists", lambda: False
        )

        response = test_client.post("/api/testing/demo/prepare")

        assert response.status_code == 200
        assert response.json()["created"] is True
        assert calls == ["built"]

    def test_is_a_noop_when_present(self, test_client, monkeypatch):
        """Verify a second call does not rebuild and wipe a live demo session."""
        calls = []
        monkeypatch.setattr(
            "backend.routes.testing.prepare_demo_database",
            lambda: calls.append("built"),
        )
        monkeypatch.setattr(
            "backend.routes.testing._demo_db_exists", lambda: True
        )

        response = test_client.post("/api/testing/demo/prepare")

        assert response.json()["created"] is False
        assert calls == []

    def test_refuses_when_forced(self, test_client, monkeypatch):
        """Verify a pinned deployment never rebuilds on a client's request."""
        calls = []
        monkeypatch.setattr(
            "backend.routes.testing.prepare_demo_database",
            lambda: calls.append("built"),
        )
        AppConfig._forced_mode = True

        response = test_client.post("/api/testing/demo/prepare")

        assert response.status_code == 200
        assert calls == []


class TestDemoReset:
    """Tests for the unconditional demo-database reset endpoint."""

    def test_rebuilds_unconditionally(self, test_client, tmp_path, monkeypatch):
        """Verify reset rebuilds even when the demo database already exists."""
        _isolate_demo_user_dir(tmp_path, monkeypatch)
        calls = []
        monkeypatch.setattr(
            "backend.routes.testing.prepare_demo_database",
            lambda: calls.append("built"),
        )
        monkeypatch.setattr(
            "backend.routes.testing._demo_db_exists", lambda: True
        )

        response = test_client.post("/api/testing/demo/reset")

        assert response.status_code == 200
        assert calls == ["built"]

    def test_refuses_when_forced(self, test_client, monkeypatch):
        """Verify a pinned deployment refuses a client-triggered rebuild."""
        calls = []
        monkeypatch.setattr(
            "backend.routes.testing.prepare_demo_database",
            lambda: calls.append("built"),
        )
        AppConfig._forced_mode = True

        response = test_client.post("/api/testing/demo/reset")

        assert response.status_code == 200
        assert calls == []
