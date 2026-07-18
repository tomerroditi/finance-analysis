"""Tests for the Beinleumi group base provider's pure parsing helpers."""

from scraper.models.result import LoginResult
from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.beinleumi_group import (
    _convert_transactions,
    _create_login_fields,
    _extract_transaction_details,
    _get_possible_login_results,
)

COMPLETED_COLS = {
    "date first": 0,
    "reference wrap_normal": 1,
    "details": 2,
    "debit": 3,
    "credit": 4,
}
PENDING_COLS = {
    "first date": 0,
    "details wrap_normal": 1,
    "details": 2,
    "debit": 3,
    "credit": 4,
}


def _row(**overrides) -> dict:
    """Build a scraped Beinleumi transaction row dict."""
    row = {
        "date": "15/03/2024",
        "description": "העברה",
        "reference": "00123",
        "debit": "₪1,000.00",
        "credit": "",
        "status": TransactionStatus.COMPLETED,
    }
    row.update(overrides)
    return row


class TestBeinleumiConvertTransactions:
    """Tests for the scraped-row to Transaction converter."""

    def test_debit_with_shekel_symbol_and_commas(self):
        """Shekel symbol and thousands separators parse into a negative amount."""
        result = _convert_transactions([_row()])
        txn = result[0]
        assert txn.original_amount == -1000.0
        assert txn.charged_amount == -1000.0
        assert txn.original_currency == "ILS"

    def test_credit_yields_positive_amount(self):
        """A credit column value yields a positive amount."""
        result = _convert_transactions(
            [_row(debit="", credit="₪250.50")]
        )
        assert result[0].original_amount == 250.5

    def test_date_parsed_to_iso(self):
        """The DD/MM/YYYY date column becomes an ISO timestamp."""
        result = _convert_transactions([_row()])
        assert result[0].date == "2024-03-15T00:00:00"
        assert result[0].processed_date == "2024-03-15T00:00:00"

    def test_rows_without_date_are_skipped(self):
        """Rows with an empty date column are dropped entirely."""
        result = _convert_transactions([_row(date="")])
        assert result == []

    def test_identifier_normalized_through_int(self):
        """Numeric references drop their leading zeros."""
        result = _convert_transactions([_row(reference="00123")])
        assert result[0].identifier == "123"

    def test_identifier_whitespace_stripped(self):
        """Padded references are stripped before normalization."""
        result = _convert_transactions([_row(reference="  456  ")])
        assert result[0].identifier == "456"

    def test_non_numeric_identifier_passes_through(self):
        """Non-numeric references are kept as-is."""
        result = _convert_transactions([_row(reference="ref-9")])
        assert result[0].identifier == "ref-9"

    def test_empty_reference_gives_none_identifier(self):
        """An empty reference yields identifier None."""
        result = _convert_transactions([_row(reference="")])
        assert result[0].identifier is None

    def test_status_defaults_to_completed(self):
        """A row without a status key defaults to COMPLETED."""
        row = _row()
        del row["status"]
        result = _convert_transactions([row])
        assert result[0].status == TransactionStatus.COMPLETED

    def test_pending_status_preserved(self):
        """A PENDING row status is carried onto the transaction."""
        result = _convert_transactions(
            [_row(status=TransactionStatus.PENDING)]
        )
        assert result[0].status == TransactionStatus.PENDING

    def test_type_is_normal(self):
        """Bank rows always convert to NORMAL transactions."""
        result = _convert_transactions([_row()])
        assert result[0].type == TransactionType.NORMAL


class TestExtractTransactionDetails:
    """Tests for mapping a table row's cells into a raw transaction dict."""

    def test_completed_row_uses_completed_columns(self):
        """Completed rows read the completed date/description classes."""
        inner_tds = ["15/03/2024 ", " תיאור ", " 123 ", " 50 ", ""]
        details = _extract_transaction_details(
            inner_tds, TransactionStatus.COMPLETED, COMPLETED_COLS
        )
        assert details == {
            "status": TransactionStatus.COMPLETED,
            "date": "15/03/2024",
            "description": "תיאור",
            "reference": "123",
            "debit": "50",
            "credit": "",
        }

    def test_pending_row_uses_pending_columns(self):
        """Pending rows read the pending date/description classes."""
        inner_tds = ["16/03/2024", "ממתין", "9", "", "75"]
        details = _extract_transaction_details(
            inner_tds, TransactionStatus.PENDING, PENDING_COLS
        )
        assert details["date"] == "16/03/2024"
        assert details["description"] == "ממתין"
        assert details["credit"] == "75"

    def test_missing_columns_give_empty_strings(self):
        """Columns absent from the mapping produce empty string fields."""
        details = _extract_transaction_details(
            ["01/01/2024"], TransactionStatus.COMPLETED, {"date first": 0}
        )
        assert details["description"] == ""
        assert details["reference"] == ""
        assert details["debit"] == ""
        assert details["credit"] == ""


class TestBeinleumiLoginConfig:
    """Tests for the Beinleumi group login detection rules."""

    def test_success_pattern_matches_online_menu_url(self):
        """The FibiMenu/Online regex flags a logged-in URL."""
        results = _get_possible_login_results()
        url = (
            "https://online.fibi.co.il/wps/myportal/FibiMenu/Online"
            "/OnAccountMngment"
        )
        assert any(p.search(url) for p in results[LoginResult.SUCCESS])

    def test_invalid_password_pattern_matches_marketing_home(self):
        """The marketing home regex flags a bounced login."""
        results = _get_possible_login_results()
        url = "https://online.fibi.co.il/FibiMenu/Marketing/Private/Home"
        assert any(
            p.search(url) for p in results[LoginResult.INVALID_PASSWORD]
        )

    def test_login_fields_map_credentials(self):
        """Username and password map to their form selectors."""
        fields = _create_login_fields({"username": "u", "password": "p"})
        assert {"selector": "#username", "value": "u"} in fields
        assert {"selector": "#password", "value": "p"} in fields
