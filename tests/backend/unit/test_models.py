"""
Unit tests for backend SQLAlchemy ORM models.

Tests cover model instantiation, table names, column types, nullable constraints,
default values, and mixin inheritance.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import (
    BankTransaction,
    BudgetRule,
    CashTransaction,
    CreditCardTransaction,
    Investment,
    ManualInvestmentTransaction,
    ScrapingHistory,
    SplitTransaction,
    TaggingRule,
)
from backend.naming_conventions import Tables


class TestTimestampMixin:
    """Tests for TimestampMixin timestamp functionality."""

    def test_created_at_auto_populated(self, db_session: Session):
        """Test that created_at is auto-populated on insert."""
        txn = BankTransaction(
            id="test-1",
            date="2026-01-01",
            provider="hapoalim",
            account_name="main",
            desc="Test transaction",
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
            desc="Test transaction",
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
            desc="Grocery store purchase",
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
            desc="Transfer",
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
            desc="Payment",
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
            desc="Online shopping",
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
            desc="Office supplies",
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
            desc="Coffee shop",
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
            desc="Stock purchase",
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


class TestBudgetRule:
    """Tests for BudgetRule model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert BudgetRule.__tablename__ == Tables.BUDGET_RULES.value

    def test_monthly_budget_rule(self, db_session: Session):
        """Test creating a monthly budget rule."""
        rule = BudgetRule(
            name="Total Budget",
            amount=5000.0,
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.name == "Total Budget"
        assert rule.amount == 5000.0
        assert rule.year == 2026
        assert rule.month == 1

    def test_category_budget_rule(self, db_session: Session):
        """Test creating a category budget rule."""
        rule = BudgetRule(
            name="Monthly Food",
            amount=1500.0,
            category="Food",
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.category == "Food"
        assert rule.tags is None

    def test_tag_budget_rule(self, db_session: Session):
        """Test creating a budget rule with tags."""
        rule = BudgetRule(
            name="Restaurant Budget",
            amount=500.0,
            category="Food",
            tags="Restaurants",
            year=2026,
            month=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.tags == "Restaurants"

    def test_project_budget_rule(self, db_session: Session):
        """Test creating a project budget (no year/month)."""
        rule = BudgetRule(
            name="Home Renovation",
            amount=50000.0,
            category="Home",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.year is None
        assert rule.month is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        rule = BudgetRule(name="Test", amount=100.0)
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert hasattr(rule, "created_at")
        assert rule.created_at is not None


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


class TestTaggingRule:
    """Tests for TaggingRule model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert TaggingRule.__tablename__ == Tables.TAGGING_RULES.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        rule = TaggingRule(
            name="Grocery Stores",
            priority=10,
            conditions='[{"field": "desc", "operator": "contains", "value": "supermarket"}]',
            category="Food",
            tag="Groceries",
            is_active=1,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.id is not None
        assert rule.name == "Grocery Stores"
        assert rule.priority == 10
        assert rule.is_active == 1

    def test_default_values(self, db_session: Session):
        """Test default values for priority and is_active."""
        rule = TaggingRule(
            name="Default Rule",
            conditions='[{"field": "desc", "operator": "equals", "value": "test"}]',
            category="Other",
            tag="Misc",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.priority == 1
        assert rule.is_active == 1

    def test_inactive_rule(self, db_session: Session):
        """Test creating an inactive rule."""
        rule = TaggingRule(
            name="Inactive Rule",
            conditions="[]",
            category="Test",
            tag="Inactive",
            is_active=0,
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert rule.is_active == 0

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        rule = TaggingRule(
            name="Timestamp Test",
            conditions="[]",
            category="Test",
            tag="Test",
        )
        db_session.add(rule)
        db_session.commit()
        db_session.refresh(rule)

        assert hasattr(rule, "created_at")
        assert rule.created_at is not None


class TestScrapingHistory:
    """Tests for ScrapingHistory model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert ScrapingHistory.__tablename__ == Tables.SCRAPING_HISTORY.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated with all fields."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="hapoalim",
            account_name="main",
            date="2026-01-16T10:30:00",
            status="success",
            start_date="2025-12-01",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.id is not None
        assert history.service_name == "banks"
        assert history.provider_name == "hapoalim"
        assert history.status == "success"

    def test_failed_scraping(self, db_session: Session):
        """Test recording a failed scraping attempt."""
        history = ScrapingHistory(
            service_name="credit_cards",
            provider_name="isracard",
            account_name="personal",
            date="2026-01-16T11:00:00",
            status="failed",
            start_date="2026-01-01",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.status == "failed"

    def test_nullable_start_date(self, db_session: Session):
        """Test that start_date is nullable."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="leumi",
            account_name="investments",
            date="2026-01-16T12:00:00",
            status="success",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert history.start_date is None

    def test_inherits_timestamp_mixin(self, db_session: Session):
        """Test model has TimestampMixin fields."""
        history = ScrapingHistory(
            service_name="banks",
            provider_name="discount",
            account_name="main",
            date="2026-01-16T13:00:00",
            status="success",
        )
        db_session.add(history)
        db_session.commit()
        db_session.refresh(history)

        assert hasattr(history, "created_at")
        assert history.created_at is not None
