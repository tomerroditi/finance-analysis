"""Tests for the Mizrahi Tefahot provider's pure parsing helpers."""

import asyncio

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.mizrahi import (
    _convert_transactions,
    _extract_pending_transactions,
    _get_transaction_identifier,
)


def _raw_row(**overrides) -> dict:
    """Build a realistic raw Mizrahi API transaction row."""
    row = {
        "MC02PeulaTaaEZ": "2024-03-15T00:00:00",
        "MC02SchumEZ": -89.9,
        "MC02TnuaTeurEZ": "כרטיס אשראי",
        "MC02AsmahtaMekoritEZ": "0034567",
        "TransactionNumber": "1",
        "IsTodayTransaction": False,
    }
    row.update(overrides)
    return row


class TestMizrahiTransactionIdentifier:
    """Tests for the reference + transaction-number identifier builder."""

    def test_numeric_reference_drops_leading_zeros(self):
        """A numeric reference with TransactionNumber 1 is int-normalized."""
        assert _get_transaction_identifier(_raw_row()) == "34567"

    def test_multi_transaction_number_appended(self):
        """A TransactionNumber other than 1 is appended after a dash."""
        row = _raw_row(TransactionNumber="3")
        assert _get_transaction_identifier(row) == "0034567-3"

    def test_missing_reference_gives_none(self):
        """Without a reference the identifier is None."""
        assert _get_transaction_identifier(
            _raw_row(MC02AsmahtaMekoritEZ=None)
        ) is None

    def test_non_numeric_reference_stringified(self):
        """A non-numeric reference is returned as a plain string."""
        row = _raw_row(MC02AsmahtaMekoritEZ="ref-x")
        assert _get_transaction_identifier(row) == "ref-x"


class TestMizrahiConvertTransactions:
    """Tests for the Mizrahi raw-row to Transaction converter."""

    def test_fields_are_mapped(self):
        """Date, amount, description, and identifier map from the raw row."""
        result = asyncio.run(_convert_transactions([_raw_row()]))
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.date == "2024-03-15T00:00:00"
        assert txn.processed_date == "2024-03-15T00:00:00"
        assert txn.original_amount == -89.9
        assert txn.charged_amount == -89.9
        assert txn.original_currency == "ILS"
        assert txn.description == "כרטיס אשראי"
        assert txn.identifier == "34567"
        assert txn.status == TransactionStatus.COMPLETED

    def test_today_transaction_pending_when_flag_enabled(self):
        """pending_if_today marks today's rows PENDING."""
        result = asyncio.run(
            _convert_transactions(
                [_raw_row(IsTodayTransaction=True)], pending_if_today=True
            )
        )
        assert result[0].status == TransactionStatus.PENDING

    def test_today_transaction_completed_when_flag_disabled(self):
        """Without pending_if_today even today's rows stay COMPLETED."""
        result = asyncio.run(
            _convert_transactions([_raw_row(IsTodayTransaction=True)])
        )
        assert result[0].status == TransactionStatus.COMPLETED

    def test_unparseable_date_row_is_skipped(self):
        """A malformed date drops the row instead of writing raw text.

        The raw string went straight into the DB date column, which broke
        every downstream date filter and sort.
        """
        result = asyncio.run(
            _convert_transactions([_raw_row(MC02PeulaTaaEZ="15/03/2024")])
        )
        assert result == []

    def test_empty_input_gives_empty_output(self):
        """No rows in, no transactions out."""
        assert asyncio.run(_convert_transactions([])) == []


def _pending_row(*cells: str) -> list[str]:
    """Build a raw pending-table row (list of cell texts)."""
    return list(cells)


class _FakeFrame:
    """Minimal stand-in for a Playwright frame returning canned table rows."""

    def __init__(self, rows: list[list[str]]):
        self._rows = rows

    async def eval_on_selector_all(self, selector: str, expression: str):
        """Return the canned rows regardless of selector/expression."""
        return self._rows


class TestMizrahiPendingTransactions:
    """Tests for the DOM-scraped pending-transactions extractor.

    The pending table renders unsigned magnitudes, so the extractor has to
    normalize the sign itself — the completed path gets an already-signed
    value from the API.
    """

    def test_pending_charge_is_negative(self):
        """A pending charge is an expense, so it must be recorded negative."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "0012345", "1,250.00", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert len(result) == 1
        assert result[0].charged_amount == -1250.0
        assert result[0].original_amount == -1250.0
        assert result[0].status == TransactionStatus.PENDING

    def test_pending_row_carries_an_identifier(self):
        """The reference column becomes the transaction identifier."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "0012345", "1,250.00", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert result[0].identifier == "12345"

    def test_non_numeric_reference_gives_no_identifier(self):
        """A reference cell without digits leaves the identifier unset."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "", "10.00", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert result[0].identifier is None

    def test_shekel_sign_and_rtl_mark_still_parse(self):
        """A ₪ sign or bidi mark must not degrade the amount to zero."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "0012345", "‏₪1,250.00", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert result[0].charged_amount == -1250.0

    def test_unparseable_amount_skips_the_row(self):
        """An unreadable amount must not become a real zero-amount row."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "0012345", "לא ידוע", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert result == []

    def test_already_negative_amount_stays_negative(self):
        """A cell that already carries a minus sign is not double-negated."""
        frame = _FakeFrame([
            _pending_row("15/03/24", "סופרמרקט", "0012345", "-1,250.00", "")
        ])
        result = asyncio.run(_extract_pending_transactions(frame))
        assert result[0].charged_amount == -1250.0

    def test_short_rows_are_ignored(self):
        """Rows without the expected column count are skipped."""
        frame = _FakeFrame([_pending_row("15/03/24", "x")])
        assert asyncio.run(_extract_pending_transactions(frame)) == []
