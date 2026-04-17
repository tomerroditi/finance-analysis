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
        monkeypatch.setattr("backend.config.AppConfig.is_demo_mode", False)

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


class TestCredentialsCacheHit:
    """Tests for credentials cache hit branch."""

    def test_cache_hit_returns_cached_data(self, mock_repo, monkeypatch):
        """Verify load_credentials returns cached data without DB lookup on second call."""
        service = CredentialsService(MagicMock())
        # First call populates cache
        assert mock_repo.get_all_credentials.call_count == 1

        # Manually call load_credentials again — should hit cache (line 57)
        mock_repo.get_all_credentials.reset_mock()
        result = service.load_credentials()
        mock_repo.get_all_credentials.assert_not_called()
        assert "credit_cards" in result

    def test_cache_returns_deep_copy(self, mock_repo):
        """Verify cached credentials are deep-copied to prevent mutation."""
        service = CredentialsService(MagicMock())
        creds1 = service.load_credentials()
        creds2 = service.load_credentials()

        creds1["credit_cards"]["isracard"]["Account 1"]["password"] = "mutated"
        assert creds2["credit_cards"]["isracard"]["Account 1"]["password"] == "secret123"


class TestSaveCredentialsTypeGuards:
    """Tests for type guard branches in save_credentials."""

    def test_skips_non_dict_providers(self, mock_repo):
        """Verify save_credentials skips non-dict provider values (line 82)."""
        service = CredentialsService(MagicMock())
        service.save_credentials({"credit_cards": "not_a_dict"})
        mock_repo.save_credentials.assert_not_called()

    def test_skips_non_dict_accounts(self, mock_repo):
        """Verify save_credentials skips non-dict account values (line 85)."""
        service = CredentialsService(MagicMock())
        service.save_credentials({"credit_cards": {"isracard": "not_a_dict"}})
        mock_repo.save_credentials.assert_not_called()

    def test_skips_non_dict_fields(self, mock_repo):
        """Verify save_credentials skips non-dict field values (line 88)."""
        service = CredentialsService(MagicMock())
        service.save_credentials({"credit_cards": {"isracard": {"Acct": "not_a_dict"}}})
        mock_repo.save_credentials.assert_not_called()

    def test_skips_empty_field_values(self, mock_repo):
        """Verify save_credentials skips accounts where all fields are empty (line 90)."""
        service = CredentialsService(MagicMock())
        service.save_credentials({"credit_cards": {"isracard": {"Acct": {"user": "", "pass": ""}}}})
        mock_repo.save_credentials.assert_not_called()

    def test_skips_empty_dict_fields(self, mock_repo):
        """Verify save_credentials skips accounts with empty fields dict."""
        service = CredentialsService(MagicMock())
        service.save_credentials({"credit_cards": {"isracard": {"Acct": {}}}})
        mock_repo.save_credentials.assert_not_called()

    def test_saves_valid_mixed_with_invalid(self, mock_repo):
        """Verify save_credentials processes valid accounts while skipping invalid ones."""
        service = CredentialsService(MagicMock())
        service.save_credentials({
            "banks": {
                "hapoalim": {
                    "Good": {"user": "x", "pass": "y"},
                    "Bad": "not_a_dict",
                },
                "bad_provider": "not_a_dict",
            },
            "bad_service": "not_a_dict",
        })
        mock_repo.save_credentials.assert_called_once_with(
            "banks", "hapoalim", "Good", {"user": "x", "pass": "y"}
        )


