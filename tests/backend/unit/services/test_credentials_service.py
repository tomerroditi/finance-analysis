"""Unit tests for CredentialsService functionality."""

import pytest
from copy import deepcopy
from unittest.mock import MagicMock
from backend.models.transaction import BankTransaction
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.services.bank_balance_service import BankBalanceService
from backend.services.pending_refunds_service import PendingRefundsService

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
    monkeypatch.setattr(cs, "_credentials_cache", {})
    yield
    monkeypatch.setattr(cs, "_credentials_cache", {})


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
        """Verify clear_cache empties every mode's cache partition."""
        CredentialsService(MagicMock())
        assert cs._credentials_cache != {}

        CredentialsService.clear_cache()
        assert cs._credentials_cache == {}

    def test_clear_cache_forces_db_reload(self, mock_repo):
        """Verify next load_credentials hits DB after cache clear."""
        service = CredentialsService(MagicMock())
        mock_repo.get_all_credentials.reset_mock()

        CredentialsService.clear_cache()
        service.load_credentials()
        mock_repo.get_all_credentials.assert_called_once()


class TestMaskedCredentials:
    """Tests for secret masking on the API read path and sentinel round-trip on save."""

    def test_get_masked_credentials_masks_password(self, mock_repo):
        """Verify sensitive fields are replaced with the mask sentinel."""
        service = CredentialsService(MagicMock())
        fields = service.get_masked_credentials("banks", "hapoalim", "Main Account")

        assert fields["userCode"] == "test_code"
        assert fields["password"] == cs.MASK_SENTINEL

    def test_get_masked_credentials_keeps_empty_password_empty(self, mock_repo):
        """Verify an empty stored password is returned empty, not masked."""
        creds = deepcopy(SAMPLE_CREDENTIALS)
        creds["banks"]["hapoalim"]["Main Account"]["password"] = ""
        mock_repo.get_all_credentials.return_value = creds

        service = CredentialsService(MagicMock())
        fields = service.get_masked_credentials("banks", "hapoalim", "Main Account")

        assert fields["password"] == ""

    def test_get_masked_credentials_unknown_account_returns_empty(self, mock_repo):
        """Verify an unknown account yields an empty dict."""
        service = CredentialsService(MagicMock())
        assert service.get_masked_credentials("banks", "hapoalim", "Nope") == {}

    def test_save_credentials_skips_sentinel_fields(self, mock_repo):
        """Verify sentinel-valued fields are stripped so stored secrets are kept."""
        service = CredentialsService(MagicMock())
        service.save_credentials({
            "banks": {
                "hapoalim": {
                    "Main Account": {
                        "userCode": "new_code",
                        "password": cs.MASK_SENTINEL,
                    }
                }
            }
        })

        mock_repo.save_credentials.assert_called_once_with(
            "banks", "hapoalim", "Main Account", {"userCode": "new_code"}
        )

    def test_save_credentials_all_sentinel_skips_account(self, mock_repo):
        """Verify an account whose every field is the sentinel is not saved."""
        service = CredentialsService(MagicMock())
        service.save_credentials({
            "banks": {
                "hapoalim": {
                    "Main Account": {"password": cs.MASK_SENTINEL}
                }
            }
        })

        mock_repo.save_credentials.assert_not_called()

    def test_save_credentials_new_password_still_saved(self, mock_repo):
        """Verify a genuinely new password value is passed through to the repo."""
        service = CredentialsService(MagicMock())
        service.save_credentials({
            "banks": {
                "hapoalim": {
                    "Main Account": {
                        "userCode": "new_code",
                        "password": "brand-new-secret",
                    }
                }
            }
        })

        mock_repo.save_credentials.assert_called_once_with(
            "banks", "hapoalim", "Main Account",
            {"userCode": "new_code", "password": "brand-new-secret"},
        )


class TestDeleteClearsScrapeHistory:
    """The scrape watermark tracks whether the data was kept or erased."""

    def test_re_added_account_gets_full_backfill(self, db_session, monkeypatch):
        """Erasing the data also clears the watermark, forcing a fresh year.

        Scrape history outliving an erased account made a re-added account
        resume from its old "last successful scrape" date, silently skipping
        ~12 months of backfill with no way for the user to force it. It is
        only cleared alongside the data — wiping it while the transactions
        stayed would force a redundant re-scrape of rows already stored.
        """
        from datetime import date

        from backend.repositories.scraping_history_repository import (
            ScrapingHistoryRepository,
        )
        from backend.services.scraping_service import ScrapingService

        history = ScrapingHistoryRepository(db_session)
        scrape_id = history.record_scrape_start(
            "banks", "hapoalim", "Main", date.today()
        )
        history.record_scrape_end(scrape_id, "success")
        assert history.get_last_successful_scrape_date(
            "banks", "hapoalim", "Main"
        )

        service = CredentialsService(db_session)
        monkeypatch.setattr(
            service.repository, "delete_credentials", lambda *a, **k: None
        )
        service.delete_credential(
            "banks", "hapoalim", "Main", delete_data=True
        )

        assert (
            history.get_last_successful_scrape_date("banks", "hapoalim", "Main")
            is None
        )
        start = ScrapingService(db_session)._get_scraper_start_date(
            "banks", "hapoalim", "Main"
        )
        assert (date.today() - start).days >= 364


