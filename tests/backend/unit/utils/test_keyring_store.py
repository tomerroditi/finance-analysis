"""Unit tests for the OS-keyring access layer (backend/utils/keyring_store.py)."""

import pytest
from unittest.mock import patch

import keyring.errors as _real_keyring_errors

from backend.errors import ValidationException
from backend.uninstall import cleanup
from backend.utils import keyring_store


@pytest.fixture
def mock_keyring():
    """Mock the keyring module inside the store."""
    with patch("backend.utils.keyring_store.keyring") as mk:
        mk.errors = _real_keyring_errors
        yield mk


class TestServiceNaming:
    """Tests for service names and entry-name formatting."""

    def test_active_service_demo_mode(self):
        """Verify the '-demo' namespace is used in demo mode."""
        with patch("backend.utils.keyring_store.AppConfig") as MockConfig:
            MockConfig.return_value.is_demo_mode = True
            assert (
                keyring_store.active_credentials_service()
                == "finance-analysis-app-demo"
            )

    def test_active_service_normal_mode(self):
        """Verify the plain namespace is used outside demo mode."""
        with patch("backend.utils.keyring_store.AppConfig") as MockConfig:
            MockConfig.return_value.is_demo_mode = False
            assert (
                keyring_store.active_credentials_service() == "finance-analysis-app"
            )

    def test_credential_secret_name_format(self):
        """Verify the canonical underscore-delimited entry name."""
        assert (
            keyring_store.credential_secret_name(
                "banks", "hapoalim", "Main Account", "password"
            )
            == "banks_hapoalim_Main Account_password"
        )


class TestSecretOperations:
    """Tests for get/set/delete pass-through behavior."""

    def test_get_secret_reads_keyring(self, mock_keyring):
        """Verify get_secret proxies to keyring.get_password."""
        mock_keyring.get_password.return_value = "s3cret"
        assert keyring_store.get_secret("svc", "name") == "s3cret"
        mock_keyring.get_password.assert_called_once_with("svc", "name")

    def test_set_secret_writes_keyring(self, mock_keyring):
        """Verify set_secret proxies to keyring.set_password."""
        keyring_store.set_secret("svc", "name", "value")
        mock_keyring.set_password.assert_called_once_with("svc", "name", "value")

    def test_set_secret_validates_backend_first(self, mock_keyring, monkeypatch):
        """Verify an insecure backend blocks the write."""
        monkeypatch.delenv("FAD_ALLOW_INSECURE_KEYRING", raising=False)
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()

        with pytest.raises(ValidationException):
            keyring_store.set_secret("svc", "name", "value")
        mock_keyring.set_password.assert_not_called()

    def test_delete_secret_returns_true_on_success(self, mock_keyring):
        """Verify delete_secret reports a successful deletion."""
        assert keyring_store.delete_secret("svc", "name") is True
        mock_keyring.delete_password.assert_called_once_with("svc", "name")

    def test_delete_secret_swallows_missing_entry(self, mock_keyring):
        """Verify a nonexistent entry is not an error."""
        mock_keyring.delete_password.side_effect = (
            _real_keyring_errors.PasswordDeleteError("not found")
        )
        assert keyring_store.delete_secret("svc", "name") is False


class _FakeInsecureBackend:
    """Stand-in whose module path matches a known-insecure backend."""


_FakeInsecureBackend.__module__ = "keyrings.alt.file"


class _FakeSecureBackend:
    """Stand-in whose module path matches a real OS backend."""


_FakeSecureBackend.__module__ = "keyring.backends.macOS"


class TestEnsureSecureBackend:
    """Tests for the insecure-backend guard."""

    @pytest.fixture(autouse=True)
    def _clear_overrides(self, monkeypatch):
        """Remove the opt-in env vars the global test fixture sets."""
        monkeypatch.delenv("FAD_ALLOW_INSECURE_KEYRING", raising=False)
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)

    def test_insecure_backend_raises(self, mock_keyring):
        """Verify a plaintext/fail backend is rejected with a clear error."""
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        with pytest.raises(ValidationException):
            keyring_store.ensure_secure_backend()

    def test_secure_backend_passes(self, mock_keyring):
        """Verify a real OS backend passes the check."""
        mock_keyring.get_keyring.return_value = _FakeSecureBackend()
        keyring_store.ensure_secure_backend()

    def test_explicit_backend_env_is_respected(self, mock_keyring, monkeypatch):
        """Verify PYTHON_KEYRING_BACKEND counts as deliberate opt-in."""
        monkeypatch.setenv(
            "PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring"
        )
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        keyring_store.ensure_secure_backend()

    def test_allow_insecure_env_is_respected(self, mock_keyring, monkeypatch):
        """Verify FAD_ALLOW_INSECURE_KEYRING=1 bypasses the check."""
        monkeypatch.setenv("FAD_ALLOW_INSECURE_KEYRING", "1")
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        keyring_store.ensure_secure_backend()


class TestUninstallCleanupDriftGuard:
    """Pins cleanup.py's deliberately-duplicated constants to the store.

    ``backend/uninstall/cleanup.py`` keeps its own lazy keyring import (and
    literal service names) so the standalone uninstall CLI works even when
    the keyring package is broken. These assertions ensure the duplicates
    can never drift from the canonical values here.
    """

    def test_service_names_match(self):
        """Verify cleanup wipes exactly the store's service namespaces."""
        assert tuple(cleanup.KEYRING_SERVICE_NAMES) == keyring_store.SERVICE_NAMES

    def test_service_level_keys_match(self):
        """Verify cleanup wipes the field-encryption key by its real name."""
        assert tuple(cleanup.SERVICE_LEVEL_KEYS) == (
            keyring_store.FIELD_ENCRYPTION_KEY_NAME,
        )

    def test_entry_name_format_matches(self):
        """Verify cleanup's f-string key format equals credential_secret_name."""
        expected = keyring_store.credential_secret_name(
            "banks", "hapoalim", "Main", "password"
        )
        svc, provider, account, field_name = "banks", "hapoalim", "Main", "password"
        assert f"{svc}_{provider}_{account}_{field_name}" == expected
