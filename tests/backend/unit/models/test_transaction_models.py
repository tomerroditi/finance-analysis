"""
Unit tests for transaction ORM models and TimestampMixin.

Covers BankTransaction, CreditCardTransaction, CashTransaction,
ManualInvestmentTransaction, and SplitTransaction.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
)


class TestTimestampMixin:
    """Tests for TimestampMixin timestamp functionality."""

    def test_created_at_auto_populated(self, db_session: Session):
        """Test that created_at is auto-populated on insert."""
        txn = BankTransaction(
            id="test-1",
            date="2026-01-01",
            provider="hapoalim",
            account_name="main",
            description="Test transaction",
            amount=-100.0,
            source="banks",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.created_at is not None
        assert isinstance(txn.created_at, datetime)

    def test_updated_at_auto_populated(self, db_session: Session):
        """Test that updated_at is auto-populated on insert."""
        txn = BankTransaction(
            id="test-2",
            date="2026-01-01",
            provider="hapoalim",
            account_name="main",
            description="Test transaction",
            amount=-50.0,
            source="banks",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.updated_at is not None
        assert isinstance(txn.updated_at, datetime)


class TestBankTransaction:
    """Tests for BankTransaction model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert BankTransaction.__tablename__ == Tables.BANK.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        txn = BankTransaction(
            id="bank-001",
            date="2026-01-15",
            provider="hapoalim",
            account_name="main account",
            account_number="123456",
            description="Grocery store purchase",
            amount=-150.50,
            category="Food",
            tag="Groceries",
            source="banks",
            type="normal",
            status="completed",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.unique_id is not None
        assert txn.id == "bank-001"
        assert txn.amount == -150.50
        assert txn.category == "Food"
        assert txn.tag == "Groceries"

    def test_nullable_fields(self, db_session: Session):
        """Test nullable fields can be None."""
        txn = BankTransaction(
            id="bank-002",
            date="2026-01-15",
            provider="leumi",
            account_name="investments",
            description="Transfer",
            amount=500.0,
            source="banks",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.account_number is None
        assert txn.category is None
        assert txn.tag is None

    def test_default_type(self, db_session: Session):
        """Test default value for type field."""
        txn = BankTransaction(
            id="bank-003",
            date="2026-01-15",
            provider="discount",
            account_name="main",
            description="Payment",
            amount=-25.0,
            source="banks",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.type == "normal"
        assert txn.status == "completed"


class TestCreditCardTransaction:
    """Tests for CreditCardTransaction model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert CreditCardTransaction.__tablename__ == Tables.CREDIT_CARD.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        txn = CreditCardTransaction(
            id="cc-001",
            date="2026-01-10",
            provider="isracard",
            account_name="personal",
            description="Online shopping",
            amount=-299.99,
            category="Shopping",
            source="credit_cards",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.unique_id is not None
        assert txn.id == "cc-001"
        assert txn.provider == "isracard"

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        txn = CreditCardTransaction(
            id="cc-002",
            date="2026-01-10",
            provider="max",
            account_name="business",
            description="Office supplies",
            amount=-89.00,
            source="credit_cards",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert hasattr(txn, "created_at")
        assert hasattr(txn, "updated_at")
        assert txn.created_at is not None


class TestCashTransaction:
    """Tests for CashTransaction model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert CashTransaction.__tablename__ == Tables.CASH.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        txn = CashTransaction(
            id="cash-001",
            date="2026-01-12",
            provider="manual",
            account_name="wallet",
            description="Coffee shop",
            amount=-15.0,
            source="cash",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.unique_id is not None
        assert txn.amount == -15.0


class TestManualInvestmentTransaction:
    """Tests for ManualInvestmentTransaction model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert (
            ManualInvestmentTransaction.__tablename__
            == Tables.MANUAL_INVESTMENT_TRANSACTIONS.value
        )

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        txn = ManualInvestmentTransaction(
            id="inv-txn-001",
            date="2026-01-05",
            provider="manual",
            account_name="brokerage",
            description="Stock purchase",
            amount=-1000.0,
            category="Investments",
            tag="Stocks",
            source="manual_investments",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.unique_id is not None
        assert txn.category == "Investments"


class TestSplitTransaction:
    """Tests for SplitTransaction model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert SplitTransaction.__tablename__ == Tables.SPLIT_TRANSACTIONS.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        split = SplitTransaction(
            transaction_id=1,
            source="banks",
            amount=-50.0,
            category="Food",
            tag="Groceries",
        )
        db_session.add(split)
        db_session.commit()
        db_session.refresh(split)

        assert split.id is not None
        assert split.transaction_id == 1
        assert split.source == "banks"
        assert split.amount == -50.0

    def test_nullable_fields(self, db_session: Session):
        """Test nullable category and tag fields."""
        split = SplitTransaction(
            transaction_id=2,
            source="credit_cards",
            amount=-25.0,
        )
        db_session.add(split)
        db_session.commit()
        db_session.refresh(split)

        assert split.category is None
        assert split.tag is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        split = SplitTransaction(
            transaction_id=3,
            source="banks",
            amount=-100.0,
        )
        db_session.add(split)
        db_session.commit()
        db_session.refresh(split)

        assert hasattr(split, "created_at")
        assert split.created_at is not None
