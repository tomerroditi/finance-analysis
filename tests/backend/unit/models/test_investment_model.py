"""
Unit tests for Investment ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.investment import Investment


class TestInvestment:
    """Tests for Investment model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert Investment.__tablename__ == Tables.INVESTMENTS.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        inv = Investment(
            category="Investments",
            tag="Bonds",
            type="bonds",
            name="Government Bond 2030",
            interest_rate=4.5,
            interest_rate_type="fixed",
            commission_deposit=0.5,
            commission_management=0.1,
            commission_withdrawal=0.0,
            liquidity_date="2025-01-01",
            maturity_date="2030-12-31",
            is_closed=0,
            created_date="2024-01-01",
            notes="5-year government bond",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        assert inv.id is not None
        assert inv.interest_rate == 4.5
        assert inv.maturity_date == "2030-12-31"

    def test_default_values(self, db_session: Session):
        """Test default values for optional fields."""
        inv = Investment(
            category="Investments",
            tag="Stocks",
            type="stocks",
            name="Tech ETF",
            created_date="2026-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        assert inv.is_closed == 0
        assert inv.interest_rate_type == "fixed"
        assert inv.closed_date is None
        assert inv.notes is None

    def test_nullable_financial_fields(self, db_session: Session):
        """Test nullable financial detail fields."""
        inv = Investment(
            category="Investments",
            tag="Emergency Fund",
            type="pakam",
            name="High Yield Savings",
            created_date="2026-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        assert inv.interest_rate is None
        assert inv.commission_deposit is None
        assert inv.liquidity_date is None

    def test_closed_investment(self, db_session: Session):
        """Test marking an investment as closed."""
        inv = Investment(
            category="Investments",
            tag="Bonds",
            type="bonds",
            name="Closed Bond",
            created_date="2020-01-01",
            is_closed=1,
            closed_date="2025-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        assert inv.is_closed == 1
        assert inv.closed_date == "2025-01-01"
