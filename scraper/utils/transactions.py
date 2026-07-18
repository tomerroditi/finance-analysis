import math
import re
from datetime import date, datetime
from typing import Callable, Optional

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta

from scraper.models.transaction import (
    Transaction,
    TransactionStatus,
    TransactionType,
)


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


def parse_amount(
    amount_str: str,
    strip_symbols: tuple[str, ...] = (),
    default: float = float("nan"),
) -> float:
    """Parse a formatted amount string into a float.

    Parameters
    ----------
    amount_str : str
        Amount string, potentially containing thousands separators and
        currency symbols.
    strip_symbols : tuple[str, ...]
        Extra substrings (e.g. a currency symbol) to remove before parsing.
        Commas are always removed.
    default : float
        Value returned when the string cannot be parsed (default NaN).

    Returns
    -------
    float
        Parsed numeric value, or ``default`` if unparseable.
    """
    try:
        cleaned = amount_str.replace(",", "")
        for symbol in strip_symbols:
            cleaned = cleaned.replace(symbol, "")
        return float(cleaned)
    except (ValueError, TypeError, AttributeError):
        return default


def credit_debit_amount(
    credit: str,
    debit: str,
    strip_symbols: tuple[str, ...] = (),
) -> float:
    """Calculate the net transaction amount from credit and debit strings.

    Unparseable values count as 0, so a row with only a debit (or only a
    credit) column still yields the correct signed amount.

    Parameters
    ----------
    credit : str
        Credit amount string.
    debit : str
        Debit amount string.
    strip_symbols : tuple[str, ...]
        Extra substrings to remove before parsing (see ``parse_amount``).

    Returns
    -------
    float
        Net amount (credit - debit).
    """
    credit_val = parse_amount(credit, strip_symbols=strip_symbols)
    debit_val = parse_amount(debit, strip_symbols=strip_symbols)
    credit_num = 0.0 if math.isnan(credit_val) else credit_val
    debit_num = 0.0 if math.isnan(debit_val) else debit_val
    return credit_num - debit_num


def parse_int_identifier(reference: str, strip: bool = False) -> Optional[str]:
    """Normalize a reference string into a transaction identifier.

    Numeric references are canonicalized through ``int`` (dropping leading
    zeros); non-numeric references pass through unchanged; empty references
    become None.

    Parameters
    ----------
    reference : str
        Raw reference/asmachta string scraped from the page.
    strip : bool
        Whether to strip surrounding whitespace before processing.

    Returns
    -------
    Optional[str]
        Normalized identifier, or None when the reference is empty.
    """
    if strip:
        reference = (reference or "").strip()
    if not reference:
        return None
    try:
        return str(int(reference))
    except (ValueError, TypeError):
        return reference


def parse_digits_identifier(reference: str) -> Optional[str]:
    """Extract only the digits of a reference string as an identifier.

    Parameters
    ----------
    reference : str
        Raw reference string scraped from the page.

    Returns
    -------
    Optional[str]
        The digits of the reference, or None when no digits remain.
    """
    cleaned = re.sub(r"\D+", "", reference or "")
    return cleaned if cleaned else None


def convert_credit_debit_rows(
    txns: list[dict],
    date_format: str,
    parse_identifier: Callable[[str], Optional[str]],
    strip_symbols: tuple[str, ...] = (),
    skip_empty_date: bool = False,
    currency: str = "ILS",
) -> list[Transaction]:
    """Convert scraped credit/debit table rows to Transaction objects.

    Shared converter for DOM-scraping bank providers (Beinleumi group,
    Union, Yahav) whose extractors produce dicts with ``date``,
    ``description``, ``reference``, ``credit``, ``debit``, and optional
    ``memo``/``status`` keys.

    Parameters
    ----------
    txns : list[dict]
        Raw scraped transaction dicts.
    date_format : str
        ``strptime`` format of the row's date column. A date that fails to
        parse is passed through verbatim.
    parse_identifier : Callable[[str], Optional[str]]
        Provider-specific reference-to-identifier normalizer.
    strip_symbols : tuple[str, ...]
        Extra substrings to remove when parsing amounts.
    skip_empty_date : bool
        Whether to drop rows whose date column is empty.
    currency : str
        Currency code assigned to every transaction.

    Returns
    -------
    list[Transaction]
        Parsed transaction objects.
    """
    results: list[Transaction] = []
    for txn in txns:
        date_str = txn.get("date", "")
        if skip_empty_date and not date_str:
            continue

        try:
            date_iso = datetime.strptime(date_str, date_format).isoformat()
        except (ValueError, TypeError):
            date_iso = date_str

        amount = credit_debit_amount(
            txn.get("credit", ""),
            txn.get("debit", ""),
            strip_symbols=strip_symbols,
        )

        results.append(
            Transaction(
                type=TransactionType.NORMAL,
                status=txn.get("status", TransactionStatus.COMPLETED),
                date=date_iso,
                processed_date=date_iso,
                original_amount=amount,
                original_currency=currency,
                charged_amount=amount,
                description=txn.get("description", ""),
                identifier=parse_identifier(txn.get("reference", "")),
                memo=txn.get("memo") or None,
            )
        )
    return results


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
