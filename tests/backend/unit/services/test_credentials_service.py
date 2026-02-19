import pytest
from copy import deepcopy
from unittest.mock import MagicMock

import backend.services.credentials_service as cs
from backend.repositories.credentials_repository import CredentialsRepository
from backend.services.credentials_service import CredentialsService


SAMPLE_CREDENTIALS = {
    "credit_cards": {
        "isracard": {
            "Account 1": {
                "username": "test_user",
                "card6Digits": "123456",
                "id": "000000000",
                "password": "",
            }
        },
    },
    "banks": {
        "hapoalim": {
            "Main Account": {
                "userCode": "test_code",
                "password": "",
            }
        },
    },
}


@pytest.fixture(autouse=True)
def reset_credentials(monkeypatch):
    """Reset credentials cache and singleton between tests."""
    monkeypatch.setattr(cs, "_credentials_cache", None)
    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False
    yield
    monkeypatch.setattr(cs, "_credentials_cache", None)
    CredentialsRepository._instance = None
    CredentialsRepository._initialized = False


@pytest.fixture
def mock_repo(monkeypatch):
    """Mock all CredentialsRepository methods to avoid filesystem and keyring access."""
    mock = MagicMock()
    mock.read_credentials_file.return_value = deepcopy(SAMPLE_CREDENTIALS)
    mock.get_password_from_keyring.return_value = "secret123"
    mock.write_credentials_file.return_value = None
    mock.set_password_in_keyring.return_value = None
    mock.delete_password_from_keyring.return_value = True
    mock.set_file_permissions.return_value = None
    mock.generate_default_credentials.return_value = {"banks": {}, "credit_cards": {}, "insurances": {}}

    monkeypatch.setattr(
        "backend.services.credentials_service.CredentialsRepository",
        lambda: mock,
    )
    return mock


class TestCredentialsService:
    """Tests for CredentialsService functionality."""

    def test_load_credentials(self, mock_repo):
        """Verify credentials loaded from YAML with keyring passwords."""
        service = CredentialsService()

        # Password fields should be populated from keyring
        cc_password = service.credentials["credit_cards"]["isracard"]["Account 1"]["password"]
        bank_password = service.credentials["banks"]["hapoalim"]["Main Account"]["password"]
        assert cc_password == "secret123"
        assert bank_password == "secret123"

        # Keyring should have been queried for each password field
        assert mock_repo.get_password_from_keyring.call_count == 2

    def test_generate_keyring_key(self):
        """Verify keyring key format: service:provider:account:field."""
        key = CredentialsService.generate_keyring_key(
            "credit_cards", "isracard", "Account 1", "password"
        )
        assert key == "credit_cards:isracard:Account 1:password"

    def test_get_available_data_sources(self, mock_repo):
        """Verify data sources list format: 'service - provider - account'."""
        service = CredentialsService()
        sources = service.get_available_data_sources()

        assert len(sources) == 2
        assert "credit_cards - isracard - Account 1" in sources
        assert "banks - hapoalim - Main Account" in sources

    def test_get_data_sources_credentials_filters(self, mock_repo):
        """Verify filtering credentials by selected data sources."""
        service = CredentialsService()
        filtered = service.get_data_sources_credentials(
            ["credit_cards - isracard - Account 1"]
        )

        assert "credit_cards" in filtered
        assert "isracard" in filtered["credit_cards"]
        assert "Account 1" in filtered["credit_cards"]["isracard"]
        # Bank should be filtered out
        assert "banks" not in filtered

    def test_save_credentials_stores_passwords_in_keyring(self, mock_repo):
        """Verify passwords extracted to keyring and cleared from YAML."""
        service = CredentialsService()

        new_creds = deepcopy(SAMPLE_CREDENTIALS)
        new_creds["credit_cards"]["isracard"]["Account 1"]["password"] = "new_pass"

        service.save_credentials(new_creds)

        # Password should be stored in keyring
        mock_repo.set_password_in_keyring.assert_any_call(
            "credit_cards:isracard:Account 1:password", "new_pass"
        )
        # YAML write should have been called with cleared passwords
        written_creds = mock_repo.write_credentials_file.call_args[0][0]
        assert written_creds["credit_cards"]["isracard"]["Account 1"]["password"] == ""

    def test_delete_account(self, mock_repo):
        """Verify account removed from credentials."""
        service = CredentialsService()

        service.delete_account("credit_cards", "isracard", "Account 1")

        # save_credentials should have been called (which writes YAML)
        assert mock_repo.write_credentials_file.called

    def test_get_safe_credentials_no_passwords(self, mock_repo):
        """Verify safe credentials contain no password fields."""
        service = CredentialsService()
        safe = service.get_safe_credentials()

        # Should have service -> provider -> [account_names]
        assert "credit_cards" in safe
        assert "isracard" in safe["credit_cards"]
        assert safe["credit_cards"]["isracard"] == ["Account 1"]
        assert "banks" in safe
        assert safe["banks"]["hapoalim"] == ["Main Account"]

    def test_get_accounts_list(self, mock_repo):
        """Verify flat list of accounts with service, provider, account_name."""
        service = CredentialsService()
        accounts = service.get_accounts_list()

        assert len(accounts) == 2
        account_tuples = {
            (a["service"], a["provider"], a["account_name"]) for a in accounts
        }
        assert ("credit_cards", "isracard", "Account 1") in account_tuples
        assert ("banks", "hapoalim", "Main Account") in account_tuples

    def test_get_available_providers(self, monkeypatch):
        """Verify providers filtered by test mode (production excludes test_ prefixed)."""
        monkeypatch.setattr("backend.config.AppConfig.is_test_mode", False)

        providers = CredentialsService.get_available_providers()

        assert "banks" in providers
        assert "credit_cards" in providers
        # No test providers in production mode
        for p in providers["banks"]:
            assert not p.startswith("test_")
        for p in providers["credit_cards"]:
            assert not p.startswith("test_")
        # Verify real providers are present
        assert "hapoalim" in providers["banks"]
        assert "isracard" in providers["credit_cards"]

    def test_delete_credential_cleans_keyring(self, mock_repo):
        """Verify keyring entries deleted on credential removal."""
        service = CredentialsService()

        service.delete_credential("credit_cards", "isracard", "Account 1")

        # Should attempt to delete keyring entries for password, secret, otp_key
        expected_keys = [
            "credit_cards_isracard_Account 1_password",
            "credit_cards_isracard_Account 1_secret",
            "credit_cards_isracard_Account 1_otp_key",
        ]
        actual_keys = [
            call.args[0]
            for call in mock_repo.delete_password_from_keyring.call_args_list
        ]
        assert actual_keys == expected_keys

        # YAML should have been written without the deleted account
        assert mock_repo.write_credentials_file.called
