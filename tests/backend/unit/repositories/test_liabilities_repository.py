"""
Unit tests for LiabilitiesRepository CRUD operations.
"""

import pytest
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.repositories.liabilities_repository import LiabilitiesRepository


class TestLiabilitiesRepository:
    """Tests for LiabilitiesRepository operations."""

    def test_create_liability(self, db_session: Session):
        """Verify creating a liability with all fields stores them correctly."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Car Loan",
            tag="Car Loan",
            principal_amount=50000.0,
            interest_rate=4.5,
            term_months=48,
            start_date="2023-06-01",
            lender="Bank Leumi",
            notes="Monthly debit from Leumi checking",
        )

        result = repo.get_all_liabilities(include_paid_off=True)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Car Loan"
        assert row["tag"] == "Car Loan"
        assert row["category"] == "Liabilities"
        assert row["principal_amount"] == 50000.0
        assert row["interest_rate"] == 4.5
        assert row["term_months"] == 48
        assert row["start_date"] == "2023-06-01"
        assert row["lender"] == "Bank Leumi"
        assert row["notes"] == "Monthly debit from Leumi checking"
        assert row["is_paid_off"] == 0

    def test_get_all_excludes_paid_off(self, db_session: Session):
        """Verify get_all_liabilities excludes paid-off liabilities by default."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Active Loan", tag="Active", principal_amount=10000.0,
            interest_rate=3.0, term_months=24, start_date="2024-01-01",
        )
        repo.create_liability(
            name="Paid Loan", tag="Paid", principal_amount=5000.0,
            interest_rate=2.5, term_months=12, start_date="2023-01-01",
        )

        all_liabilities = repo.get_all_liabilities(include_paid_off=True)
        paid_id = int(all_liabilities[all_liabilities["name"] == "Paid Loan"].iloc[0]["id"])
        repo.mark_paid_off(paid_id, "2024-01-01")

        result = repo.get_all_liabilities(include_paid_off=False)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Active Loan"

    def test_get_by_id(self, db_session: Session):
        """Verify retrieving a liability by its ID."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Mortgage", tag="Mortgage", principal_amount=800000.0,
            interest_rate=3.5, term_months=240, start_date="2020-01-01",
        )

        all_liabilities = repo.get_all_liabilities(include_paid_off=True)
        liability_id = int(all_liabilities.iloc[0]["id"])

        result = repo.get_by_id(liability_id)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Mortgage"

    def test_get_by_id_not_found(self, db_session: Session):
        """Verify EntityNotFoundException is raised for a non-existent ID."""
        repo = LiabilitiesRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.get_by_id(999)

    def test_update_liability(self, db_session: Session):
        """Verify updating liability fields persists the changes."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Old Name", tag="Loan", principal_amount=15000.0,
            interest_rate=5.0, term_months=36, start_date="2023-03-01",
        )

        all_liabilities = repo.get_all_liabilities(include_paid_off=True)
        liability_id = int(all_liabilities.iloc[0]["id"])

        repo.update_liability(liability_id, name="New Name", notes="Updated notes")

        updated = repo.get_by_id(liability_id)
        assert updated.iloc[0]["name"] == "New Name"
        assert updated.iloc[0]["notes"] == "Updated notes"

    def test_mark_paid_off_and_reopen(self, db_session: Session):
        """Verify full lifecycle: create → mark paid off → reopen."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Student Loan", tag="Student Loan", principal_amount=20000.0,
            interest_rate=3.8, term_months=36, start_date="2022-01-01",
        )

        all_liabilities = repo.get_all_liabilities(include_paid_off=True)
        liability_id = int(all_liabilities.iloc[0]["id"])

        # Mark paid off
        repo.mark_paid_off(liability_id, "2025-01-01")
        paid = repo.get_by_id(liability_id)
        assert paid.iloc[0]["is_paid_off"] == 1
        assert paid.iloc[0]["paid_off_date"] == "2025-01-01"

        # Verify excluded from default query
        active = repo.get_all_liabilities(include_paid_off=False)
        assert active.empty

        # Reopen
        repo.reopen(liability_id)
        reopened = repo.get_by_id(liability_id)
        assert reopened.iloc[0]["is_paid_off"] == 0
        assert reopened.iloc[0]["paid_off_date"] is None

    def test_delete_liability(self, db_session: Session):
        """Verify deleting a liability removes it and raises on subsequent get."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Delete Me", tag="Temp Loan", principal_amount=1000.0,
            interest_rate=1.0, term_months=6, start_date="2024-01-01",
        )

        all_liabilities = repo.get_all_liabilities(include_paid_off=True)
        liability_id = int(all_liabilities.iloc[0]["id"])

        repo.delete_liability(liability_id)

        with pytest.raises(EntityNotFoundException):
            repo.get_by_id(liability_id)

    def test_delete_not_found(self, db_session: Session):
        """Verify EntityNotFoundException is raised when deleting a non-existent liability."""
        repo = LiabilitiesRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.delete_liability(999)
