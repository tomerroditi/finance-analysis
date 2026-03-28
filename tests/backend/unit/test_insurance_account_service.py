"""
Unit tests for InsuranceAccountService and InsuranceAccountRepository.

Tests balance aggregation, CRUD operations, and upsert logic
for insurance account metadata.
"""

import pytest

from backend.models.insurance_account import InsuranceAccount
from backend.repositories.insurance_account_repository import (
    InsuranceAccountRepository,
)
from backend.services.insurance_account_service import InsuranceAccountService


@pytest.fixture
def insurance_repo(db_session):
    """Create an InsuranceAccountRepository with the test DB session."""
    return InsuranceAccountRepository(db_session)


@pytest.fixture
def insurance_service(db_session):
    """Create an InsuranceAccountService with the test DB session."""
    return InsuranceAccountService(db_session)


@pytest.fixture
def seed_insurance_accounts(db_session):
    """Seed two hishtalmut accounts and one pension account."""
    accounts = [
        InsuranceAccount(
            provider="hafenix",
            policy_id="KH-001",
            policy_type="hishtalmut",
            account_name="Keren Hishtalmut A",
            balance=150000.0,
            balance_date="2026-01-15",
        ),
        InsuranceAccount(
            provider="hafenix",
            policy_id="KH-002",
            policy_type="hishtalmut",
            account_name="Keren Hishtalmut B",
            balance=80000.0,
            balance_date="2026-01-15",
        ),
        InsuranceAccount(
            provider="hafenix",
            policy_id="PN-001",
            policy_type="pension",
            pension_type="makifa",
            account_name="Pension Makifa",
            balance=500000.0,
            balance_date="2026-01-15",
        ),
    ]
    for a in accounts:
        db_session.add(a)
    db_session.commit()
    return accounts


class TestInsuranceAccountRepository:
    """Tests for InsuranceAccountRepository CRUD operations."""

    def test_get_all_empty(self, insurance_repo):
        """Returns empty list when no accounts exist."""
        assert insurance_repo.get_all() == []

    def test_get_all_returns_all(self, insurance_repo, seed_insurance_accounts):
        """Returns all seeded insurance accounts."""
        result = insurance_repo.get_all()
        assert len(result) == 3

    def test_get_by_policy_type_hishtalmut(
        self, insurance_repo, seed_insurance_accounts
    ):
        """Filters to only hishtalmut accounts."""
        result = insurance_repo.get_by_policy_type("hishtalmut")
        assert len(result) == 2
        assert all(a.policy_type == "hishtalmut" for a in result)

    def test_get_by_policy_type_pension(
        self, insurance_repo, seed_insurance_accounts
    ):
        """Filters to only pension accounts."""
        result = insurance_repo.get_by_policy_type("pension")
        assert len(result) == 1
        assert result[0].policy_type == "pension"

    def test_get_by_policy_type_nonexistent(self, insurance_repo):
        """Returns empty list for unknown policy type."""
        assert insurance_repo.get_by_policy_type("gemel") == []

    def test_get_by_policy_id_found(
        self, insurance_repo, seed_insurance_accounts
    ):
        """Returns matching account by policy ID."""
        result = insurance_repo.get_by_policy_id("KH-001")
        assert result is not None
        assert result.account_name == "Keren Hishtalmut A"

    def test_get_by_policy_id_not_found(self, insurance_repo):
        """Returns None when policy ID does not exist."""
        assert insurance_repo.get_by_policy_id("NONEXISTENT") is None

    def test_upsert_creates_new(self, insurance_repo):
        """Upsert creates a new account when policy_id is new."""
        result = insurance_repo.upsert(
            provider="hafenix",
            policy_id="NEW-001",
            policy_type="hishtalmut",
            account_name="New Account",
            balance=10000.0,
        )
        assert result.id is not None
        assert result.policy_id == "NEW-001"
        assert result.balance == 10000.0

    def test_upsert_updates_existing(
        self, insurance_repo, seed_insurance_accounts
    ):
        """Upsert updates balance when policy_id already exists."""
        result = insurance_repo.upsert(
            policy_id="KH-001",
            balance=200000.0,
        )
        assert result.balance == 200000.0
        assert result.account_name == "Keren Hishtalmut A"

    def test_upsert_missing_policy_id_raises(self, insurance_repo):
        """Upsert raises ValueError when policy_id is not provided."""
        with pytest.raises(ValueError, match="policy_id is required"):
            insurance_repo.upsert(
                provider="hafenix",
                policy_type="hishtalmut",
                account_name="No Policy ID",
            )


class TestInsuranceAccountService:
    """Tests for InsuranceAccountService business logic."""

    def test_get_all_empty(self, insurance_service):
        """Returns empty list when no accounts exist."""
        assert insurance_service.get_all() == []

    def test_get_all_returns_orm_objects(
        self, insurance_service, seed_insurance_accounts
    ):
        """Returns ORM objects for all accounts."""
        result = insurance_service.get_all()
        assert len(result) == 3
        assert all(isinstance(a, InsuranceAccount) for a in result)

    def test_get_keren_hishtalmut_balance_with_data(
        self, insurance_service, seed_insurance_accounts
    ):
        """Sums balances of all hishtalmut accounts."""
        balance = insurance_service.get_keren_hishtalmut_balance()
        assert balance == 230000.0  # 150000 + 80000

    def test_get_keren_hishtalmut_balance_no_data(self, insurance_service):
        """Returns None when no hishtalmut accounts exist."""
        assert insurance_service.get_keren_hishtalmut_balance() is None

    def test_get_keren_hishtalmut_balance_null_balances(
        self, insurance_service, db_session
    ):
        """Returns None when all hishtalmut balances are null."""
        db_session.add(
            InsuranceAccount(
                provider="hafenix",
                policy_id="KH-NULL",
                policy_type="hishtalmut",
                account_name="Null Balance",
                balance=None,
            )
        )
        db_session.commit()
        assert insurance_service.get_keren_hishtalmut_balance() is None

    def test_get_keren_hishtalmut_balance_zero_total(
        self, insurance_service, db_session
    ):
        """Returns None when total hishtalmut balance is zero."""
        db_session.add(
            InsuranceAccount(
                provider="hafenix",
                policy_id="KH-ZERO",
                policy_type="hishtalmut",
                account_name="Zero Balance",
                balance=0.0,
            )
        )
        db_session.commit()
        assert insurance_service.get_keren_hishtalmut_balance() is None

    def test_upsert_delegates_to_repo(self, insurance_service):
        """Upsert creates via repository and returns ORM object."""
        result = insurance_service.upsert(
            provider="hafenix",
            policy_id="SVC-001",
            policy_type="pension",
            account_name="Via Service",
            balance=100000.0,
        )
        assert result.policy_id == "SVC-001"
        assert isinstance(result, InsuranceAccount)

    def test_upsert_missing_policy_id_raises(self, insurance_service):
        """Upsert propagates ValueError when policy_id is missing."""
        with pytest.raises(ValueError, match="policy_id is required"):
            insurance_service.upsert(
                provider="hafenix",
                policy_type="hishtalmut",
                account_name="No Policy ID",
            )
