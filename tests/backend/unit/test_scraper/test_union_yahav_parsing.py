"""Tests for the Union Bank and Yahav providers' transaction converters.

Both providers route through the shared ``convert_credit_debit_rows``
helper; these tests pin each provider's specific configuration (date
format, identifier normalization, empty-date handling).
"""

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.union import (
    _convert_transactions as union_convert,
)
from scraper.providers.banks.yahav import (
    _convert_transactions as yahav_convert,
)


class TestUnionConvertTransactions:
    """Tests for the Union Bank scraped-row converter."""

    def test_two_digit_year_date_format(self):
        """Union dates use DD/MM/YY and convert to ISO timestamps."""
        result = union_convert(
            [
                {
                    "date": "15/03/24",
                    "description": "הפקדה",
                    "reference": "00987",
                    "credit": "1,500.00",
                    "debit": "",
                    "status": TransactionStatus.COMPLETED,
                    "memo": "",
                }
            ]
        )
        txn = result[0]
        assert txn.date == "2024-03-15T00:00:00"
        assert txn.original_amount == 1500.0
        assert txn.identifier == "987"
        assert txn.memo is None
        assert txn.type == TransactionType.NORMAL

    def test_debit_yields_negative_amount(self):
        """A debit-only row yields a negative amount."""
        result = union_convert(
            [{"date": "01/01/24", "credit": "", "debit": "300"}]
        )
        assert result[0].original_amount == -300.0

    def test_empty_date_row_is_kept_verbatim(self):
        """Union does not skip rows with an empty date column."""
        result = union_convert([{"date": "", "credit": "5", "debit": ""}])
        assert len(result) == 1
        assert result[0].date == ""

    def test_non_numeric_reference_passes_through(self):
        """A non-numeric reference is kept unchanged as the identifier."""
        result = union_convert(
            [{"date": "01/01/24", "reference": "אס-1א", "credit": "1", "debit": ""}]
        )
        assert result[0].identifier == "אס-1א"

    def test_pending_status_preserved(self):
        """The status set by the table extractor survives conversion."""
        result = union_convert(
            [
                {
                    "date": "01/01/24",
                    "credit": "1",
                    "debit": "",
                    "status": TransactionStatus.PENDING,
                }
            ]
        )
        assert result[0].status == TransactionStatus.PENDING


class TestYahavConvertTransactions:
    """Tests for the Yahav scraped-row converter."""

    def test_four_digit_year_date_format(self):
        """Yahav dates use DD/MM/YYYY and convert to ISO timestamps."""
        result = yahav_convert(
            [
                {
                    "date": "15/03/2024",
                    "reference": "אס: 445-66",
                    "description": "משכורת",
                    "debit": "",
                    "credit": "9,000.00",
                    "memo": "",
                    "status": TransactionStatus.COMPLETED,
                }
            ]
        )
        txn = result[0]
        assert txn.date == "2024-03-15T00:00:00"
        assert txn.original_amount == 9000.0
        assert txn.description == "משכורת"

    def test_identifier_keeps_digits_only(self):
        """Yahav references strip all non-digit characters."""
        result = yahav_convert(
            [
                {
                    "date": "15/03/2024",
                    "reference": "אס: 445-66",
                    "debit": "",
                    "credit": "1",
                }
            ]
        )
        assert result[0].identifier == "44566"

    def test_reference_without_digits_gives_none(self):
        """A reference with no digits yields identifier None."""
        result = yahav_convert(
            [{"date": "15/03/2024", "reference": "אין", "debit": "1", "credit": ""}]
        )
        assert result[0].identifier is None

    def test_debit_yields_negative_amount(self):
        """A debit-only row yields a negative amount."""
        result = yahav_convert(
            [{"date": "15/03/2024", "debit": "2,500.75", "credit": ""}]
        )
        assert result[0].original_amount == -2500.75

    def test_bad_date_passes_through(self):
        """A malformed date string is kept verbatim."""
        result = yahav_convert(
            [{"date": "15/03/24", "debit": "1", "credit": ""}]
        )
        # Two-digit year does not match Yahav's DD/MM/YYYY format.
        assert result[0].date == "15/03/24"
