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
    """Tests for keyring-store-backed key creation and caching."""

    def test_generates_and_stores_key_on_first_use(self, monkeypatch):
        """Verify a missing key is generated and persisted via the store."""
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_store = MagicMock()
        mock_store.get_secret.return_value = None
        mock_store.PROD_SERVICE = "finance-analysis-app"
        mock_store.FIELD_ENCRYPTION_KEY_NAME = "field-encryption-key"
        monkeypatch.setattr(crypto, "keyring_store", mock_store)

        fernet = crypto.get_fernet()

        assert fernet is not None
        mock_store.set_secret.assert_called_once()
        service, name, key = mock_store.set_secret.call_args[0]
        assert service == "finance-analysis-app"
        assert name == "field-encryption-key"
        Fernet(key.encode())  # stored key is a valid Fernet key

    def test_reuses_existing_key(self, monkeypatch):
        """Verify an existing stored key is loaded, not regenerated."""
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_store = MagicMock()
        mock_store.get_secret.return_value = Fernet.generate_key().decode()
        monkeypatch.setattr(crypto, "keyring_store", mock_store)

        crypto.get_fernet()

        mock_store.set_secret.assert_not_called()

    def test_fernet_instance_is_cached(self, monkeypatch):
        """Verify the keyring store is only consulted once per process."""
        monkeypatch.setattr(crypto, "_fernet", None)
        mock_store = MagicMock()
        mock_store.get_secret.return_value = Fernet.generate_key().decode()
        monkeypatch.setattr(crypto, "keyring_store", mock_store)

        first = crypto.get_fernet()
        second = crypto.get_fernet()

        assert first is second
        assert mock_store.get_secret.call_count == 1
