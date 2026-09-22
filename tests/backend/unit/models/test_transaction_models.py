"""
Unit tests for transaction ORM models and TimestampMixin.

Covers BankTransaction, CreditCardTransaction, CashTransaction,
ManualInvestmentTransaction, and SplitTransaction.

The ``source`` column holds the **table** name (``bank_transactions``), not
the service alias (``banks``) — that is what the ingestion path writes and
what the split read-side joins on, so the fixtures here use the ``Tables``
enum rather than a hand-written string.
"""

from datetime import datetime

import pytest
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

    def test_timestamps_auto_populated(self, db_session: Session):
        """created_at and updated_at are both set to datetimes on insert."""
        txn = BankTransaction(
            id="test-1",
            date="2026-01-01",
            provider="hapoalim",
            account_name="main",
            description="Test transaction",
            amount=-100.0,
            source=Tables.BANK.value,
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert isinstance(txn.created_at, datetime)
        assert isinstance(txn.updated_at, datetime)


class TestBankTransaction:
    """Tests for BankTransaction model."""

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
            source=Tables.BANK.value,
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
            source=Tables.BANK.value,
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
            source=Tables.BANK.value,
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.type == "normal"
        assert txn.status == "completed"


class TestOtherTransactionTables:
    """The non-bank transaction tables persist rows and assign a unique_id."""

    @pytest.mark.parametrize(
        ("model", "table"),
        [
            pytest.param(CreditCardTransaction, Tables.CREDIT_CARD, id="credit_card"),
            pytest.param(CashTransaction, Tables.CASH, id="cash"),
            pytest.param(
                ManualInvestmentTransaction,
                Tables.MANUAL_INVESTMENT_TRANSACTIONS,
                id="manual_investment",
            ),
        ],
    )
    def test_model_instantiation(self, db_session: Session, model, table):
        """A fully-populated row round-trips and gets an auto-increment unique_id."""
        txn = model(
            id="txn-001",
            date="2026-01-10",
            provider="isracard",
            account_name="personal",
            description="Online shopping",
            amount=-299.99,
            category="Shopping",
            source=table.value,
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        assert txn.unique_id is not None
        assert txn.id == "txn-001"
        assert txn.amount == -299.99
        assert txn.category == "Shopping"


class TestSplitTransaction:
    """Tests for SplitTransaction model."""

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        split = SplitTransaction(
            transaction_id=1,
            source=Tables.BANK.value,
            amount=-50.0,
            category="Food",
            tag="Groceries",
        )
        db_session.add(split)
        db_session.commit()
        db_session.refresh(split)

        assert split.id is not None
        assert split.transaction_id == 1
        assert split.source == Tables.BANK.value
        assert split.amount == -50.0

    def test_nullable_fields(self, db_session: Session):
        """Test nullable category and tag fields."""
        split = SplitTransaction(
            transaction_id=2,
            source=Tables.CREDIT_CARD.value,
            amount=-25.0,
        )
        db_session.add(split)
        db_session.commit()
        db_session.refresh(split)

        assert split.category is None
        assert split.tag is None
