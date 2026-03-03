from datetime import date

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta

from scraper.models.transaction import Transaction, TransactionType


def fix_installments(transactions: list[Transaction]) -> list[Transaction]:
    """Adjust dates for non-initial installment transactions."""
    result = []
    for txn in transactions:
        if (
            txn.type == TransactionType.INSTALLMENTS
            and txn.installments
            and txn.installments.number > 1
        ):
            txn_date = parse_date(txn.date).date()
            adjusted = txn_date + relativedelta(months=txn.installments.number - 1)
            txn = Transaction(**{**txn.__dict__, "date": adjusted.isoformat()})
        result.append(txn)
    return result


def sort_transactions_by_date(transactions: list[Transaction]) -> list[Transaction]:
    """Sort transactions by date ascending."""
    return sorted(transactions, key=lambda t: t.date)


def filter_old_transactions(
    transactions: list[Transaction],
    start_date: date,
    combine_installments: bool = False,
) -> list[Transaction]:
    """Filter out transactions before start_date."""
    result = []
    for txn in transactions:
        txn_date = parse_date(txn.date).date()
        if not combine_installments:
            if txn_date >= start_date:
                result.append(txn)
        else:
            is_normal = txn.type == TransactionType.NORMAL
            is_initial = (
                txn.type == TransactionType.INSTALLMENTS
                and txn.installments
                and txn.installments.number == 1
            )
            if (is_normal or is_initial) and txn_date >= start_date:
                result.append(txn)
    return result
