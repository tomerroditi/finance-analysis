"""Tests for GoogleDriveService token management."""

from unittest.mock import patch, MagicMock

from backend.services.google_drive_service import GoogleDriveService


class TestGoogleDriveServiceConnection:
    """Tests for Google account connection status."""

    @patch("backend.services.google_drive_service.keyring")
    def test_is_connected_returns_true_when_token_exists(self, mock_keyring):
        """Should return True when refresh token is in keyring."""
        mock_keyring.get_password.return_value = "fake-refresh-token"
        service = GoogleDriveService()
        assert service.is_connected() is True

    @patch("backend.services.google_drive_service.keyring")
    def test_is_connected_returns_false_when_no_token(self, mock_keyring):
        """Should return False when no refresh token in keyring."""
        mock_keyring.get_password.return_value = None
        service = GoogleDriveService()
        assert service.is_connected() is False

    @patch("backend.services.google_drive_service.keyring")
    def test_get_status_returns_connected_with_email(self, mock_keyring):
        """Should return connection status with email and avatar."""
        def side_effect(service, key):
            return {
                "refresh_token": "fake-token",
                "user_email": "user@gmail.com",
                "user_avatar_url": "https://example.com/avatar.jpg",
            }.get(key)

        mock_keyring.get_password.side_effect = side_effect
        service = GoogleDriveService()
        status = service.get_status()
        assert status["connected"] is True
        assert status["email"] == "user@gmail.com"
        assert status["avatar_url"] == "https://example.com/avatar.jpg"

    @patch("backend.services.google_drive_service.keyring")
    def test_get_status_returns_disconnected(self, mock_keyring):
        """Should return disconnected status when no token."""
        mock_keyring.get_password.return_value = None
        service = GoogleDriveService()
        status = service.get_status()
        assert status["connected"] is False
        assert status.get("email") is None

    @patch("backend.services.google_drive_service.keyring")
    def test_disconnect_removes_all_keys(self, mock_keyring):
        """Should remove refresh_token, user_email, user_avatar_url from keyring."""
        mock_keyring.get_password.return_value = "fake-token"
        service = GoogleDriveService()
        service.disconnect()
        assert mock_keyring.delete_password.call_count == 3

    @patch("backend.services.google_drive_service.keyring")
    def test_store_tokens_saves_to_keyring(self, mock_keyring):
        """Should save refresh token, email, and avatar to keyring."""
        service = GoogleDriveService()
        service.store_tokens(
            refresh_token="refresh-123",
            email="user@gmail.com",
            avatar_url="https://example.com/pic.jpg",
        )
        assert mock_keyring.set_password.call_count == 3


class TestGoogleDriveServiceFileOps:
    """Tests for Google Drive file operations."""

    @patch("backend.services.google_drive_service.keyring")
    def test_get_or_create_folder_creates_new(self, mock_keyring):
        """Should create a folder when none exists."""
        mock_keyring.get_password.return_value = "fake-token"
        service = GoogleDriveService()

        mock_drive = MagicMock()
        mock_drive.files().list().execute.return_value = {"files": []}
        mock_drive.files().create().execute.return_value = {"id": "folder-123"}

        folder_id = service._get_or_create_backup_folder(mock_drive)
        assert folder_id == "folder-123"

    @patch("backend.services.google_drive_service.keyring")
    def test_get_or_create_folder_returns_existing(self, mock_keyring):
        """Should return existing folder ID when found."""
        mock_keyring.get_password.return_value = "fake-token"
        service = GoogleDriveService()

        mock_drive = MagicMock()
        mock_drive.files().list().execute.return_value = {
            "files": [{"id": "existing-folder-456"}]
        }

        folder_id = service._get_or_create_backup_folder(mock_drive)
        assert folder_id == "existing-folder-456"

    @patch("backend.services.google_drive_service.keyring")
    def test_list_backups_returns_sorted(self, mock_keyring):
        """Should return backup folders sorted newest first."""
        mock_keyring.get_password.return_value = "fake-token"
        service = GoogleDriveService()

        mock_drive = MagicMock()
        # When folder_id is provided, list_backups skips _get_or_create_backup_folder
        mock_drive.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "20260401_100000", "createdTime": "2026-04-01T10:00:00Z"},
                {"id": "f2", "name": "20260403_150000", "createdTime": "2026-04-03T15:00:00Z"},
                {"id": "f3", "name": "20260402_120000", "createdTime": "2026-04-02T12:00:00Z"},
            ],
        }

        backups = service.list_backups(mock_drive, "root-folder")
        assert backups[0]["name"] == "20260403_150000"
        assert backups[1]["name"] == "20260402_120000"
        assert backups[2]["name"] == "20260401_100000"