class TestGetScraperCredentials:
    """Tests for get_scraper_credentials filtering."""

    def test_filter_by_string_params(self, mock_repo):
        """Verify filtering by single string service/provider/account."""
        service = CredentialsService(MagicMock())
        result = service.get_scraper_credentials("banks", "hapoalim", "Main Account")

        assert "banks" in result
        assert "hapoalim" in result["banks"]
        assert "Main Account" in result["banks"]["hapoalim"]

    def test_filter_by_list_params(self, mock_repo):
        """Verify filtering by list of services/providers/accounts."""
        service = CredentialsService(MagicMock())
        result = service.get_scraper_credentials(
            ["banks", "credit_cards"],
            ["hapoalim", "isracard"],
            ["Main Account", "Account 1"],
        )

        assert "banks" in result
        assert "credit_cards" in result

    def test_nonexistent_service_returns_empty(self, mock_repo):
        """Verify nonexistent service returns empty dict."""
        service = CredentialsService(MagicMock())
        result = service.get_scraper_credentials("insurance", "provider", "acct")
        assert result == {}

    def test_nonexistent_provider_returns_empty_nested(self, mock_repo):
        """Verify nonexistent provider returns service key with empty provider dict."""
        service = CredentialsService(MagicMock())
        result = service.get_scraper_credentials("banks", "leumi", "Main Account")
        assert result == {"banks": {}}

    def test_nonexistent_account_returns_empty_nested(self, mock_repo):
        """Verify nonexistent account returns empty account dict."""
        service = CredentialsService(MagicMock())
        result = service.get_scraper_credentials("banks", "hapoalim", "Missing")
        assert result == {"banks": {"hapoalim": {}}}


class TestSeedDemoCredentials:
    """Tests for demo credential seeding."""

    def test_seeds_all_when_none_exist(self, mock_repo):
        """Verify every demo credential is created when none exist.

        Seeds cover bank (hapoalim), credit cards (max, visa cal) and insurance
        (hafenix) — four accounts in total. Each should trigger a save.
        """
        from backend.errors import EntityNotFoundException

        mock_repo.get_credentials.side_effect = EntityNotFoundException("Not found")
        service = CredentialsService(MagicMock())
        service.seed_demo_credentials()

        assert mock_repo.save_credentials.call_count == 4
        saved_targets = {
            (call.args[0], call.args[1], call.args[2])
            for call in mock_repo.save_credentials.call_args_list
        }
        assert ("banks", "hapoalim", "Main Account") in saved_targets
        assert ("credit_cards", "max", "Family Card") in saved_targets
        assert ("credit_cards", "visa cal", "Online Shopping") in saved_targets
        assert ("insurances", "hafenix", "The Cohens") in saved_targets

    def test_skips_existing_credentials(self, mock_repo):
        """Verify existing demo credentials are not re-inserted."""
        mock_repo.get_credentials.return_value = {"username": "demo"}
        service = CredentialsService(MagicMock())
        service.seed_demo_credentials()

        mock_repo.save_credentials.assert_not_called()

    def test_partial_seeding(self, mock_repo):
        """Verify only missing demo credentials are created.

        The first credential already exists (returned by the repo); the
        remaining three raise EntityNotFoundException and therefore get saved.
        """
        from backend.errors import EntityNotFoundException

        call_count = 0

        def get_creds_side_effect(service, provider, account):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"username": "demo"}  # First exists
            raise EntityNotFoundException("Not found")

        mock_repo.get_credentials.side_effect = get_creds_side_effect
        service = CredentialsService(MagicMock())
        service.seed_demo_credentials()

        assert mock_repo.save_credentials.call_count == 3


class TestClearCache:
    """Tests for static cache clearing."""

    def test_clear_cache_sets_none(self, mock_repo, monkeypatch):
        """Verify clear_cache sets module-level cache to None."""
        CredentialsService(MagicMock())
        assert cs._credentials_cache is not None

        CredentialsService.clear_cache()
        assert cs._credentials_cache is None

    def test_clear_cache_forces_db_reload(self, mock_repo):
        """Verify next load_credentials hits DB after cache clear."""
        service = CredentialsService(MagicMock())
        mock_repo.get_all_credentials.reset_mock()

        CredentialsService.clear_cache()
        service.load_credentials()
        mock_repo.get_all_credentials.assert_called_once()
