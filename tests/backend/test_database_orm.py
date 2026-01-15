import pytest
import time
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.base import Base
from backend.models.transaction import CashTransaction
from backend.models.budget import BudgetRule
from backend.models.tagging import TaggingRule
from backend.models.investment import Investment
from backend.models.scraping import ScrapingHistory

from backend.repositories.transactions_repository import CashTransactionDTO, CashRepository, TransactionsRepository
from backend.repositories.budget_repository import BudgetRepository
from backend.repositories.tagging_rules_repository import TaggingRulesRepository
from backend.repositories.investments_repository import InvestmentsRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.naming_conventions import Tables, Services

# Setup in-memory SQLite DB for testing
@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_timestamp_mixin(db_session):
    """Test that timestamps are automatically handled."""
    # Create a generic model instance (using BudgetRule as example)
    rule = BudgetRule(name="Test Rule", amount=100.0)
    db_session.add(rule)
    db_session.commit()
    
    assert rule.created_at is not None
    assert rule.updated_at is not None
    assert rule.created_at == rule.updated_at
    
    # Update
    original_updated_at = rule.updated_at
    time.sleep(1.1) 
    rule.amount = 200.0
    db_session.commit()
    
    assert rule.updated_at > original_updated_at

def test_transactions_repository(db_session):
    repo = TransactionsRepository(db_session)
    
    # Test adding transaction
    tx_dto = CashTransactionDTO(
        date=datetime.now(),
        account_name="Wallet",
        desc="Lunch",
        amount=-50.0,
        category="Food",
        tag="Lunch"
    )
    
    # Add via aggregated repo (to specific service)
    repo.add_transaction(tx_dto, Services.CASH.value)
    
    # Verify
    df = repo.get_table(service=Services.CASH.value)
    assert len(df) == 1
    assert df.iloc[0]['amount'] == -50.0
    assert df.iloc[0]['desc'] == "Lunch"
    
    # Verify ID generation
    assert df.iloc[0]['id'] == '1'

def test_budget_repository(db_session):
    repo = BudgetRepository(db_session)
    
    repo.add("Rent", 2000.0, "Housing", "Rent", 1, 2024)
    
    df = repo.read_all()
    assert len(df) == 1
    assert df.iloc[0]['name'] == "Rent"

def test_tagging_repository(db_session):
    repo = TaggingRulesRepository(db_session)
    
    rule_id = repo.add_rule(
        name="Coffee Rule",
        conditions=[{"field": "desc", "operator": "contains", "value": "Starbucks"}],
        category="Food",
        tag="Coffee"
    )
    
    assert rule_id is not None
    
    rule = repo.get_rule_by_id(rule_id)
    assert rule['name'] == "Coffee Rule"
    assert rule['category'] == "Food"

def test_investments_repository(db_session):
    repo = InvestmentsRepository(db_session)
    
    repo.create_investment(
        category="Savings",
        tag="Emergency Fund",
        type_="cash",
        name="My Bank",
        interest_rate=2.5
    )
    
    df = repo.get_all_investments()
    assert len(df) == 1
    assert df.iloc[0]['name'] == "My Bank"
    assert df.iloc[0]['interest_rate'] == 2.5

def test_scraping_history_repository(db_session):
    repo = ScrapingHistoryRepository(db_session)
    
    scrape_id = repo.record_scrape_start(
        service_name="bank",
        provider_name="hapoalim",
        account_name="main",
        start_date=datetime.now().date()
    )
    
    status = repo.get_scraping_status(scrape_id)
    assert status == repo.IN_PROGRESS
    
    repo.record_scrape_end(scrape_id, repo.SUCCESS)
    status_end = repo.get_scraping_status(scrape_id)
    assert status_end == repo.SUCCESS
