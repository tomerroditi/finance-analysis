"""
Google Drive service for OAuth and Drive API operations.

Handles Google account connection, token management via OS keyring,
and Google Drive file operations for backup/restore.
"""

import logging
import os

import keyring

from backend.config import AppConfig

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
_KEYRING_KEYS = ("refresh_token", "user_email", "user_avatar_url")
_OAUTH_KEYRING_KEYS = ("client_id", "client_secret")


class GoogleDriveService:
    """Manages Google OAuth tokens and Drive API operations."""

    BACKUP_FOLDER_NAME = "Finance Analysis Backups"

    def __init__(self):
        self._config = AppConfig()

    @property
    def _keyring_service(self) -> str:
        return self._config.get_google_keyring_service()

    def is_configured(self) -> bool:
        """Check if Google OAuth client credentials are set up.

        Returns
        -------
        bool
            True if client_id and client_secret are stored in the OS keyring.
        """
        client_id = keyring.get_password(self._keyring_service, "client_id")
        client_secret = keyring.get_password(self._keyring_service, "client_secret")
        return bool(client_id and client_secret)

    def save_oauth_credentials(self, client_id: str, client_secret: str) -> None:
        """Store Google OAuth client credentials in the OS keyring.

        Parameters
        ----------
        client_id : str
            The Google OAuth client ID.
        client_secret : str
            The Google OAuth client secret.
        """
        keyring.set_password(self._keyring_service, "client_id", client_id)
        keyring.set_password(self._keyring_service, "client_secret", client_secret)

    def _get_client_credentials(self) -> tuple[str, str]:
        """Retrieve OAuth client credentials from keyring, falling back to env vars.

        Returns
        -------
        tuple[str, str]
            (client_id, client_secret)

        Raises
        ------
        ValueError
            If credentials are not found in keyring or env vars.
        """
        client_id = keyring.get_password(self._keyring_service, "client_id")
        client_secret = keyring.get_password(self._keyring_service, "client_secret")
        if not client_id or not client_secret:
            client_id = os.environ.get("GOOGLE_CLIENT_ID")
            client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials not configured")
        return client_id, client_secret

    def is_connected(self) -> bool:
        """Check if a Google account is connected (refresh token exists).

        Returns
        -------
        bool
            True if a refresh token is stored in the OS keyring, False otherwise.
        """
        token = keyring.get_password(self._keyring_service, "refresh_token")
        return token is not None

    def get_status(self) -> dict:
        """Get Google account connection status.

        Returns
        -------
        dict
            A dict with ``connected`` bool. When connected, also includes
            ``email`` and ``avatar_url`` keys.
        """
        token = keyring.get_password(self._keyring_service, "refresh_token")
        if not token:
            return {"connected": False}
        return {
            "connected": True,
            "email": keyring.get_password(self._keyring_service, "user_email"),
            "avatar_url": keyring.get_password(self._keyring_service, "user_avatar_url"),
        }

    def store_tokens(self, refresh_token: str, email: str, avatar_url: str | None = None) -> None:
        """Store OAuth tokens and user info in keyring.

        Parameters
        ----------
        refresh_token : str
            The OAuth2 refresh token from Google.
        email : str
            The authenticated user's email address.
        avatar_url : str or None, optional
            URL of the user's Google profile picture.
        """
        keyring.set_password(self._keyring_service, "refresh_token", refresh_token)
        keyring.set_password(self._keyring_service, "user_email", email)
        keyring.set_password(self._keyring_service, "user_avatar_url", avatar_url or "")

    def disconnect(self) -> None:
        """Remove all Google tokens from keyring.

        Silently ignores missing entries so the call is always safe to make
        regardless of the current connection state.
        """
        for key in _KEYRING_KEYS:
            try:
                keyring.delete_password(self._keyring_service, key)
            except keyring.errors.PasswordDeleteError:
                pass

    def get_auth_url(self) -> str:
        """Generate Google OAuth authorization URL.

        Returns
        -------
        str
            The URL to redirect the user to for Google OAuth consent.

        Raises
        ------
        ValueError
            If ``GOOGLE_CLIENT_ID`` or ``GOOGLE_CLIENT_SECRET`` env vars are not set.
        """
        from google_auth_oauthlib.flow import Flow

        client_id, client_secret = self._get_client_credentials()

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri="http://localhost:8000/api/google/callback",
        )
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
        return auth_url

    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for tokens.

        Fetches the token, retrieves user info, then stores all credentials
        in the OS keyring via :meth:`store_tokens`.

        Parameters
        ----------
        code : str
            The authorization code returned by Google after user consent.

        Returns
        -------
        dict
            A dict with ``refresh_token``, ``email``, and ``avatar_url`` keys.
        """
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build

        client_id, client_secret = self._get_client_credentials()

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri="http://localhost:8000/api/google/callback",
        )
        flow.fetch_token(code=code)
        credentials = flow.credentials

        oauth2_service = build("oauth2", "v2", credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()

        refresh_token = credentials.refresh_token
        email = user_info.get("email", "")
        avatar_url = user_info.get("picture", "")

        self.store_tokens(refresh_token, email, avatar_url)
        return {"refresh_token": refresh_token, "email": email, "avatar_url": avatar_url}

    def _get_credentials(self):
        """Build Google credentials from stored refresh token.

        Returns
        -------
        google.oauth2.credentials.Credentials or None
            Credentials object if a refresh token is stored, otherwise None.
        """
        from google.oauth2.credentials import Credentials

        refresh_token = keyring.get_password(self._keyring_service, "refresh_token")
        if not refresh_token:
            return None

        try:
            client_id, client_secret = self._get_client_credentials()
        except ValueError:
            return None

        return Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

    def _get_drive_service(self):
        """Build a Google Drive API service client.

        Returns
        -------
        googleapiclient.discovery.Resource or None
            An authenticated Drive v3 service resource, or None if not connected.
        """
        from googleapiclient.discovery import build

        creds = self._get_credentials()
        if not creds:
            return None
        return build("drive", "v3", credentials=creds)

    def _get_or_create_backup_folder(self, drive_service) -> str:
        """Get the root backup folder ID, creating it if it does not exist.

        Parameters
        ----------
        drive_service : googleapiclient.discovery.Resource
            An authenticated Drive v3 service resource.

        Returns
        -------
        str
            The Google Drive folder ID for :attr:`BACKUP_FOLDER_NAME`.
        """
        query = (
            f"name='{self.BACKUP_FOLDER_NAME}' "
            "and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        result = drive_service.files().list(q=query, fields="files(id)").execute()
        files = result.get("files", [])
        if files:
            return files[0]["id"]

        metadata = {
            "name": self.BACKUP_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = drive_service.files().create(body=metadata, fields="id").execute()
        return folder["id"]

    def list_backups(self, drive_service=None, folder_id: str | None = None) -> list[dict]:
        """List all backup subfolders sorted newest first.

        Parameters
        ----------
        drive_service : googleapiclient.discovery.Resource or None, optional
            An authenticated Drive v3 service resource. If None, one is built
            via :meth:`_get_drive_service`.
        folder_id : str or None, optional
            Root backup folder ID. If None, looked up via
            :meth:`_get_or_create_backup_folder`.

        Returns
        -------
        list[dict]
            List of folder metadata dicts (id, name, createdTime), sorted by
            ``createdTime`` descending (newest first).
        """
        if drive_service is None:
            drive_service = self._get_drive_service()
            if not drive_service:
                return []
        if folder_id is None:
            folder_id = self._get_or_create_backup_folder(drive_service)

        query = (
            f"'{folder_id}' in parents "
            "and mimeType='application/vnd.google-apps.folder' "
            "and trashed=false"
        )
        result = (
            drive_service.files()
            .list(q=query, fields="files(id,name,createdTime)", orderBy="createdTime desc")
            .execute()
        )
        folders = result.get("files", [])
        return sorted(folders, key=lambda f: f.get("createdTime", ""), reverse=True)

    def upload_backup(self, folder_id: str, subfolder_name: str, files: dict[str, str]) -> str:
        """Upload a backup bundle to Google Drive.

        Creates a timestamped subfolder and uploads all files into it.

        Parameters
        ----------
        folder_id : str
            Parent backup folder ID.
        subfolder_name : str
            Name for the backup subfolder (e.g. ``"20260404_120000"``).
        files : dict[str, str]
            Mapping of filename -> local file path to upload.

        Returns
        -------
        str
            ID of the created subfolder.
        """
        from googleapiclient.http import MediaFileUpload

        drive_service = self._get_drive_service()
        if not drive_service:
            raise RuntimeError("Google Drive not connected")

        subfolder_metadata = {
            "name": subfolder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [folder_id],
        }
        subfolder = drive_service.files().create(body=subfolder_metadata, fields="id").execute()
        subfolder_id = subfolder["id"]

        for filename, local_path in files.items():
            media = MediaFileUpload(local_path, resumable=True)
            file_metadata = {"name": filename, "parents": [subfolder_id]}
            drive_service.files().create(
                body=file_metadata, media_body=media, fields="id"
            ).execute()
            logger.info("Uploaded %s to Drive backup %s", filename, subfolder_name)

        return subfolder_id

    def download_backup(self, subfolder_id: str, dest_dir: str) -> list[str]:
        """Download all files from a backup subfolder to a local directory.

        Parameters
        ----------
        subfolder_id : str
            Google Drive ID of the backup subfolder to download.
        dest_dir : str
            Local directory path where files will be written.

        Returns
        -------
        list[str]
            Absolute paths of the downloaded local files.
        """
        import io
        from googleapiclient.http import MediaIoBaseDownload

        drive_service = self._get_drive_service()
        os.makedirs(dest_dir, exist_ok=True)

        query = f"'{subfolder_id}' in parents and trashed=false"
        result = drive_service.files().list(q=query, fields="files(id,name)").execute()
        remote_files = result.get("files", [])

        downloaded_paths: list[str] = []
        for remote_file in remote_files:
            file_id = remote_file["id"]
            file_name = remote_file["name"]
            dest_path = os.path.join(dest_dir, file_name)

            request = drive_service.files().get_media(fileId=file_id)
            with open(dest_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            downloaded_paths.append(dest_path)
            logger.info("Downloaded %s from Drive subfolder %s", file_name, subfolder_id)

        return downloaded_paths

    def delete_backup(self, subfolder_id: str) -> None:
        """Permanently delete a backup subfolder and all its contents.

        Parameters
        ----------
        subfolder_id : str
            Google Drive ID of the backup subfolder to delete.
        """
        drive_service = self._get_drive_service()
        drive_service.files().delete(fileId=subfolder_id).execute()
        logger.info("Deleted Drive subfolder %s", subfolder_id)