def _seed_account(db, monkeypatch):
    """Seed two bank accounts, a balance with prior wealth, and a scrape."""
    db.add(BankTransaction(
        id="ad1", date="2024-01-05", provider="hapoalim", account_name="Main",
        description="rent", amount=-3000.0, category="Home", tag="Rent",
        source="bank_transactions", type="normal", status="completed"))
    db.add(BankTransaction(
        id="ad2", date="2024-01-06", provider="hapoalim", account_name="Other",
        description="keep me", amount=-50.0, category="Food", tag=None,
        source="bank_transactions", type="normal", status="completed"))
    db.commit()
    BankBalanceRepository(db).upsert(
        provider="hapoalim", account_name="Main",
        balance=25000.0, prior_wealth_amount=20000.0)
    from datetime import date
    h = ScrapingHistoryRepository(db)
    sid = h.record_scrape_start("banks", "hapoalim", "Main", date.today())
    h.record_scrape_end(sid, "success")
    svc = CredentialsService(db)
    monkeypatch.setattr(svc.repository, "delete_credentials", lambda *a, **k: None)
    return svc, h


class TestKeepData:
    """delete_data=False removes only the connection."""

    def test_transactions_balance_and_history_survive(self, db_session, monkeypatch):
        """Nothing but the credential is touched."""
        svc, hist = _seed_account(db_session, monkeypatch)
        res = svc.delete_credential("banks", "hapoalim", "Main")
        assert res["transactions_deleted"] == 0
        assert db_session.query(BankTransaction).count() == 2
        assert BankBalanceService(db_session).get_total_prior_wealth() == 20000.0
        assert hist.get_last_successful_scrape_date("banks", "hapoalim", "Main")


class TestRemoveData:
    """delete_data=True removes the account's data and its dependents."""

    def test_only_that_accounts_transactions_go(self, db_session, monkeypatch):
        """Sibling accounts on the same provider are untouched."""
        svc, hist = _seed_account(db_session, monkeypatch)
        res = svc.delete_credential(
            "banks", "hapoalim", "Main", delete_data=True)
        assert res["transactions_deleted"] == 1
        remaining = db_session.query(BankTransaction).all()
        assert [t.account_name for t in remaining] == ["Other"]

    def test_history_cleared_so_next_scrape_backfills(self, db_session, monkeypatch):
        """The watermark goes, so reconnecting starts a fresh year."""
        svc, hist = _seed_account(db_session, monkeypatch)
        svc.delete_credential("banks", "hapoalim", "Main", delete_data=True)
        assert hist.get_last_successful_scrape_date(
            "banks", "hapoalim", "Main") is None

    def test_dependent_records_are_purged(self, db_session, monkeypatch):
        """A pending refund on a deleted transaction does not survive."""
        svc, _ = _seed_account(db_session, monkeypatch)
        uid = db_session.query(BankTransaction).filter_by(id="ad1").one().unique_id
        PendingRefundsService(db_session).mark_as_pending_refund(
            "transaction", uid, "banks", 100.0)

        svc.delete_credential("banks", "hapoalim", "Main", delete_data=True)

        assert PendingRefundsService(db_session).get_all_pending() == []

    def test_prior_wealth_survives_a_keep_delete(self, db_session, monkeypatch):
        """Disconnecting must not destroy the account's prior wealth.

        The balance row carries ``prior_wealth_amount``. Dropping it while the
        transactions stayed removed money from net worth that the surviving
        history still accounted for.
        """
        svc, _ = _seed_account(db_session, monkeypatch)
        before = BankBalanceService(db_session).get_total_prior_wealth()
        svc.delete_credential("banks", "hapoalim", "Main")
        assert BankBalanceService(db_session).get_total_prior_wealth() == before

    def test_keeping_data_keeps_the_watermark(self, db_session, monkeypatch):
        """Disconnecting without erasing leaves the scrape watermark intact.

        Reconnecting then resumes from where it left off rather than
        re-scraping a year of transactions that are still stored.
        """
        from datetime import date

        history = ScrapingHistoryRepository(db_session)
        scrape_id = history.record_scrape_start(
            "banks", "hapoalim", "Main", date.today()
        )
        history.record_scrape_end(scrape_id, "success")

        service = CredentialsService(db_session)
        monkeypatch.setattr(
            service.repository, "delete_credentials", lambda *a, **k: None
        )
        service.delete_credential("banks", "hapoalim", "Main")

        assert history.get_last_successful_scrape_date(
            "banks", "hapoalim", "Main"
        )
