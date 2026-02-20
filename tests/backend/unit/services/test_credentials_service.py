"""Unit tests for CredentialsService functionality."""

import pytest
from copy import deepcopy
from unittest.mock import MagicMock

import backend.services.credentials_service as cs
from backend.services.credentials_service import CredentialsService


SAMPLE_CREDENTIALS = {
    "credit_cards": {
        "isracard": {
            "Account 1": {
                "username": "test_user",
                "card6Digits": "123456",
                "id": "000000000",
                "password": "secret123",
            }
        },
    },
    "banks": {
        "hapoalim": {
            "Main Account": {
                "userCode": "test_code",
                "password": "secret123",
            }
        },
    },
}


@pytest.fixture(autouse=True)
def reset_credentials_cache(monkeypatch):
    """Reset credentials cache between tests."""
    monkeypatch.setattr(cs, "_credentials_cache", None)
    yield
    monkeypatch.setattr(cs, "_credentials_cache", None)


@pytest.fixture
def mock_repo(monkeypatch):
    """Mock CredentialsRepository to avoid DB and keyring access."""
    mock = MagicMock()
    mock.get_all_credentials.return_value = deepcopy(SAMPLE_CREDENTIALS)
    mock.list_accounts.return_value = [
        {"service": "credit_cards", "provider": "isracard", "account_name": "Account 1"},
        {"service": "banks", "provider": "hapoalim", "account_name": "Main Account"},
    ]
    mock.save_credentials.return_value = None
    mock.delete_credentials.return_value = None

    monkeypatch.setattr(
        "backend.services.credentials_service.CredentialsRepository",
        lambda db: mock,
    )
    return mock


class TestCredentialsService:
    """Tests for CredentialsService functionality."""

    def test_load_credentials(self, mock_repo):
        """Verify credentials loaded from DB with keyring passwords."""
        service = CredentialsService(MagicMock())

        cc_password = service.credentials["credit_cards"]["isracard"]["Account 1"]["password"]
        bank_password = service.credentials["banks"]["hapoalim"]["Main Account"]["password"]
        assert cc_password == "secret123"
        assert bank_password == "secret123"

    def test_get_available_data_sources(self, mock_repo):
        """Verify data sources list format: 'service - provider - account'."""
        service = CredentialsService(MagicMock())
        sources = service.get_available_data_sources()

        assert len(sources) == 2
        assert "credit_cards - isracard - Account 1" in sources
        assert "banks - hapoalim - Main Account" in sources

    def test_get_data_sources_credentials_filters(self, mock_repo):
        """Verify filtering credentials by selected data sources."""
        service = CredentialsService(MagicMock())
        filtered = service.get_data_sources_credentials(
            ["credit_cards - isracard - Account 1"]
        )

        assert "credit_cards" in filtered
        assert "isracard" in filtered["credit_cards"]
        assert "Account 1" in filtered["credit_cards"]["isracard"]
        assert "banks" not in filtered

    def test_save_credentials_calls_repo(self, mock_repo):
        """Verify save_credentials delegates to repo per account."""
        service = CredentialsService(MagicMock())

        new_creds = deepcopy(SAMPLE_CREDENTIALS)
        new_creds["credit_cards"]["isracard"]["Account 1"]["password"] = "new_pass"

        service.save_credentials(new_creds)

        assert mock_repo.save_credentials.called

    def test_delete_account(self, mock_repo):
        """Verify account removed via repo."""
        service = CredentialsService(MagicMock())
        service.delete_account("credit_cards", "isracard", "Account 1")

        mock_repo.delete_credentials.assert_called_once_with(
            "credit_cards", "isracard", "Account 1"
        )

    def test_get_safe_credentials_no_passwords(self, mock_repo):
        """Verify safe credentials contain no password fields."""
        service = CredentialsService(MagicMock())
        safe = service.get_safe_credentials()

        assert "credit_cards" in safe
        assert "isracard" in safe["credit_cards"]
        assert safe["credit_cards"]["isracard"] == ["Account 1"]
        assert "banks" in safe
        assert safe["banks"]["hapoalim"] == ["Main Account"]

    def test_get_accounts_list(self, mock_repo):
        """Verify flat list of accounts with service, provider, account_name."""
        service = CredentialsService(MagicMock())
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
        for p in providers["banks"]:
            assert not p.startswith("test_")
        for p in providers["credit_cards"]:
            assert not p.startswith("test_")
        assert "hapoalim" in providers["banks"]
        assert "isracard" in providers["credit_cards"]

    def test_delete_credential(self, mock_repo):
        """Verify delete_credential delegates to repo."""
        service = CredentialsService(MagicMock())
        service.delete_credential("credit_cards", "isracard", "Account 1")

        mock_repo.delete_credentials.assert_called_once_with(
            "credit_cards", "isracard", "Account 1"
        )
