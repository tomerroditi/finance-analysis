"""Unit tests for credential field encryption (backend/utils/crypto.py)."""

import pytest
from cryptography.fernet import Fernet
from unittest.mock import MagicMock, patch

from backend.errors import ValidationException
from backend.utils import crypto


class TestEncryptDecryptRoundtrip:
    """Tests for the encrypt/decrypt envelope format."""

    def test_roundtrip_restores_original_fields(self):
        """Verify decrypt(encrypt(fields)) returns the original dict."""
        fields = {"userCode": "abc", "id": "123456789", "card6Digits": "654321"}
        assert crypto.decrypt_fields(crypto.encrypt_fields(fields)) == fields

    def test_encrypted_envelope_hides_plaintext(self):
        """Verify the stored envelope contains no plaintext field values."""
        stored = crypto.encrypt_fields({"id": "123456789"})
        assert set(stored.keys()) == {crypto.ENCRYPTED_MARKER}
        assert "123456789" not in stored[crypto.ENCRYPTED_MARKER]

    def test_is_encrypted_detects_envelope(self):
        """Verify is_encrypted distinguishes envelopes from plaintext dicts."""
        assert crypto.is_encrypted(crypto.encrypt_fields({"a": 1}))
        assert not crypto.is_encrypted({"userCode": "abc"})

    def test_decrypt_passes_legacy_plaintext_through(self):
        """Verify pre-encryption plaintext rows are returned unchanged."""
        legacy = {"userCode": "abc", "num": "42"}
        result = crypto.decrypt_fields(legacy)
        assert result == legacy
        assert result is not legacy  # defensive copy

    def test_decrypt_with_wrong_key_raises_validation_exception(self):
        """Verify a key mismatch surfaces a clear ValidationException."""
        stored = crypto.encrypt_fields({"id": "123"})
        with patch.object(crypto, "_fernet", Fernet(Fernet.generate_key())):
            with pytest.raises(ValidationException):
                crypto.decrypt_fields(stored)


class TestGetFernetKeyManagement:
    """Tests for keyring-backed key creation and caching."""

    def test_generates_and_stores_key_on_first_use(self, monkeypatch):
        """Verify a missing keyring key is generated and persisted."""
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        fernet = crypto.get_fernet()

        assert fernet is not None
        mock_keyring.set_password.assert_called_once()
        service, name, key = mock_keyring.set_password.call_args[0]
        assert service == "finance-analysis-app"
        assert name == "field-encryption-key"
        Fernet(key.encode())  # stored key is a valid Fernet key

    def test_reuses_existing_keyring_key(self, monkeypatch):
        """Verify an existing keyring key is loaded, not regenerated."""
        existing_key = Fernet.generate_key().decode()
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = existing_key
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        crypto.get_fernet()

        mock_keyring.set_password.assert_not_called()

    def test_fernet_instance_is_cached(self, monkeypatch):
        """Verify the keyring is only consulted once per process."""
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = Fernet.generate_key().decode()
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        first = crypto.get_fernet()
        second = crypto.get_fernet()

        assert first is second
        assert mock_keyring.get_password.call_count == 1


class _FakeInsecureBackend:
    """Stand-in whose module path matches a known-insecure backend."""


_FakeInsecureBackend.__module__ = "keyrings.alt.file"


class _FakeSecureBackend:
    """Stand-in whose module path matches a real OS backend."""


_FakeSecureBackend.__module__ = "keyring.backends.macOS"


class TestEnsureSecureKeyringBackend:
    """Tests for the insecure-backend guard."""

    @pytest.fixture(autouse=True)
    def _clear_overrides(self, monkeypatch):
        """Remove the opt-in env vars the global test fixture sets."""
        monkeypatch.delenv("FAD_ALLOW_INSECURE_KEYRING", raising=False)
        monkeypatch.delenv("PYTHON_KEYRING_BACKEND", raising=False)

    def test_insecure_backend_raises(self, monkeypatch):
        """Verify a plaintext/fail backend is rejected with a clear error."""
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        with pytest.raises(ValidationException):
            crypto.ensure_secure_keyring_backend()

    def test_secure_backend_passes(self, monkeypatch):
        """Verify a real OS backend passes the check."""
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = _FakeSecureBackend()
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        crypto.ensure_secure_keyring_backend()

    def test_explicit_backend_env_is_respected(self, monkeypatch):
        """Verify PYTHON_KEYRING_BACKEND counts as deliberate opt-in."""
        monkeypatch.setenv(
            "PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring"
        )
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        crypto.ensure_secure_keyring_backend()

    def test_allow_insecure_env_is_respected(self, monkeypatch):
        """Verify FAD_ALLOW_INSECURE_KEYRING=1 bypasses the check."""
        monkeypatch.setenv("FAD_ALLOW_INSECURE_KEYRING", "1")
        mock_keyring = MagicMock()
        mock_keyring.get_keyring.return_value = _FakeInsecureBackend()
        monkeypatch.setattr(crypto, "keyring", mock_keyring)

        crypto.ensure_secure_keyring_backend()
