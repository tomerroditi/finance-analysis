"""
Endpoint tests for ``POST /api/uninstall``.

The route is macOS-only, so on every other platform the tests verify
the 400 fallback. On darwin we patch out the deferred-script
materialisation + Terminal launch and assert the cleanup module was
called with the right arguments.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from backend.uninstall.cleanup import CleanupReport


class TestUninstallRoute:
    """Tests for ``POST /api/uninstall``."""

    def test_non_darwin_platforms_get_400(self, test_client, monkeypatch) -> None:
        """The route refuses to run on Windows / Linux."""
        monkeypatch.setattr(
            "backend.routes.uninstall.sys.platform", "linux", raising=False
        )

        resp = test_client.post("/api/uninstall", json={"wipe_data": False})

        assert resp.status_code == 400
        assert "macOS" in resp.json()["detail"]

    def test_darwin_runs_cleanup_and_schedules_deferred_removal(
        self, test_client, monkeypatch, tmp_path
    ) -> None:
        """On darwin, cleanup is invoked and a deferred Terminal script is launched."""
        monkeypatch.setattr(
            "backend.routes.uninstall.sys.platform", "darwin", raising=False
        )

        report = CleanupReport(
            wipe_data=True,
            user_dir=str(tmp_path),
            user_dir_existed=True,
            user_dir_removed=True,
            keyring_entries_deleted=4,
            keyring_entries_attempted=4,
        )

        with patch(
            "backend.routes.uninstall.run_cleanup", return_value=report
        ) as cleanup_spy, patch(
            "backend.routes.uninstall._launch_in_terminal"
        ) as launch_spy:
            resp = test_client.post(
                "/api/uninstall", json={"wipe_data": True}
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "scheduled"
        assert body["keyring_entries_deleted"] == 4
        assert body["user_dir_will_be_removed"] is True

        cleanup_spy.assert_called_once_with(wipe_data=True)
        launch_spy.assert_called_once()
        # The deferred script path should exist on disk after the call.
        called_path = launch_spy.call_args.args[0]
        assert called_path.is_file()

    def test_default_request_body_keeps_data(
        self, test_client, monkeypatch, tmp_path
    ) -> None:
        """An empty body defaults to wipe_data=False (preserve data)."""
        monkeypatch.setattr(
            "backend.routes.uninstall.sys.platform", "darwin", raising=False
        )

        report = CleanupReport(
            wipe_data=False,
            user_dir=str(tmp_path),
            user_dir_existed=False,
            user_dir_removed=False,
            keyring_entries_deleted=0,
            keyring_entries_attempted=0,
        )

        with patch(
            "backend.routes.uninstall.run_cleanup", return_value=report
        ) as cleanup_spy, patch(
            "backend.routes.uninstall._launch_in_terminal"
        ):
            resp = test_client.post("/api/uninstall", json={})

        assert resp.status_code == 200
        cleanup_spy.assert_called_once_with(wipe_data=False)
