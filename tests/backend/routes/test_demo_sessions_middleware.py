"""Tests for routing requests into per-visitor demo sandboxes.

The middleware in ``backend.main`` hands a request to
``demo_sessions.serve_in_session`` only when sandboxes are enabled, the
request is in demo mode, and the ``X-FAD-Demo-Session`` header is
well-formed. These tests pin that gate and the persist-after-write contract
using a recording store, so no file or network I/O happens.
"""

import pytest

from backend import demo_sessions
from backend.config import AppConfig

SID = "visitor-0123456789abcdef"
STATUS = "/api/testing/demo_mode_status"


class RecordingStore:
    """Store double that records which sandbox each hook was called for."""

    durable = False

    def __init__(self):
        self.synced: list[str] = []
        self.persisted: list[str] = []
        self.seen_paths: list[str] = []

    def sync(self, session_id):
        self.synced.append(session_id)
        self.seen_paths.append(AppConfig().get_db_path())

    def persist(self, session_id):
        self.persisted.append(session_id)
        return True


@pytest.fixture
def store(monkeypatch, tmp_path):
    """Enable sandboxes with an isolated user dir and a recording store."""
    monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
    monkeypatch.setattr(AppConfig(), "_base_user_dir_override", None)
    monkeypatch.setenv(demo_sessions.SESSIONS_ENV, "1")
    AppConfig._forced_mode = None
    recording = RecordingStore()
    demo_sessions.set_store(recording)
    yield recording
    demo_sessions.set_store(None)
    AppConfig._forced_mode = None


class TestGate:
    """Tests for when a request is (not) bound to a sandbox."""

    def test_demo_request_with_header_is_sandboxed(self, test_client, store):
        """Verify demo mode plus a valid id reports a sandboxed request."""
        response = test_client.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
        )
        assert response.json()["sandboxed"] is True

    def test_forced_deployment_binds_header(self, test_client, store):
        """Verify the pinned Vercel deployment honours the id without X-FAD-Demo."""
        AppConfig._forced_mode = True
        response = test_client.get(STATUS, headers={demo_sessions.SESSION_HEADER: SID})
        assert response.json() == {
            "demo_mode": True,
            "forced": True,
            "sandboxed": True,
            "durable": False,
        }

    def test_real_mode_ignores_header(self, test_client, store):
        """Verify a real-mode request is never redirected into a sandbox."""
        response = test_client.get(STATUS, headers={demo_sessions.SESSION_HEADER: SID})
        assert response.json() == {
            "demo_mode": False,
            "forced": False,
            "sandboxed": False,
            "durable": False,
        }

    def test_disabled_feature_ignores_header(self, test_client, store, monkeypatch):
        """Verify a local backend keeps the shared demo DB even with the header."""
        monkeypatch.delenv(demo_sessions.SESSIONS_ENV)
        response = test_client.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
        )
        assert response.json()["sandboxed"] is False

    @pytest.mark.parametrize("bad", ["short", "../../x0123456789abcd", "with space 0123456789"])
    def test_malformed_header_falls_back_to_shared(self, test_client, store, bad):
        """Verify an unsafe id is dropped rather than used as a path segment."""
        response = test_client.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: bad}
        )
        assert response.json()["sandboxed"] is False
        assert store.synced == []

    def test_session_does_not_leak_between_requests(self, test_client, store):
        """Verify the bound id is reset once the request finishes."""
        test_client.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
        )
        response = test_client.get(STATUS, headers={"X-FAD-Demo": "1"})
        assert response.json()["sandboxed"] is False


class TestMaterializeAndPersist:
    """Tests for the ensure-before / persist-after contract."""

    def test_syncs_sandbox_in_session_context_on_every_request(self, test_client, store, tmp_path):
        """Verify each request revalidates the sandbox with the id bound.

        Revalidating every time (not just the first time an instance sees a
        visitor) is what makes a write on one serverless instance visible
        to the reads another instance serves a moment later.
        """
        for _ in range(2):
            test_client.get(
                STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
            )
        assert store.synced == [SID, SID]
        assert set(store.seen_paths) == {
            str(tmp_path / "demo_env" / "sessions" / SID / "demo_data.db")
        }

    def test_persists_after_successful_write(self, test_client, store):
        """Verify a 2xx mutating /api request uploads the sandbox."""
        response = test_client.post(
            "/api/testing/demo/prepare",
            headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID},
        )
        assert response.status_code == 200
        assert store.persisted == [SID]

    def test_does_not_persist_reads(self, test_client, store):
        """Verify GET requests never trigger an upload."""
        test_client.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
        )
        assert store.persisted == []

    def test_does_not_persist_failed_writes(self, test_client, store):
        """Verify a rejected write (validation error) does not upload."""
        response = test_client.post(
            "/api/tagging/categories",
            json={"nope": True},
            headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID},
        )
        assert response.status_code == 422
        assert store.persisted == []

    def test_materialize_failure_returns_503(self, test_client_no_raise, store):
        """Verify a sandbox that cannot be built fails closed with a clear 503."""

        def boom(session_id):
            raise RuntimeError("disk full")

        store.sync = boom
        response = test_client_no_raise.get(
            STATUS, headers={"X-FAD-Demo": "1", demo_sessions.SESSION_HEADER: SID}
        )
        assert response.status_code == 503
