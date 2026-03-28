"""
Unit tests for the Liability and LiabilityTransaction models.
"""

from sqlalchemy.orm import Session

from backend.models.liability import Liability, LiabilityTransaction


class TestLiabilityModel:
    """Tests for Liability ORM model."""

    def test_create_liability(self, db_session: Session):
        """Verify creating a liability record with all fields."""
        liability = Liability(
            name="Car Loan",
            lender="Bank Leumi",
            category="Liabilities",
            tag="Car Loan",
            principal_amount=50000.0,
            interest_rate=4.5,
            term_months=48,
            start_date="2024-01-15",
            created_date="2024-01-15",
        )
        db_session.add(liability)
        db_session.commit()

        result = db_session.query(Liability).first()
        assert result.name == "Car Loan"
        assert result.lender == "Bank Leumi"
        assert result.principal_amount == 50000.0
        assert result.interest_rate == 4.5
        assert result.term_months == 48
        assert result.is_paid_off == 0

    def test_create_liability_minimal_fields(self, db_session: Session):
        """Verify creating a liability with only required fields."""
        liability = Liability(
            name="Personal Loan",
            category="Liabilities",
            tag="Personal",
            principal_amount=10000.0,
            interest_rate=5.0,
            term_months=24,
            start_date="2024-06-01",
            created_date="2024-06-01",
        )
        db_session.add(liability)
        db_session.commit()

        result = db_session.query(Liability).first()
        assert result.lender is None
        assert result.notes is None
        assert result.paid_off_date is None


class TestLiabilityTransactionModel:
    """Tests for LiabilityTransaction ORM model."""

    def test_create_liability_transaction(self, db_session: Session):
        """Verify creating a liability transaction linked to a liability."""
        liability = Liability(
            name="Test Loan",
            category="Liabilities",
            tag="Test",
            principal_amount=10000.0,
            interest_rate=5.0,
            term_months=12,
            start_date="2024-01-01",
            created_date="2024-01-01",
        )
        db_session.add(liability)
        db_session.flush()

        txn = LiabilityTransaction(
            liability_id=liability.id,
            date="2024-02-01",
            amount=-850.0,
            payment_number=1,
            description="Test Loan - Payment #1",
        )
        db_session.add(txn)
        db_session.commit()

        result = db_session.query(LiabilityTransaction).first()
        assert result.liability_id == liability.id
        assert result.date == "2024-02-01"
        assert result.amount == -850.0
        assert result.payment_number == 1
        assert result.description == "Test Loan - Payment #1"

    def test_nullable_description(self, db_session: Session):
        """Verify description field is optional."""
        liability = Liability(
            name="Nullable Test",
            category="Liabilities",
            tag="Nullable",
            principal_amount=5000.0,
            interest_rate=3.0,
            term_months=6,
            start_date="2024-01-01",
            created_date="2024-01-01",
        )
        db_session.add(liability)
        db_session.flush()

        txn = LiabilityTransaction(
            liability_id=liability.id,
            date="2024-02-01",
            amount=-850.0,
            payment_number=1,
        )
        db_session.add(txn)
        db_session.commit()

        result = db_session.query(LiabilityTransaction).first()
        assert result.description is None
