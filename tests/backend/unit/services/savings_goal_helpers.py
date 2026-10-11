"""Shared fixtures-as-functions for the savings-goal service tests.

Plain helpers, not tests: they seed transactions, liquid money and project
budgets into the test database so each savings-goal test file can describe
its scenario in a few lines.
"""

from datetime import date

from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance
from backend.models.transaction import BankTransaction, CreditCardTransaction
from backend.services.budget.project import ProjectBudgetService
from backend.services.tagging_service import CategoriesTagsService


def month_str(offset_back: int) -> str:
    """Return ``YYYY-MM`` for the month ``offset_back`` months before now."""
    today = date.today()
    month = today.month - offset_back
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return f"{year:04d}-{month:02d}"


def day_in_month(month: str, day: int = 15) -> str:
    """Return a ``YYYY-MM-DD`` date inside the given ``YYYY-MM`` month."""
    return f"{month}-{day:02d}"


def add_txn(
    db: Session,
    month: str,
    amount: float,
    category: str,
    tag: str | None = None,
    day: int = 15,
) -> BankTransaction:
    """Insert one bank transaction into a month and return it."""
    txn = BankTransaction(
        id=f"t-{month}-{amount}-{day}",
        date=day_in_month(month, day),
        provider="TestBank",
        account_name="Main",
        description="test",
        amount=amount,
        category=category,
        tag=tag,
        source="bank_transactions",
        type="normal",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def add_card_txn(
    db: Session, month: str, amount: float, category: str, day: int = 15
) -> CreditCardTransaction:
    """Insert one itemized credit-card purchase into a month and return it."""
    txn = CreditCardTransaction(
        id=f"cc-{month}-{amount}-{day}",
        date=day_in_month(month, day),
        provider="TestCard",
        account_name="Card",
        description="test",
        amount=amount,
        category=category,
        source="credit_card_transactions",
        type="normal",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


def seed_surplus(db: Session, month: str, income: float, expenses: float) -> None:
    """Give a month a known realized surplus of ``income - expenses``."""
    add_txn(db, month, income, "Salary", day=1)
    add_txn(db, month, -expenses, "Food", day=2)


def seed_liquid(db: Session, amount: float) -> None:
    """Give the user ``amount`` of liquid money from before tracking began.

    Free cash is bank and cash prior wealth, plus every bank and cash
    transaction, less what the goals hold — so this is how a test says "there
    was already money in the account".
    """
    db.add(
        BankBalance(
            provider="TestBank",
            account_name="Main",
            balance=amount,
            prior_wealth_amount=amount,
        )
    )
    db.commit()


def create_project(db: Session, name: str, budget: float = 50000) -> None:
    """Create a project budget over a fresh category."""
    CategoriesTagsService(db).add_category(name, ["Venue"])
    ProjectBudgetService(db).create_project(name, budget)
