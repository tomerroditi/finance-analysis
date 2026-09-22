"""
Unit tests for Investment ORM model.
"""

from sqlalchemy.orm import Session

from backend.models.investment import Investment


class TestInvestment:
    """Tests for Investment model."""

    def test_default_values(self, db_session: Session):
        """Optional fields take their defaults: open, fixed-rate, and null details."""
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
        assert inv.interest_rate is None
        assert inv.commission_deposit is None
        assert inv.liquidity_date is None
