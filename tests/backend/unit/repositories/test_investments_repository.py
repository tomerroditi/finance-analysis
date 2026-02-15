"""
Unit tests for InvestmentsRepository CRUD operations.
"""

import pytest
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.repositories.investments_repository import InvestmentsRepository


class TestInvestmentsRepository:
    """Tests for InvestmentsRepository operations."""

    def test_create_investment(self, db_session: Session):
        """Verify creating an investment with all fields."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments",
            tag="Stock Fund",
            type_="stocks",
            name="S&P 500 Index",
            interest_rate=7.5,
            interest_rate_type="variable",
            commission_deposit=0.1,
            commission_management=0.5,
            commission_withdrawal=0.2,
            liquidity_date="2025-01-01",
            maturity_date="2030-12-31",
            notes="Long term investment",
        )

        result = repo.get_all_investments(include_closed=True)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["category"] == "Investments"
        assert row["tag"] == "Stock Fund"
        assert row["name"] == "S&P 500 Index"
        assert row["interest_rate"] == 7.5
        assert row["notes"] == "Long term investment"

    def test_get_all_investments_excludes_closed(self, db_session: Session):
        """Verify get_all_investments excludes closed by default."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Open Fund", type_="stocks", name="Open"
        )
        repo.create_investment(
            category="Investments", tag="Closed Fund", type_="bonds", name="Closed"
        )

        # Close the second one
        all_inv = repo.get_all_investments(include_closed=True)
        closed_id = int(all_inv[all_inv["name"] == "Closed"].iloc[0]["id"])
        repo.close_investment(closed_id, "2024-06-01")

        result = repo.get_all_investments(include_closed=False)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Open"

    def test_get_all_investments_includes_closed(self, db_session: Session):
        """Verify include_closed=True returns closed investments."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Open Fund", type_="stocks", name="Open"
        )
        repo.create_investment(
            category="Investments", tag="Closed Fund", type_="bonds", name="Closed"
        )

        all_inv = repo.get_all_investments(include_closed=True)
        closed_id = int(all_inv[all_inv["name"] == "Closed"].iloc[0]["id"])
        repo.close_investment(closed_id, "2024-06-01")

        result = repo.get_all_investments(include_closed=True)
        assert len(result) == 2

    def test_get_by_id(self, db_session: Session):
        """Verify retrieving investment by ID."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Stock Fund", type_="stocks", name="Test Fund"
        )

        all_inv = repo.get_all_investments(include_closed=True)
        inv_id = int(all_inv.iloc[0]["id"])

        result = repo.get_by_id(inv_id)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Test Fund"

    def test_get_by_id_not_found(self, db_session: Session):
        """Verify EntityNotFoundException for non-existent ID."""
        repo = InvestmentsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.get_by_id(999)

    def test_get_by_category_tag(self, db_session: Session):
        """Verify filtering by category and tag."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Stock Fund", type_="stocks", name="Fund A"
        )
        repo.create_investment(
            category="Investments", tag="Bond Fund", type_="bonds", name="Fund B"
        )

        result = repo.get_by_category_tag("Investments", "Stock Fund")
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Fund A"

    def test_update_investment(self, db_session: Session):
        """Verify updating investment fields."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Stock Fund", type_="stocks", name="Old Name"
        )

        all_inv = repo.get_all_investments(include_closed=True)
        inv_id = int(all_inv.iloc[0]["id"])

        repo.update_investment(inv_id, name="New Name", notes="Updated")

        updated = repo.get_by_id(inv_id)
        assert updated.iloc[0]["name"] == "New Name"
        assert updated.iloc[0]["notes"] == "Updated"

    def test_update_investment_not_found(self, db_session: Session):
        """Verify EntityNotFoundException for updating non-existent investment."""
        repo = InvestmentsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.update_investment(999, name="Nope")

    def test_close_and_reopen_investment(self, db_session: Session):
        """Verify closing sets is_closed and closed_date, reopening clears them."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Stock Fund", type_="stocks", name="Test"
        )

        all_inv = repo.get_all_investments(include_closed=True)
        inv_id = int(all_inv.iloc[0]["id"])

        # Close
        repo.close_investment(inv_id, "2024-06-15")
        closed = repo.get_by_id(inv_id)
        assert closed.iloc[0]["is_closed"] == 1
        assert closed.iloc[0]["closed_date"] == "2024-06-15"

        # Reopen
        repo.reopen_investment(inv_id)
        reopened = repo.get_by_id(inv_id)
        assert reopened.iloc[0]["is_closed"] == 0
        assert reopened.iloc[0]["closed_date"] is None

    def test_delete_investment(self, db_session: Session):
        """Verify deleting removes the investment."""
        repo = InvestmentsRepository(db_session)
        repo.create_investment(
            category="Investments", tag="Stock Fund", type_="stocks", name="Delete Me"
        )

        all_inv = repo.get_all_investments(include_closed=True)
        inv_id = int(all_inv.iloc[0]["id"])

        repo.delete_investment(inv_id)

        result = repo.get_all_investments(include_closed=True)
        assert result.empty

    def test_delete_investment_not_found(self, db_session: Session):
        """Verify EntityNotFoundException for deleting non-existent investment."""
        repo = InvestmentsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.delete_investment(999)
