import logging
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

logger = logging.getLogger(__name__)

# Characters that Israeli providers sprinkle into scraped amount cells:
# thousands separators, bidi control marks, non-breaking spaces, and the
# shekel sign. Stripped before any numeric coercion.
_AMOUNT_NOISE = (
    ",", "‎", "‏", "‪", "‫", "‬", "‭", "‮",
    " ", " ", "₪", "₪",
)


def parse_transaction_date(date_str: str) -> date:
    """Parse a ``Transaction.date`` value into a ``date``.

    Most providers already emit ISO-8601, so ISO is tried first and
    strictly. Anything else is Israeli-style and therefore **day-first**:
    ``dateutil``'s default is month-first, which silently read
    ``03/12/2024`` as 12 March instead of 3 December — a nine-month error
    that both shifted installment dates and dropped transactions from the
    scrape window.

    ``dayfirst=True`` must NOT be applied blanket-wide: ``dateutil`` honours
    it even for ``YYYY-MM-DD`` input, re-reading ``2024-01-10`` as
    2024-10-01. Hence the ISO-first ordering.

    Parameters
    ----------
    date_str : str
        The transaction's date string.

    Returns
    -------
    date
        The parsed calendar date.

    Raises
    ------
    ValueError
        If the value cannot be parsed at all — a loud failure is preferable
        to silently mis-dating money.
    """
    text = str(date_str).strip()
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return parse_date(text, dayfirst=True).date()


def to_amount(value: object, default: float = 0.0) -> float:
    """Coerce a raw provider amount to ``float``.

    Provider APIs return amounts as numbers *or* as formatted strings
    (``"1,234.56"``), sometimes padded with bidi control marks. A bare
    ``float(value)`` raises ``ValueError`` on those strings, which aborts
    the entire scrape run from inside a per-row loop.

    Parameters
    ----------
    value : object
        Raw amount from the provider (number, numeric string, or None).
    default : float
        Value returned when ``value`` cannot be parsed at all.

    Returns
    -------
    float
        The parsed amount, or ``default`` when it cannot be parsed.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    cleaned = str(value)
    for noise in _AMOUNT_NOISE:
        cleaned = cleaned.replace(noise, "")
    cleaned = cleaned.strip()
    if not cleaned:
        return default
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return default


def parse_provider_date(
    value: object, date_format: Optional[str] = None
) -> Optional[datetime]:
    """Parse a provider date, returning ``None`` when it cannot be read.

    Providers used to fall back to passing the *raw* string through when
    ``strptime`` failed. That raw text landed in the DB date column, where
    it broke every date filter and sort, and was later re-parsed
    month-first (turning ``03/12/2024`` into 12 March). Returning ``None``
    lets callers drop the row instead of corrupting it.

    Parameters
    ----------
    value : object
        Raw date value scraped from the provider.
    date_format : str, optional
        ``strptime`` format. When omitted the value is parsed as ISO-8601.

    Returns
    -------
    Optional[datetime]
        The parsed datetime, or ``None`` when the value is empty or
        does not match the expected shape.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if date_format:
            return datetime.strptime(text, date_format)
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def fix_installments(transactions: list[Transaction]) -> list[Transaction]:
    """Adjust dates for non-initial installment transactions."""
    result = []
    for txn in transactions:
        if (
            txn.type == TransactionType.INSTALLMENTS
            and txn.installments
            and txn.installments.number > 1
        ):
            txn_date = parse_transaction_date(txn.date)
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
        ``strptime`` format of the row's date column. A row whose date does
        not match is logged and dropped — never emitted with a raw,
        unparseable date string.
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

        parsed_date = parse_provider_date(date_str, date_format)
        if parsed_date is None:
            logger.warning(
                "Dropping scraped row with unparseable date %r "
                "(expected format %r)",
                date_str,
                date_format,
            )
            continue
        date_iso = parsed_date.isoformat()

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
        txn_date = parse_transaction_date(txn.date)
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
