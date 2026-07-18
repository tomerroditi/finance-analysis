"""Endpoint tests for the /api/backups API.

The backup utilities (``backend.utils.backup``) touch the real user dir,
the SQLAlchemy engine, and Alembic migrations (``restore_backup`` runs
``alembic upgrade head`` after copying), so they are mocked at the route
module level — these tests exercise the HTTP contract only.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch


class TestListBackups:
    """Tests for GET /api/backups/."""

    def test_list_backups_returns_entries(self, test_client):
        """The route returns the utility's backup listing as-is."""
        backups = [
            {
                "filename": "data_20260401_120000.db",
                "created_at": "2026-04-01T12:00:00",
                "size_bytes": 2048,
            },
            {
                "filename": "data_20260301_090000.db",
                "created_at": "2026-03-01T09:00:00",
                "size_bytes": 1024,
            },
        ]
        with patch(
            "backend.routes.backup.list_backups", return_value=backups
        ) as mock_list:
            response = test_client.get("/api/backups/")

        assert response.status_code == 200
        assert response.json() == backups
        mock_list.assert_called_once_with()

    def test_list_backups_empty(self, test_client):
        """No backups yields an empty list."""
        with patch("backend.routes.backup.list_backups", return_value=[]):
            response = test_client.get("/api/backups/")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateBackup:
    """Tests for POST /api/backups/."""

    def test_create_backup_returns_file_info(self, test_client, tmp_path):
        """A successful backup returns filename, timestamp, and size."""
        backup_file = tmp_path / "data_20260401_120000.db"
        backup_file.write_bytes(b"x" * 512)

        with patch(
            "backend.routes.backup.backup_db", return_value=Path(backup_file)
        ):
            response = test_client.post("/api/backups/")

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "data_20260401_120000.db"
        assert data["size_bytes"] == 512
        assert data["created_at"]  # ISO timestamp string

    def test_create_backup_failure_returns_500(self, test_client):
        """backup_db returning None (failure) maps to a 500 response."""
        with patch("backend.routes.backup.backup_db", return_value=None):
            response = test_client.post("/api/backups/")

        assert response.status_code == 500
        assert response.json()["detail"] == "Backup failed"


class TestRestoreBackup:
    """Tests for POST /api/backups/restore."""

    def test_restore_happy_path(self, test_client):
        """A valid filename restores and echoes the restored filename."""
        mock_restore = MagicMock()
        with patch("backend.routes.backup.restore_backup", mock_restore):
            response = test_client.post(
                "/api/backups/restore",
                json={"filename": "data_20260401_120000.db"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "status": "restored",
            "filename": "data_20260401_120000.db",
        }
        mock_restore.assert_called_once_with("data_20260401_120000.db")

    def test_restore_missing_file_returns_404(self, test_client):
        """A FileNotFoundError from the utility maps to 404."""
        with patch(
            "backend.routes.backup.restore_backup",
            side_effect=FileNotFoundError("Backup file not found: data_x.db"),
        ):
            response = test_client.post(
                "/api/backups/restore",
                json={"filename": "data_20260401_120000.db"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_restore_invalid_filename_returns_400(self, test_client):
        """A ValueError (invalid/traversal filename) maps to a 400 response.

        ``restore_backup`` raises ValueError for filenames that don't match
        the ``data_YYYYMMDD_HHMMSS.db`` shape and for non-SQLite files —
        client input problems, surfaced via BadRequestException.
        """
        with patch(
            "backend.routes.backup.restore_backup",
            side_effect=ValueError("Invalid backup filename: ../../etc/passwd"),
        ):
            response = test_client.post(
                "/api/backups/restore",
                json={"filename": "../../etc/passwd"},
            )

        assert response.status_code == 400
        assert "Invalid backup filename" in response.json()["detail"]

    def test_restore_missing_filename_field_returns_422(self, test_client):
        """A body without ``filename`` fails request validation."""
        response = test_client.post("/api/backups/restore", json={})
        assert response.status_code == 422
