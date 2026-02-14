"""
Composable seed fixtures for backend tests.

Provides realistic ORM records inserted into the in-memory SQLite database.
Each fixture is function-scoped and independent -- tests pick only the
fixtures they need.
"""

import pytest
from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance
from backend.models.budget import BudgetRule
from backend.models.investment import Investment
from backend.models.tagging_rules import TaggingRule
from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
)


# ---------------------------------------------------------------------------
# 1. Base transactions (~30 records across 3 months)
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_base_transactions(db_session: Session) -> list:
    """Insert ~30 realistic transactions across Jan-Mar 2024.

    Includes credit-card, bank, and cash transactions with proper
    category/tag assignments and the negative-expense / positive-income
    convention.
    """
    records = [
        # ---- January 2024 - Credit Card ----
        CreditCardTransaction(
            id="cc_jan_1",
            date="2024-01-05",
            provider="isracard",
            account_name="Main Card",
            description="Shufersal Deal",
            amount=-150.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_jan_2",
            date="2024-01-10",
            provider="isracard",
            account_name="Main Card",
            description="Cafe Landwer",
            amount=-80.0,
            category="Food",
            tag="Restaurants",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_jan_3",
            date="2024-01-15",
            provider="max",
            account_name="Joint Card",
            description="Sonol Gas Station",
            amount=-60.0,
            category="Transport",
            tag="Gas",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_jan_4",
            date="2024-01-20",
            provider="max",
            account_name="Joint Card",
            description="Cinema City",
            amount=-40.0,
            category="Entertainment",
            tag="Cinema",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        # ---- January 2024 - Bank ----
        BankTransaction(
            id="bank_jan_1",
            date="2024-01-01",
            provider="hapoalim",
            account_name="Checking",
            description="Salary January",
            amount=8000.0,
            category="Salary",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_jan_2",
            date="2024-01-03",
            provider="hapoalim",
            account_name="Checking",
            description="Rent Payment",
            amount=-3000.0,
            category="Home",
            tag="Rent",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_jan_3",
            date="2024-01-12",
            provider="hapoalim",
            account_name="Checking",
            description="Internal Transfer Out",
            amount=-500.0,
            category="Ignore",
            tag="Transfer",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_jan_4",
            date="2024-01-12",
            provider="hapoalim",
            account_name="Savings",
            description="Internal Transfer In",
            amount=500.0,
            category="Ignore",
            tag="Transfer",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        # ---- January 2024 - Cash ----
        CashTransaction(
            id="cash_jan_1",
            date="2024-01-08",
            provider="cash",
            account_name="Cash Wallet",
            description="Morning Coffee",
            amount=-15.0,
            category="Food",
            tag="Coffee",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        CashTransaction(
            id="cash_jan_2",
            date="2024-01-18",
            provider="cash",
            account_name="Cash Wallet",
            description="Street Parking",
            amount=-10.0,
            category="Transport",
            tag="Parking",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        # ---- February 2024 - Credit Card ----
        CreditCardTransaction(
            id="cc_feb_1",
            date="2024-02-03",
            provider="isracard",
            account_name="Main Card",
            description="Rami Levy Supermarket",
            amount=-180.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_feb_2",
            date="2024-02-14",
            provider="isracard",
            account_name="Main Card",
            description="Iza Restaurant",
            amount=-120.0,
            category="Food",
            tag="Restaurants",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_feb_3",
            date="2024-02-18",
            provider="max",
            account_name="Joint Card",
            description="Delek Gas Station",
            amount=-55.0,
            category="Transport",
            tag="Gas",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_feb_4",
            date="2024-02-22",
            provider="max",
            account_name="Joint Card",
            description="Yes Planet Cinema",
            amount=-45.0,
            category="Entertainment",
            tag="Cinema",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        # ---- February 2024 - Bank ----
        BankTransaction(
            id="bank_feb_1",
            date="2024-02-01",
            provider="hapoalim",
            account_name="Checking",
            description="Salary February",
            amount=8500.0,
            category="Salary",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_feb_2",
            date="2024-02-03",
            provider="hapoalim",
            account_name="Checking",
            description="Rent Payment",
            amount=-3000.0,
            category="Home",
            tag="Rent",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        # ---- February 2024 - Cash ----
        CashTransaction(
            id="cash_feb_1",
            date="2024-02-10",
            provider="cash",
            account_name="Cash Wallet",
            description="Aroma Coffee",
            amount=-18.0,
            category="Food",
            tag="Coffee",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        CashTransaction(
            id="cash_feb_2",
            date="2024-02-20",
            provider="cash",
            account_name="Cash Wallet",
            description="Parking Lot",
            amount=-12.0,
            category="Transport",
            tag="Parking",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        # ---- March 2024 - Credit Card ----
        CreditCardTransaction(
            id="cc_mar_1",
            date="2024-03-02",
            provider="isracard",
            account_name="Main Card",
            description="Mega Supermarket",
            amount=-200.0,
            category="Food",
            tag="Groceries",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_mar_2",
            date="2024-03-11",
            provider="isracard",
            account_name="Main Card",
            description="Vitrina Restaurant",
            amount=-95.0,
            category="Food",
            tag="Restaurants",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_mar_3",
            date="2024-03-15",
            provider="max",
            account_name="Joint Card",
            description="Paz Gas Station",
            amount=-70.0,
            category="Transport",
            tag="Gas",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_mar_4",
            date="2024-03-25",
            provider="max",
            account_name="Joint Card",
            description="Hot Cinema",
            amount=-35.0,
            category="Entertainment",
            tag="Cinema",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        # ---- March 2024 - Bank ----
        BankTransaction(
            id="bank_mar_1",
            date="2024-03-01",
            provider="hapoalim",
            account_name="Checking",
            description="Salary March",
            amount=8200.0,
            category="Salary",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_mar_2",
            date="2024-03-03",
            provider="hapoalim",
            account_name="Checking",
            description="Rent Payment",
            amount=-3000.0,
            category="Home",
            tag="Rent",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_mar_3",
            date="2024-03-10",
            provider="hapoalim",
            account_name="Checking",
            description="Internal Transfer Out",
            amount=-700.0,
            category="Ignore",
            tag="Transfer",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_mar_4",
            date="2024-03-10",
            provider="hapoalim",
            account_name="Savings",
            description="Internal Transfer In",
            amount=700.0,
            category="Ignore",
            tag="Transfer",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        # ---- March 2024 - Cash ----
        CashTransaction(
            id="cash_mar_1",
            date="2024-03-07",
            provider="cash",
            account_name="Cash Wallet",
            description="Cofix Coffee",
            amount=-12.0,
            category="Food",
            tag="Coffee",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        CashTransaction(
            id="cash_mar_2",
            date="2024-03-22",
            provider="cash",
            account_name="Cash Wallet",
            description="Municipal Parking",
            amount=-8.0,
            category="Transport",
            tag="Parking",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
        # ---- Extra variety ----
        CreditCardTransaction(
            id="cc_jan_5",
            date="2024-01-25",
            provider="visa_cal",
            account_name="Business Card",
            description="Office Depot Supplies",
            amount=-250.0,
            category="Other",
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_feb_3",
            date="2024-02-15",
            provider="leumi",
            account_name="Business Account",
            description="Freelance Payment",
            amount=3500.0,
            category="Other Income",
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
    ]

    db_session.add_all(records)
    db_session.commit()
    for r in records:
        db_session.refresh(r)
    return records


# ---------------------------------------------------------------------------
# 2. Split transactions
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_split_transactions(db_session: Session) -> dict:
    """Insert parent transactions and their splits.

    Returns a dict with keys ``cc_parent``, ``bank_parent``, and ``splits``
    so tests can reference them by role.
    """
    # CC parent — 300 NIS purchase split across 3 categories
    cc_parent = CreditCardTransaction(
        id="cc_split_parent_1",
        date="2024-02-08",
        provider="isracard",
        account_name="Main Card",
        description="Mega Complex Purchase",
        amount=-300.0,
        category=None,
        tag=None,
        source="credit_card_transactions",
        type="split_parent",
        status="completed",
    )
    db_session.add(cc_parent)
    db_session.flush()  # populate unique_id

    # Bank parent — 200 NIS split across 2 categories
    bank_parent = BankTransaction(
        id="bank_split_parent_1",
        date="2024-02-12",
        provider="hapoalim",
        account_name="Checking",
        description="Mixed Bill Payment",
        amount=-200.0,
        category=None,
        tag=None,
        source="bank_transactions",
        type="split_parent",
        status="completed",
    )
    db_session.add(bank_parent)
    db_session.flush()

    splits = [
        # CC splits
        SplitTransaction(
            transaction_id=cc_parent.unique_id,
            source="credit_card_transactions",
            amount=-150.0,
            category="Food",
            tag="Groceries",
        ),
        SplitTransaction(
            transaction_id=cc_parent.unique_id,
            source="credit_card_transactions",
            amount=-100.0,
            category="Home",
            tag="Cleaning",
        ),
        SplitTransaction(
            transaction_id=cc_parent.unique_id,
            source="credit_card_transactions",
            amount=-50.0,
            category="Other",
            tag=None,
        ),
        # Bank splits
        SplitTransaction(
            transaction_id=bank_parent.unique_id,
            source="bank_transactions",
            amount=-120.0,
            category="Home",
            tag="Maintenance",
        ),
        SplitTransaction(
            transaction_id=bank_parent.unique_id,
            source="bank_transactions",
            amount=-80.0,
            category="Other",
            tag=None,
        ),
    ]

    db_session.add_all(splits)
    db_session.commit()
    for obj in [cc_parent, bank_parent, *splits]:
        db_session.refresh(obj)

    return {
        "cc_parent": cc_parent,
        "bank_parent": bank_parent,
        "splits": splits,
    }


# ---------------------------------------------------------------------------
# 3. Prior-wealth transactions
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_prior_wealth_transactions(db_session: Session) -> dict:
    """Insert prior-wealth seed data (cash, manual investment, bank balances).

    Returns a dict with keys ``cash``, ``manual_investment``, and
    ``bank_balances``.
    """
    cash_pw = CashTransaction(
        id="cash_pw_1",
        date="2024-01-01",
        provider="cash",
        account_name="Cash Wallet",
        description="Prior Wealth - Cash",
        amount=5000.0,
        category="Other Income",
        tag="Prior Wealth",
        source="cash_transactions",
        type="normal",
        status="completed",
    )

    manual_inv_pw = ManualInvestmentTransaction(
        id="inv_pw_1",
        date="2024-01-01",
        provider="manual_investments",
        account_name="Investment Account",
        description="Prior Wealth - Investments",
        amount=3000.0,
        category="Other Income",
        tag="Prior Wealth",
        source="manual_investment_transactions",
        type="normal",
        status="completed",
    )

    bank_balance_1 = BankBalance(
        provider="hapoalim",
        account_name="Checking",
        balance=45000.0,
        prior_wealth_amount=20000.0,
        last_manual_update="2024-01-01",
    )
    bank_balance_2 = BankBalance(
        provider="leumi",
        account_name="Savings",
        balance=30000.0,
        prior_wealth_amount=15000.0,
        last_manual_update="2024-01-01",
    )

    db_session.add_all([cash_pw, manual_inv_pw, bank_balance_1, bank_balance_2])
    db_session.commit()
    for obj in [cash_pw, manual_inv_pw, bank_balance_1, bank_balance_2]:
        db_session.refresh(obj)

    return {
        "cash": cash_pw,
        "manual_investment": manual_inv_pw,
        "bank_balances": [bank_balance_1, bank_balance_2],
    }


# ---------------------------------------------------------------------------
# 4. Untagged transactions
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_untagged_transactions(db_session: Session) -> list:
    """Insert transactions with no category/tag, matching potential tagging rules.

    Descriptions are chosen to match common auto-tagging patterns
    (SUPERMARKET, UBER, Netflix, etc.).
    """
    records = [
        CreditCardTransaction(
            id="cc_untag_1",
            date="2024-01-07",
            provider="isracard",
            account_name="Main Card",
            description="SUPERMARKET PURCHASE",
            amount=-95.0,
            category=None,
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_untag_2",
            date="2024-01-14",
            provider="isracard",
            account_name="Main Card",
            description="UBER TRIP TLV",
            amount=-32.0,
            category=None,
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_untag_3",
            date="2024-02-05",
            provider="max",
            account_name="Joint Card",
            description="Netflix Monthly",
            amount=-49.90,
            category=None,
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_untag_4",
            date="2024-02-19",
            provider="max",
            account_name="Joint Card",
            description="PHARMACY PURCHASE",
            amount=-65.0,
            category=None,
            tag=None,
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_untag_1",
            date="2024-01-22",
            provider="hapoalim",
            account_name="Checking",
            description="SUPERMARKET CHAIN",
            amount=-210.0,
            category=None,
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_untag_2",
            date="2024-02-11",
            provider="hapoalim",
            account_name="Checking",
            description="UBER EATS DELIVERY",
            amount=-78.0,
            category=None,
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_untag_3",
            date="2024-03-05",
            provider="leumi",
            account_name="Business Account",
            description="Netflix Subscription",
            amount=-49.90,
            category=None,
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_untag_4",
            date="2024-03-18",
            provider="leumi",
            account_name="Business Account",
            description="Unknown Wire Transfer",
            amount=-150.0,
            category=None,
            tag=None,
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
    ]

    db_session.add_all(records)
    db_session.commit()
    for r in records:
        db_session.refresh(r)
    return records


# ---------------------------------------------------------------------------
# 5. Project transactions + budget rules
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_project_transactions(db_session: Session) -> dict:
    """Insert project-related transactions and their project budget rules.

    Two projects: Wedding and Renovation, each with several tagged
    transactions and a project budget rule (month=None, year=None).

    Returns a dict with keys ``transactions`` and ``budget_rules``.
    """
    txns = [
        # Wedding transactions
        CreditCardTransaction(
            id="cc_wedding_1",
            date="2024-01-15",
            provider="isracard",
            account_name="Main Card",
            description="Wedding Venue Deposit",
            amount=-5000.0,
            category="Wedding",
            tag="Venue",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_wedding_2",
            date="2024-02-10",
            provider="isracard",
            account_name="Main Card",
            description="Catering Tasting",
            amount=-800.0,
            category="Wedding",
            tag="Catering",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_wedding_1",
            date="2024-02-20",
            provider="hapoalim",
            account_name="Checking",
            description="Wedding Venue Final",
            amount=-15000.0,
            category="Wedding",
            tag="Venue",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_wedding_2",
            date="2024-03-01",
            provider="hapoalim",
            account_name="Checking",
            description="Catering Full Payment",
            amount=-12000.0,
            category="Wedding",
            tag="Catering",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_wedding_3",
            date="2024-03-10",
            provider="max",
            account_name="Joint Card",
            description="Wedding Flowers",
            amount=-2500.0,
            category="Wedding",
            tag="Venue",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        # Renovation transactions
        CreditCardTransaction(
            id="cc_reno_1",
            date="2024-01-20",
            provider="max",
            account_name="Joint Card",
            description="Home Center Materials",
            amount=-3200.0,
            category="Renovation",
            tag="Materials",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_reno_1",
            date="2024-02-05",
            provider="hapoalim",
            account_name="Checking",
            description="Contractor Payment",
            amount=-8000.0,
            category="Renovation",
            tag="Labor",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        CreditCardTransaction(
            id="cc_reno_2",
            date="2024-02-25",
            provider="max",
            account_name="Joint Card",
            description="ACE Hardware Materials",
            amount=-1500.0,
            category="Renovation",
            tag="Materials",
            source="credit_card_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="bank_reno_2",
            date="2024-03-08",
            provider="hapoalim",
            account_name="Checking",
            description="Plumber Payment",
            amount=-4500.0,
            category="Renovation",
            tag="Labor",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        CashTransaction(
            id="cash_reno_1",
            date="2024-03-12",
            provider="cash",
            account_name="Cash Wallet",
            description="Small Hardware Store",
            amount=-350.0,
            category="Renovation",
            tag="Materials",
            source="cash_transactions",
            type="normal",
            status="completed",
        ),
    ]

    budget_rules = [
        BudgetRule(
            name="Wedding Budget",
            amount=50000.0,
            category="Wedding",
            tags="Venue;Catering",
            year=None,
            month=None,
        ),
        BudgetRule(
            name="Renovation Budget",
            amount=25000.0,
            category="Renovation",
            tags="Materials;Labor",
            year=None,
            month=None,
        ),
    ]

    db_session.add_all(txns + budget_rules)
    db_session.commit()
    for obj in txns + budget_rules:
        db_session.refresh(obj)

    return {"transactions": txns, "budget_rules": budget_rules}


# ---------------------------------------------------------------------------
# 6. Budget rules (monthly, Jan 2024)
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_budget_rules(db_session: Session) -> list:
    """Insert monthly budget rules for January 2024.

    Includes Total Budget, Food, Transport, and Entertainment budgets.
    """
    rules = [
        BudgetRule(
            name="Total Budget",
            amount=10000.0,
            category=None,
            tags=None,
            year=2024,
            month=1,
        ),
        BudgetRule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags="All Tags",
            year=2024,
            month=1,
        ),
        BudgetRule(
            name="Transport",
            amount=500.0,
            category="Transport",
            tags=None,
            year=2024,
            month=1,
        ),
        BudgetRule(
            name="Entertainment",
            amount=300.0,
            category="Entertainment",
            tags=None,
            year=2024,
            month=1,
        ),
    ]

    db_session.add_all(rules)
    db_session.commit()
    for r in rules:
        db_session.refresh(r)
    return rules


# ---------------------------------------------------------------------------
# 7. Tagging rules
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_tagging_rules(db_session: Session) -> list:
    """Insert tagging rules for automated categorisation.

    Rules target descriptions containing SUPERMARKET, UBER, and Netflix.
    """
    rules = [
        TaggingRule(
            name="Supermarket Rule",
            conditions={
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "SUPERMARKET",
                    }
                ],
            },
            category="Food",
            tag="Groceries",
        ),
        TaggingRule(
            name="Uber Rule",
            conditions={
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "UBER",
                    }
                ],
            },
            category="Transport",
            tag="Rides",
        ),
        TaggingRule(
            name="Netflix Rule",
            conditions={
                "type": "AND",
                "subconditions": [
                    {
                        "type": "CONDITION",
                        "field": "description",
                        "operator": "contains",
                        "value": "Netflix",
                    }
                ],
            },
            category="Entertainment",
            tag="Streaming",
        ),
    ]

    db_session.add_all(rules)
    db_session.commit()
    for r in rules:
        db_session.refresh(r)
    return rules


# ---------------------------------------------------------------------------
# 8. Investments
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_investments(db_session: Session) -> dict:
    """Insert investment records and related manual-investment transactions.

    Returns a dict with keys ``investments`` and ``transactions``.
    """
    stock_fund = Investment(
        category="Investments",
        tag="Stock Fund",
        type="mutual_fund",
        name="Migdal S&P 500 Fund",
        interest_rate=7.5,
        interest_rate_type="variable",
        created_date="2023-06-15",
        is_closed=0,
    )
    bond_fund = Investment(
        category="Investments",
        tag="Bond Fund",
        type="bond",
        name="Psagot Government Bond",
        interest_rate=3.2,
        interest_rate_type="fixed",
        created_date="2023-01-10",
        is_closed=1,
        closed_date="2024-01-10",
        maturity_date="2024-01-10",
    )

    db_session.add_all([stock_fund, bond_fund])
    db_session.flush()

    inv_txns = [
        ManualInvestmentTransaction(
            id="inv_txn_1",
            date="2023-06-15",
            provider="manual_investments",
            account_name="Investment Account",
            description="Initial deposit - Migdal S&P 500",
            amount=-10000.0,
            category="Investments",
            tag="Stock Fund",
            source="manual_investment_transactions",
            type="normal",
            status="completed",
        ),
        ManualInvestmentTransaction(
            id="inv_txn_2",
            date="2024-01-15",
            provider="manual_investments",
            account_name="Investment Account",
            description="Monthly deposit - Migdal S&P 500",
            amount=-2000.0,
            category="Investments",
            tag="Stock Fund",
            source="manual_investment_transactions",
            type="normal",
            status="completed",
        ),
        ManualInvestmentTransaction(
            id="inv_txn_3",
            date="2023-01-10",
            provider="manual_investments",
            account_name="Investment Account",
            description="Bond purchase - Psagot Gov",
            amount=-5000.0,
            category="Investments",
            tag="Bond Fund",
            source="manual_investment_transactions",
            type="normal",
            status="completed",
        ),
        ManualInvestmentTransaction(
            id="inv_txn_4",
            date="2024-01-10",
            provider="manual_investments",
            account_name="Investment Account",
            description="Bond maturity - Psagot Gov",
            amount=5160.0,
            category="Investments",
            tag="Bond Fund",
            source="manual_investment_transactions",
            type="normal",
            status="completed",
        ),
    ]

    db_session.add_all(inv_txns)
    db_session.commit()
    for obj in [stock_fund, bond_fund, *inv_txns]:
        db_session.refresh(obj)

    return {
        "investments": [stock_fund, bond_fund],
        "transactions": inv_txns,
    }


# ---------------------------------------------------------------------------
# 9. Sample categories YAML
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_categories_yaml() -> dict:
    """Return a realistic categories-to-tags mapping dict.

    Mirrors the structure of ``~/.finance-analysis/categories.yaml``.
    No database interaction required.
    """
    return {
        "Food": ["Groceries", "Restaurants", "Coffee"],
        "Transport": ["Gas", "Parking", "Rides"],
        "Entertainment": ["Cinema", "Streaming"],
        "Salary": [],
        "Other Income": ["Prior Wealth"],
        "Ignore": ["Transfer"],
        "Investments": ["Stock Fund", "Bond Fund"],
        "Liabilities": ["Mortgage"],
        "Wedding": ["Venue", "Catering"],
        "Renovation": ["Materials", "Labor"],
        "Home": ["Cleaning", "Maintenance", "Rent"],
        "Other": [],
    }


# ---------------------------------------------------------------------------
# 10. Sample credentials YAML
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_credentials_yaml() -> dict:
    """Return a fake credentials dict for testing.

    Mirrors the structure of ``~/.finance-analysis/credentials.yaml``
    without any real secrets.
    """
    return {
        "credit_cards": {
            "isracard": [
                {
                    "username": "test_user",
                    "card6Digits": "123456",
                    "id": "000000000",
                }
            ],
        },
        "banks": {
            "hapoalim": [
                {
                    "userCode": "test_code",
                }
            ],
        },
    }
