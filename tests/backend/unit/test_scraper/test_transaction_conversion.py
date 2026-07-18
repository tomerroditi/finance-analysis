"""Tests for the shared transaction-conversion helpers in scraper.utils."""

import asyncio
import math
from datetime import date

import pytest

from scraper.models.transaction import (
    InstallmentInfo,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from scraper.utils.transactions import (
    convert_credit_debit_rows,
    credit_debit_amount,
    filter_old_transactions,
    fix_installments,
    parse_amount,
    parse_digits_identifier,
    parse_int_identifier,
    sort_transactions_by_date,
)
from scraper.utils.waiting import wait_for_first


def _make_txn(**overrides) -> Transaction:
    """Build a Transaction with sane defaults, overridable per test."""
    defaults = dict(
        type=TransactionType.NORMAL,
        status=TransactionStatus.COMPLETED,
        date="2024-03-15T00:00:00",
        processed_date="2024-03-15T00:00:00",
        original_amount=-100.0,
        original_currency="ILS",
        charged_amount=-100.0,
        description="test",
    )
    defaults.update(overrides)
    return Transaction(**defaults)


class TestParseAmount:
    """Tests for the shared amount-string parser."""

    def test_plain_number_parses(self):
        """A plain numeric string parses to its float value."""
        assert parse_amount("1234.56") == 1234.56

    def test_commas_are_stripped(self):
        """Thousands separators are removed before parsing."""
        assert parse_amount("1,234,567.89") == 1234567.89

    def test_currency_symbols_are_stripped_when_requested(self):
        """Symbols passed in strip_symbols are removed before parsing."""
        assert parse_amount("₪1,234.56", strip_symbols=("₪",)) == 1234.56

    def test_unstripped_symbol_yields_default(self):
        """A symbol not listed in strip_symbols makes the string unparseable."""
        assert math.isnan(parse_amount("₪123"))

    def test_unparseable_returns_nan_by_default(self):
        """Garbage input returns NaN when no default is given."""
        assert math.isnan(parse_amount("not-a-number"))

    def test_unparseable_returns_custom_default(self):
        """Garbage input returns the caller-provided default."""
        assert parse_amount("garbage", default=0.0) == 0.0

    def test_none_input_returns_default(self):
        """A None input is treated as unparseable, not an exception."""
        assert parse_amount(None, default=0.0) == 0.0

    def test_negative_amount_parses(self):
        """Negative amounts keep their sign."""
        assert parse_amount("-42.5") == -42.5


class TestCreditDebitAmount:
    """Tests for the net credit-minus-debit amount calculation."""

    def test_credit_only_is_positive(self):
        """A credit with an empty debit yields a positive amount."""
        assert credit_debit_amount("150.00", "") == 150.0

    def test_debit_only_is_negative(self):
        """A debit with an empty credit yields a negative amount."""
        assert credit_debit_amount("", "75.25") == -75.25

    def test_both_columns_net_out(self):
        """When both columns are present the result is credit minus debit."""
        assert credit_debit_amount("100", "40") == 60.0

    def test_both_empty_is_zero(self):
        """Two empty columns net to zero (unparseable counts as 0)."""
        assert credit_debit_amount("", "") == 0.0

    def test_symbols_stripped_in_both_columns(self):
        """strip_symbols applies to both the credit and debit strings."""
        assert credit_debit_amount(
            "₪10", "₪4", strip_symbols=("₪",)
        ) == 6.0

    def test_commas_handled(self):
        """Comma-formatted amounts are parsed in both columns."""
        assert credit_debit_amount("1,000.50", "500.25") == 500.25


class TestParseIntIdentifier:
    """Tests for the int-normalizing reference parser."""

    def test_numeric_reference_drops_leading_zeros(self):
        """A numeric reference is canonicalized through int."""
        assert parse_int_identifier("00123") == "123"

    def test_non_numeric_reference_passes_through(self):
        """A non-numeric reference is returned unchanged."""
        assert parse_int_identifier("ref-42") == "ref-42"

    def test_empty_reference_is_none(self):
        """An empty reference yields None."""
        assert parse_int_identifier("") is None

    def test_strip_removes_surrounding_whitespace(self):
        """With strip=True, padded numeric references still normalize."""
        assert parse_int_identifier("  00123  ", strip=True) == "123"

    def test_whitespace_only_with_strip_is_none(self):
        """A whitespace-only reference becomes None when stripped."""
        assert parse_int_identifier("   ", strip=True) is None


class TestParseDigitsIdentifier:
    """Tests for the digits-only reference parser (Yahav-style)."""

    def test_digits_extracted_from_mixed_reference(self):
        """Non-digit characters are removed, keeping the digits in order."""
        assert parse_digits_identifier("ref-12a34") == "1234"

    def test_pure_digits_pass_through(self):
        """An all-digit reference is returned as-is."""
        assert parse_digits_identifier("987654") == "987654"

    def test_no_digits_is_none(self):
        """A reference without any digits yields None."""
        assert parse_digits_identifier("abc-def") is None

    def test_empty_or_none_is_none(self):
        """Empty string and None both yield None."""
        assert parse_digits_identifier("") is None
        assert parse_digits_identifier(None) is None


class TestConvertCreditDebitRows:
    """Tests for the shared scraped-row to Transaction converter."""

    def test_full_row_maps_all_fields(self):
        """A complete row maps date, amount, identifier, and description."""
        rows = [
            {
                "date": "15/03/2024",
                "description": "grocery store",
                "reference": "00777",
                "credit": "",
                "debit": "1,250.00",
                "status": TransactionStatus.PENDING,
            }
        ]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert len(result) == 1
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.status == TransactionStatus.PENDING
        assert txn.date == "2024-03-15T00:00:00"
        assert txn.processed_date == "2024-03-15T00:00:00"
        assert txn.original_amount == -1250.0
        assert txn.charged_amount == -1250.0
        assert txn.original_currency == "ILS"
        assert txn.description == "grocery store"
        assert txn.identifier == "777"
        assert txn.memo is None

    def test_status_defaults_to_completed(self):
        """A row with no status key defaults to COMPLETED."""
        rows = [{"date": "01/01/2024", "credit": "10", "debit": ""}]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert result[0].status == TransactionStatus.COMPLETED

    def test_unparseable_date_passes_through(self):
        """A date that doesn't match the format is kept verbatim."""
        rows = [{"date": "not-a-date", "credit": "10", "debit": ""}]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert result[0].date == "not-a-date"

    def test_skip_empty_date_drops_rows(self):
        """With skip_empty_date=True, rows without a date are dropped."""
        rows = [
            {"date": "", "credit": "10", "debit": ""},
            {"date": "01/01/2024", "credit": "10", "debit": ""},
        ]
        result = convert_credit_debit_rows(
            rows,
            date_format="%d/%m/%Y",
            parse_identifier=parse_int_identifier,
            skip_empty_date=True,
        )
        assert len(result) == 1
        assert result[0].date == "2024-01-01T00:00:00"

    def test_empty_date_kept_by_default(self):
        """Without skip_empty_date, rows with an empty date are still emitted."""
        rows = [{"date": "", "credit": "10", "debit": ""}]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert len(result) == 1
        assert result[0].date == ""

    def test_memo_empty_string_becomes_none(self):
        """An empty memo string is normalized to None."""
        rows = [{"date": "01/01/2024", "credit": "1", "debit": "", "memo": ""}]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert result[0].memo is None

    def test_memo_value_is_preserved(self):
        """A non-empty memo string is preserved on the transaction."""
        rows = [
            {"date": "01/01/2024", "credit": "1", "debit": "", "memo": "note"}
        ]
        result = convert_credit_debit_rows(
            rows, date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        )
        assert result[0].memo == "note"

    def test_strip_symbols_forwarded_to_amount_parsing(self):
        """Currency symbols in amount columns are stripped when configured."""
        rows = [{"date": "01/01/2024", "credit": "", "debit": "₪50"}]
        result = convert_credit_debit_rows(
            rows,
            date_format="%d/%m/%Y",
            parse_identifier=parse_int_identifier,
            strip_symbols=("₪",),
        )
        assert result[0].original_amount == -50.0

    def test_empty_input_yields_empty_list(self):
        """No rows in, no transactions out."""
        assert convert_credit_debit_rows(
            [], date_format="%d/%m/%Y", parse_identifier=parse_int_identifier
        ) == []


class TestFixInstallments:
    """Tests for installment date adjustment."""

    def test_later_installment_date_is_shifted(self):
        """Installment N has its date advanced by N-1 months."""
        txn = _make_txn(
            type=TransactionType.INSTALLMENTS,
            date="2024-01-10",
            installments=InstallmentInfo(number=3, total=6),
        )
        result = fix_installments([txn])
        assert result[0].date == "2024-03-10"

    def test_first_installment_untouched(self):
        """The first installment keeps its original date."""
        txn = _make_txn(
            type=TransactionType.INSTALLMENTS,
            date="2024-01-10",
            installments=InstallmentInfo(number=1, total=6),
        )
        result = fix_installments([txn])
        assert result[0].date == "2024-01-10"

    def test_normal_transaction_untouched(self):
        """Non-installment transactions are returned unchanged."""
        txn = _make_txn(date="2024-01-10")
        result = fix_installments([txn])
        assert result[0] is txn


class TestFilterOldTransactions:
    """Tests for the start-date transaction filter."""

    def test_old_transactions_dropped(self):
        """Transactions strictly before start_date are removed."""
        old = _make_txn(date="2024-01-01")
        new = _make_txn(date="2024-03-01")
        result = filter_old_transactions([old, new], date(2024, 2, 1))
        assert result == [new]

    def test_combine_installments_keeps_only_initial(self):
        """With combine_installments, later installments are dropped entirely."""
        later = _make_txn(
            type=TransactionType.INSTALLMENTS,
            date="2024-03-01",
            installments=InstallmentInfo(number=2, total=3),
        )
        initial = _make_txn(
            type=TransactionType.INSTALLMENTS,
            date="2024-03-01",
            installments=InstallmentInfo(number=1, total=3),
        )
        result = filter_old_transactions(
            [later, initial], date(2024, 1, 1), combine_installments=True
        )
        assert result == [initial]

    def test_sort_transactions_by_date_orders_ascending(self):
        """sort_transactions_by_date returns transactions oldest first."""
        a = _make_txn(date="2024-03-01")
        b = _make_txn(date="2024-01-01")
        assert sort_transactions_by_date([a, b]) == [b, a]


class TestWaitForFirst:
    """Tests for the first-completed awaitable race helper."""

    def test_returns_when_first_completes_and_cancels_rest(self):
        """The helper returns after the fastest awaitable; slower ones cancel."""

        async def run():
            state = {"slow_finished": False}

            async def fast():
                await asyncio.sleep(0.01)

            async def slow():
                await asyncio.sleep(5)
                state["slow_finished"] = True

            await wait_for_first(fast(), slow())
            # Give cancelled tasks a tick to unwind.
            await asyncio.sleep(0.01)
            return state["slow_finished"]

        assert asyncio.run(run()) is False

    def test_exception_in_first_completed_is_not_raised(self):
        """A failing awaitable (e.g. a timed-out wait) does not propagate."""

        async def run():
            async def failing():
                raise RuntimeError("element not found")

            async def slow():
                await asyncio.sleep(5)

            await wait_for_first(failing(), slow())
            return True

        assert asyncio.run(run()) is True
