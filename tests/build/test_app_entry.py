"""
Unit tests for build/app_entry.py — the PyInstaller-bundled entry point.

These tests exercise the helpers and the CLI dispatch logic without
ever starting uvicorn or opening a browser, so they run in <1s on
any platform.

The full integration verification (does the bundled .app actually
boot? does --smoke-test return 0?) lives in
.github/workflows/build-smoke.yml — that's the only place a real
PyInstaller bundle is launched. These tests cover the unit-testable
branches; the build-smoke workflow covers everything else.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add build/ to sys.path so we can import app_entry as a module. It's
# not a Python package; PyInstaller runs it as a script, but for tests
# we need to import it directly.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build"))

import app_entry  # noqa: E402


@pytest.fixture
def tmp_user_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Force ``FAD_USER_DIR`` at a tmp path so tests can't touch real data."""
    monkeypatch.setenv("FAD_USER_DIR", str(tmp_path))
    # Reload app_entry-bound state. ``_setup_env`` reads the env var
    # fresh on each call, so no module reload is needed.
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


class TestResourceRoot:
    """Tests for ``_resource_root``."""

    def test_returns_meipass_when_frozen(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """When ``sys.frozen`` is set, the resource root is ``sys._MEIPASS``."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

        assert app_entry._resource_root() == tmp_path

    def test_returns_repo_root_when_not_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When not frozen, the resource root is the project root (parent of build/)."""
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)

        # ``app_entry.__file__`` is build/app_entry.py; its grandparent is the repo.
        assert app_entry._resource_root() == Path(app_entry.__file__).resolve().parent.parent


class TestSetupEnv:
    """Tests for ``_setup_env``."""

    def test_creates_user_dir_and_logs_subdir(self, tmp_user_dir: Path) -> None:
        """``_setup_env`` should create the user-data dir and its logs subdir."""
        # Pre-condition: tmp_user_dir exists (as a tmp_path fixture artifact)
        # but it's empty.
        assert not (tmp_user_dir / "logs").exists()

        result = app_entry._setup_env()

        assert result == tmp_user_dir
        assert (tmp_user_dir / "logs").is_dir()

    def test_sets_playwright_browsers_path_when_bundled(
        self, tmp_user_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """When a bundled ``playwright_browsers/`` dir exists, point env at it."""
        # Stand up a fake bundled playwright dir.
        fake_bundle = tmp_path / "fake-bundle"
        (fake_bundle / "playwright_browsers").mkdir(parents=True)
        monkeypatch.setattr(app_entry, "_resource_root", lambda: fake_bundle)

        # Make sure we don't inherit a real user's setting.
        monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

        app_entry._setup_env()

        assert os.environ["PLAYWRIGHT_BROWSERS_PATH"] == str(
            fake_bundle / "playwright_browsers"
        )

    def test_does_not_set_playwright_when_not_bundled(
        self, tmp_user_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If there's no bundled Chromium dir, leave PLAYWRIGHT_BROWSERS_PATH alone."""
        empty_root = tmp_path / "empty-root"
        empty_root.mkdir()
        monkeypatch.setattr(app_entry, "_resource_root", lambda: empty_root)
        monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)

        app_entry._setup_env()

        assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ


class TestPickPort:
    """Tests for ``_pick_port``."""

    def test_returns_a_usable_port(self) -> None:
        """``_pick_port`` returns a port we can bind to immediately afterwards."""
        import socket

        port = app_entry._pick_port()
        assert 1024 < port < 65536
        # The port should be free; binding right after the picker confirms it.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))


# ---------------------------------------------------------------------------
# CLI dispatch.
# ---------------------------------------------------------------------------


class TestCli:
    """Tests for the ``main`` argv dispatcher."""

    def test_default_runs_default_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No flags → ``_run_default_mode``."""
        spy = MagicMock(return_value=0)
        monkeypatch.setattr(app_entry, "_run_default_mode", spy)

        assert app_entry.main([]) == 0
        spy.assert_called_once()

    def test_smoke_test_runs_smoke_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``--smoke-test`` → ``_run_smoke_test``."""
        spy = MagicMock(return_value=0)
        monkeypatch.setattr(app_entry, "_run_smoke_test", spy)

        assert app_entry.main(["--smoke-test"]) == 0
        spy.assert_called_once()

    def test_uninstall_cleanup_wipe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``--uninstall-cleanup --wipe`` → cleanup with wipe_data=True."""
        spy = MagicMock(return_value=0)
        monkeypatch.setattr(app_entry, "_run_uninstall_cleanup", spy)

        assert app_entry.main(["--uninstall-cleanup", "--wipe"]) == 0
        spy.assert_called_once_with(wipe_data=True)

    def test_uninstall_cleanup_keep_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``--uninstall-cleanup --keep-data`` → cleanup with wipe_data=False."""
        spy = MagicMock(return_value=0)
        monkeypatch.setattr(app_entry, "_run_uninstall_cleanup", spy)

        assert app_entry.main(["--uninstall-cleanup", "--keep-data"]) == 0
        spy.assert_called_once_with(wipe_data=False)

    def test_uninstall_cleanup_requires_wipe_or_keep_data(self) -> None:
        """``--uninstall-cleanup`` without --wipe or --keep-data must error."""
        with pytest.raises(SystemExit):
            app_entry.main(["--uninstall-cleanup"])

    def test_uninstall_cleanup_rejects_both_flags(self) -> None:
        """``--uninstall-cleanup --wipe --keep-data`` is a contradiction."""
        with pytest.raises(SystemExit):
            app_entry.main(["--uninstall-cleanup", "--wipe", "--keep-data"])


# ---------------------------------------------------------------------------
# --uninstall-cleanup mode delegates to backend.uninstall.cleanup.run.
# ---------------------------------------------------------------------------


class TestRunUninstallCleanup:
    """Tests for ``_run_uninstall_cleanup``."""

    def test_delegates_to_cleanup_run_with_wipe_flag(
        self, capsys: pytest.CaptureFixture[str], tmp_user_dir: Path
    ) -> None:
        """``_run_uninstall_cleanup(True)`` calls ``cleanup.run(wipe_data=True)``."""
        from backend.uninstall.cleanup import CleanupReport

        fake_report = CleanupReport(
            wipe_data=True,
            user_dir=str(tmp_user_dir),
            user_dir_existed=True,
            user_dir_removed=True,
            keyring_entries_deleted=4,
            keyring_entries_attempted=4,
        )
        with patch(
            "backend.uninstall.cleanup.run", return_value=fake_report
        ) as run_spy:
            rc = app_entry._run_uninstall_cleanup(wipe_data=True)

        run_spy.assert_called_once_with(wipe_data=True)
        assert rc == 0
        # JSON report goes to stdout so NSIS can capture it.
        captured = capsys.readouterr()
        import json

        body = json.loads(captured.out)
        assert body["wipe_data"] is True
        assert body["user_dir_removed"] is True

    def test_returns_1_on_cleanup_errors(
        self, capsys: pytest.CaptureFixture[str], tmp_user_dir: Path
    ) -> None:
        """A non-empty ``errors`` list flips the exit code to 1."""
        from backend.uninstall.cleanup import CleanupReport

        fake_report = CleanupReport(
            wipe_data=False,
            user_dir=str(tmp_user_dir),
            user_dir_existed=False,
            user_dir_removed=False,
            keyring_entries_deleted=0,
            keyring_entries_attempted=0,
            errors=["keychain locked"],
        )
        with patch("backend.uninstall.cleanup.run", return_value=fake_report):
            rc = app_entry._run_uninstall_cleanup(wipe_data=False)

        assert rc == 1
