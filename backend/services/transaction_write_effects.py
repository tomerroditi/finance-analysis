"""
Keep the figures derived from transactions true after a write.

Two stored figures are sums over transaction rows: a cash account's balance
(its prior wealth plus its cash transactions) and an investment's prior wealth
(minus its manual investment transactions, matched by category and tag). A
write that creates, moves, retags, re-amounts or removes such a row must
recompute the holdings on *both* sides of the change — the account or
investment the row left as well as the one it joined.

Callers wrap the write in :meth:`TransactionWriteEffects.track` and say only
which rows they are about to touch; the tracker reads those rows before and
after and recomputes every holding either reading names. Bank and credit-card
rows carry no such figure, so tracking them costs nothing.
"""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.repositories.transactions import TransactionsRepository
from backend.services.cash_balance_service import CashBalanceService
from backend.services.investments import InvestmentsService

HoldingKey = tuple[str | None, str | None, str | None]

_TRACKED_TABLES = {Tables.CASH.value, Tables.MANUAL_INVESTMENT_TRANSACTIONS.value}


class TouchedRows:
    """The holdings a write moves money in or out of.

    Parameters
    ----------
    table : str
        Table the write targets.
    """

    def __init__(self, table: str) -> None:
        self.table = table
        self.keys: set[HoldingKey] = set()

    def include(
        self,
        account_name: str | None = None,
        category: str | None = None,
        tag: str | None = None,
    ) -> None:
        """Add a row the tracked ids cannot name, such as one being created.

        Parameters
        ----------
        account_name : str, optional
            The row's account.
        category : str, optional
            The row's category.
        tag : str, optional
            The row's tag.
        """
        self.keys.add((account_name, category, tag))


class TransactionWriteEffects:
    """Recompute cash balances and investment prior wealth around a write.

    Parameters
    ----------
    db : Session
        Database session the write runs on.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.transactions_repository = TransactionsRepository(db)

    @contextmanager
    def track(
        self, source: str, unique_ids: Iterable[int] = ()
    ) -> Iterator[TouchedRows]:
        """Recompute every holding the rows named belong to, before or after.

        The block's write must be committed when it exits normally; nothing is
        recomputed when it raises.

        Parameters
        ----------
        source : str
            Table or service name of the rows being written.
        unique_ids : iterable of int, optional
            Existing rows the write updates or deletes.

        Yields
        ------
        TouchedRows
            Lets the caller add rows the ids do not cover, such as a new one.
        """
        repo = self.transactions_repository.get_repo_by_source(source)
        table = repo.model.__tablename__ if repo is not None else source
        touched = TouchedRows(table)
        if table not in _TRACKED_TABLES:
            yield touched
            return

        ids = list(unique_ids)
        touched.keys.update(self._keys(table, ids))
        yield touched
        touched.keys.update(self._keys(table, ids))
        self._recompute(touched)

    def _keys(self, table: str, unique_ids: list[int]) -> list[HoldingKey]:
        """Read the holding keys of the rows that currently exist."""
        if not unique_ids:
            return []
        return self.transactions_repository.get_holding_keys(table, unique_ids)

    def _recompute(self, touched: TouchedRows) -> None:
        """Recompute the stored figure of every holding in ``touched``."""
        if touched.table == Tables.CASH.value:
            cash_balances = CashBalanceService(self.db)
            for account in sorted({k[0] for k in touched.keys if k[0]}):
                cash_balances.recalculate_current_balance(account)
            return

        investments = InvestmentsService(self.db)
        for category, tag in sorted(
            {(k[1], k[2]) for k in touched.keys if k[1] and k[2]}
        ):
            investments.recalculate_prior_wealth_by_tag(category, tag)
