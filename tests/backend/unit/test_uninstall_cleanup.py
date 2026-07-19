"""
Unit tests for the cross-platform cleanup module used by the
Windows NSIS uninstaller, the macOS Uninstall.command script, and the
in-app POST /api/uninstall route.

Covers:
    - --keep-data preserves the user-data directory.
    - --wipe removes the user-data directory.
    - Keychain entries are looked up from the credentials DB and deleted.
    - Missing data dir / missing DB are not errors.
    - dry_run reports what would be done without doing it.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.uninstall import cleanup


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the imported ``keyring`` module with a MagicMock that
    counts ``delete_password`` invocations and lets us simulate
    "entry not found" via PasswordDeleteError.
    """
    fake = MagicMock()
    fake.errors.PasswordDeleteError = type(
        "PasswordDeleteError", (Exception,), {}
    )

    deleted: list[tuple[str, str]] = []

    def fake_delete(service: str, key: str) -> None:
        deleted.append((service, key))

    fake.delete_password.side_effect = fake_delete
    fake._deleted = deleted  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setitem(sys.modules, "keyring.errors", fake.errors)
    return fake


def _seed_credentials_db(db_path: Path, rows: list[tuple[str, str, str]]) -> None:
    """Populate a minimal credentials table the cleanup module can read."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "CREATE TABLE credentials (service TEXT, provider TEXT, account_name TEXT)"
        )
        conn.executemany(
            "INSERT INTO credentials (service, provider, account_name) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()


class TestCleanupRun:
    """Tests for backend.uninstall.cleanup.run."""

    def test_keep_data_preserves_user_dir(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """``wipe_data=False`` leaves the user-data directory intact."""
        (tmp_path / "data.db").touch()
        (tmp_path / "credentials.yaml").touch()

        report = cleanup.run(wipe_data=False, user_dir=tmp_path)

        assert report.user_dir_existed is True
        assert report.user_dir_removed is False
        assert (tmp_path / "data.db").exists()
        assert (tmp_path / "credentials.yaml").exists()

    def test_wipe_removes_user_dir(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """``wipe_data=True`` removes the entire user-data directory."""
        (tmp_path / "data.db").touch()
        (tmp_path / "credentials.yaml").touch()

        report = cleanup.run(wipe_data=True, user_dir=tmp_path)

        assert report.user_dir_existed is True
        assert report.user_dir_removed is True
        assert not tmp_path.exists()

    def test_missing_user_dir_is_not_an_error(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """No user-data dir means nothing to remove and no error."""
        ghost = tmp_path / "nonexistent"

        report = cleanup.run(wipe_data=True, user_dir=ghost)

        assert report.user_dir_existed is False
        assert report.user_dir_removed is False
        assert report.errors == []

    def test_keyring_entries_deleted_for_each_credential_row(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """Each (service, provider, account_name) triple in the DB triggers
        a delete attempt for every sensitive field name and for both the
        production and demo keyring service namespaces.
        """
        _seed_credentials_db(
            tmp_path / "data.db",
            [
                ("banks", "hapoalim", "primary"),
                ("credit_cards", "isracard", "personal"),
            ],
        )

        report = cleanup.run(wipe_data=False, user_dir=tmp_path)

        # 2 rows × 4 fields × 2 service namespaces = 16 attempts, plus the
        # service-level field-encryption key in both namespaces = 18.
        assert report.keyring_entries_attempted == 18
        assert fake_keyring.delete_password.call_count == 18

        # Spot-check a few of the calls.
        called_pairs = set(fake_keyring._deleted)  # type: ignore[attr-defined]
        assert ("finance-analysis-app", "banks_hapoalim_primary_password") in called_pairs
        assert (
            "finance-analysis-app-demo",
            "credit_cards_isracard_personal_otpLongTermToken",
        ) in called_pairs
        assert ("finance-analysis-app", "field-encryption-key") in called_pairs

    def test_dry_run_makes_no_destructive_calls(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """dry_run reports what would be removed without performing it."""
        _seed_credentials_db(tmp_path / "data.db", [("banks", "discount", "x")])

        report = cleanup.run(wipe_data=True, user_dir=tmp_path, dry_run=True)

        assert report.dry_run is True
        assert report.user_dir_removed is True  # would have been removed
        assert tmp_path.exists()  # but actually wasn't
        assert fake_keyring.delete_password.call_count == 0
        # All 10 attempts (1 row × 4 fields × 2 namespaces, plus the
        # field-encryption key in both namespaces) are reported but skipped.
        assert report.keyring_entries_attempted == 10
        assert report.keyring_entries_deleted == 0

    def test_keyring_passworddeleteerror_is_swallowed(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """``keyring.errors.PasswordDeleteError`` (entry not found) is not an error."""
        _seed_credentials_db(tmp_path / "data.db", [("banks", "leumi", "main")])

        # Make every delete raise the "entry not found" exception.
        fake_keyring.delete_password.side_effect = fake_keyring.errors.PasswordDeleteError(
            "not found"
        )

        report = cleanup.run(wipe_data=False, user_dir=tmp_path)

        assert report.errors == []
        assert report.keyring_entries_deleted == 0

    def test_unexpected_keyring_error_is_recorded(
        self, tmp_path: Path, fake_keyring: MagicMock
    ) -> None:
        """A non-PasswordDeleteError keyring exception is recorded, not raised."""
        _seed_credentials_db(tmp_path / "data.db", [("banks", "leumi", "main")])

        fake_keyring.delete_password.side_effect = RuntimeError("keychain locked")

        report = cleanup.run(wipe_data=False, user_dir=tmp_path)

        assert report.errors  # at least one error recorded
        assert any("keychain locked" in e for e in report.errors)


class TestCli:
    """Tests for the ``python -m backend.uninstall`` CLI."""

    def test_cli_keep_data_emits_json_report(
        self, tmp_path: Path, fake_keyring: MagicMock, capsys: Any
    ) -> None:
        """CLI exits 0 and prints a JSON report when no errors occur."""
        rc = cleanup.cli(["--keep-data", "--dry-run"])
        captured = capsys.readouterr()

        assert rc == 0
        # Stdout must be valid JSON.
        import json

        payload = json.loads(captured.out)
        assert payload["wipe_data"] is False
        assert payload["dry_run"] is True

    def test_cli_requires_one_of_wipe_or_keep_data(self) -> None:
        """Missing --wipe / --keep-data → argparse SystemExit."""
        with pytest.raises(SystemExit):
            cleanup.cli([])
