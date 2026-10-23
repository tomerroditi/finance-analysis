"""Every transaction write leaves the balances derived from transactions true.

A cash account's balance is its prior wealth plus the sum of its cash
transactions, and an investment's prior wealth is minus the sum of the manual
investment transactions under its category and tag. Each write through
``TransactionsService`` must leave both identities holding, whichever rows it
created, moved, retagged or removed.
"""

from collections.abc import Callable
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.cash_balance import CashBalance
from backend.models.investment import Investment
from backend.models.transaction import CashTransaction, ManualInvestmentTransaction
from backend.services.cash_balance_service import CashBalanceService
from backend.services.investments import InvestmentsService
from backend.services.transactions_service import TransactionsService

CASH = "cash_transactions"
INVEST = "manual_investment_transactions"


def _cash(db: Session, tx_id: str, account: str, amount: float) -> int:
    """Insert one cash transaction and return its unique_id."""
    tx = CashTransaction(
        id=tx_id, date="2024-02-10", provider="CASH", account_name=account,
        description=tx_id, amount=amount, category="Food", tag="Groceries",
        source=CASH, type="normal", status="completed",
    )
    db.add(tx)
    db.commit()
    return tx.unique_id


@pytest.fixture
def holdings(db_session: Session, seed_investments: dict) -> dict[str, int]:
    """Two cash accounts and two investments whose stored figures are current."""
    db_session.add_all([
        CashBalance(account_name="Wallet", balance=0.0, prior_wealth_amount=500.0),
        CashBalance(account_name="Envelope", balance=0.0, prior_wealth_amount=0.0),
    ])
    db_session.commit()
    ids = {
        "wallet": _cash(db_session, "c1", "Wallet", -100.0),
        "wallet_2": _cash(db_session, "c2", "Wallet", -40.0),
        "envelope": _cash(db_session, "c3", "Envelope", -25.0),
    }
    for name in ("Wallet", "Envelope"):
        CashBalanceService(db_session).recalculate_current_balance(name)
    for inv in seed_investments["investments"]:
        InvestmentsService(db_session).recalculate_prior_wealth(inv.id)
    for tx in seed_investments["transactions"]:
        ids[tx.id] = tx.unique_id
    return ids


def _assert_derived_figures_hold(db: Session) -> None:
    """Every stored balance and prior wealth matches the transactions under it."""
    db.expire_all()
    for row in db.scalars(select(CashBalance)):
        spent = db.scalar(
            select(func.coalesce(func.sum(CashTransaction.amount), 0.0)).where(
                CashTransaction.account_name == row.account_name
            )
        )
        assert row.balance == pytest.approx(row.prior_wealth_amount + spent), (
            row.account_name
        )
    for inv in db.scalars(select(Investment)):
        total = db.scalar(
            select(func.coalesce(func.sum(ManualInvestmentTransaction.amount), 0.0))
            .where(ManualInvestmentTransaction.category == inv.category)
            .where(ManualInvestmentTransaction.tag == inv.tag)
        )
        assert inv.prior_wealth_amount == pytest.approx(-total), inv.tag


WRITES: dict[str, Callable[[TransactionsService, dict[str, int]], object]] = {
    "create cash": lambda s, ids: s.create_transaction(
        {"date": date(2024, 3, 1), "description": "x", "amount": -7.0,
         "account_name": "Wallet"}, "cash",
    ),
    "create cash in a new account": lambda s, ids: s.create_transaction(
        {"date": date(2024, 3, 1), "description": "x", "amount": -7.0,
         "account_name": "Jar"}, "cash",
    ),
    "create investment deposit": lambda s, ids: s.create_transaction(
        {"date": date(2024, 3, 1), "description": "x", "amount": -300.0,
         "account_name": "Investment Account", "category": "Investments",
         "tag": "Stock Fund"}, "manual_investments",
    ),
    "edit cash amount": lambda s, ids: s.update_transaction(
        ids["wallet"], CASH, {"amount": -900.0}
    ),
    "move cash to another account": lambda s, ids: s.update_transaction(
        ids["wallet"], CASH, {"account_name": "Envelope"}
    ),
    "edit investment amount": lambda s, ids: s.update_transaction(
        ids["inv_txn_2"], INVEST, {"amount": -6000.0}
    ),
    "move investment deposit to another investment": lambda s, ids: (
        s.update_transaction(ids["inv_txn_2"], INVEST, {"tag": "Bond Fund"})
    ),
    "retag investment deposit": lambda s, ids: s.update_tagging_by_id(
        INVEST, ids["inv_txn_2"], "Investments", "Bond Fund"
    ),
    "untag investment deposit": lambda s, ids: s.update_transaction(
        ids["inv_txn_2"], INVEST, {"category": "", "tag": ""}
    ),
    "delete cash": lambda s, ids: s.delete_transaction(ids["wallet"], CASH),
    "delete investment deposit": lambda s, ids: s.delete_transaction(
        ids["inv_txn_2"], INVEST
    ),
    "bulk edit cash amount": lambda s, ids: s.bulk_tag_transactions(
        [ids["wallet"], ids["envelope"]], CASH, "Food", "Groceries", amount=-1.0
    ),
    "bulk move cash to another account": lambda s, ids: s.bulk_tag_transactions(
        [ids["wallet"], ids["wallet_2"]], CASH, "Food", "Groceries",
        account_name="Envelope",
    ),
    "bulk retag investment deposits": lambda s, ids: s.bulk_tag_transactions(
        [ids["inv_txn_1"], ids["inv_txn_3"]], INVEST, "Investments", "Bond Fund"
    ),
    "bulk edit investment amounts": lambda s, ids: s.bulk_tag_transactions(
        [ids["inv_txn_1"], ids["inv_txn_3"]], INVEST, "Investments",
        "Stock Fund", amount=-1.0,
    ),
}


class TestTransactionWriteEffects:
    """Writes keep cash balances and investment prior wealth in step."""

    @pytest.mark.parametrize("write", WRITES.values(), ids=WRITES.keys())
    def test_write_keeps_derived_figures(
        self,
        db_session: Session,
        holdings: dict[str, int],
        write: Callable[[TransactionsService, dict[str, int]], object],
    ) -> None:
        """After the write, every balance and prior wealth matches its rows."""
        _assert_derived_figures_hold(db_session)

        write(TransactionsService(db_session), holdings)

        _assert_derived_figures_hold(db_session)
