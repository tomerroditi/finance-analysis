"""Unit tests for InsuranceAccountRepository CRUD and upsert-by-policy-id."""

import pytest

from backend.models.insurance_account import InsuranceAccount
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)


def _pension_fields(**overrides) -> dict:
    """Return a minimal valid pension account field dict."""
    fields = {
        "provider": "hafenix",
        "policy_id": "pol-001",
        "policy_type": "pension",
        "pension_type": "makifa",
        "account_name": "Phoenix Pension",
        "balance": 150000.0,
        "balance_date": "2026-06-30",
    }
    fields.update(overrides)
    return fields


class TestInsuranceAccountRepositoryQueries:
    """Tests for the read paths."""

    def test_get_all_empty_returns_empty_list(self, db_session):
        """A fresh DB yields an empty list."""
        repo = InsuranceAccountRepository(db_session)
        assert repo.get_all() == []

    def test_get_by_policy_type_filters(self, db_session):
        """get_by_policy_type returns only accounts of the requested type."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(**_pension_fields())
        repo.upsert(
            **_pension_fields(
                policy_id="pol-002",
                policy_type="hishtalmut",
                pension_type=None,
                account_name="Phoenix KH",
            )
        )

        pensions = repo.get_by_policy_type("pension")
        hishtalmut = repo.get_by_policy_type("hishtalmut")

        assert [a.policy_id for a in pensions] == ["pol-001"]
        assert [a.policy_id for a in hishtalmut] == ["pol-002"]

    def test_get_by_policy_id_returns_none_for_unknown(self, db_session):
        """An unknown policy_id resolves to None."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(**_pension_fields())

        assert repo.get_by_policy_id("pol-001") is not None
        assert repo.get_by_policy_id("nope") is None


class TestInsuranceAccountRepositoryUpsert:
    """Tests for upsert create/update semantics."""

    def test_upsert_creates_record(self, db_session):
        """First upsert inserts a new account row."""
        repo = InsuranceAccountRepository(db_session)

        account = repo.upsert(**_pension_fields())

        assert account.id is not None
        assert account.balance == 150000.0
        assert len(repo.get_all()) == 1

    def test_upsert_without_policy_id_raises_value_error(self, db_session):
        """upsert requires policy_id to key the record."""
        repo = InsuranceAccountRepository(db_session)
        with pytest.raises(ValueError, match="policy_id is required"):
            repo.upsert(provider="hafenix", policy_type="pension")

    def test_upsert_updates_existing_by_policy_id(self, db_session):
        """Re-upserting a known policy updates fields without duplicating."""
        repo = InsuranceAccountRepository(db_session)
        created = repo.upsert(**_pension_fields())

        updated = repo.upsert(
            **_pension_fields(balance=160000.0, balance_date="2026-07-31")
        )

        assert updated.id == created.id
        assert updated.balance == 160000.0
        assert updated.balance_date == "2026-07-31"
        assert len(repo.get_all()) == 1

    def test_upsert_preserves_custom_name_when_not_provided(self, db_session):
        """A scrape upsert (no custom_name key) keeps the user's rename."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(**_pension_fields())
        repo.set_custom_name("pol-001", "My Pension")

        repo.upsert(**_pension_fields(balance=170000.0))

        account = repo.get_by_policy_id("pol-001")
        assert account.custom_name == "My Pension"
        assert account.balance == 170000.0


class TestSetCustomName:
    """Tests for the custom display-name override."""

    def test_set_custom_name_sets_value(self, db_session):
        """set_custom_name writes the override and returns the record."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(**_pension_fields())

        account = repo.set_custom_name("pol-001", "My Pension")

        assert account.custom_name == "My Pension"
        assert db_session.get(InsuranceAccount, account.id).custom_name == "My Pension"

    def test_set_custom_name_empty_string_clears_override(self, db_session):
        """An empty string clears the override back to None."""
        repo = InsuranceAccountRepository(db_session)
        repo.upsert(**_pension_fields())
        repo.set_custom_name("pol-001", "My Pension")

        account = repo.set_custom_name("pol-001", "")

        assert account.custom_name is None

    def test_set_custom_name_unknown_policy_returns_none(self, db_session):
        """Renaming an unknown policy returns None rather than raising."""
        repo = InsuranceAccountRepository(db_session)
        assert repo.set_custom_name("nope", "Name") is None
