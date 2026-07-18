"""Tests for the Discount Bank provider's pure parsing helpers."""

from scraper.models.result import LoginResult
from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.discount import (
    _convert_transactions,
    _create_login_fields,
    _get_possible_login_results,
)


def _raw_txn(**overrides) -> dict:
    """Build a realistic raw Discount API transaction dict."""
    raw = {
        "OperationDate": 20240301,
        "ValueDate": 20240302,
        "OperationAmount": -150.75,
        "OperationNumber": 456789,
        "OperationDescriptionToDisplay": "משיכת מזומן",
    }
    raw.update(overrides)
    return raw


class TestDiscountConvertTransactions:
    """Tests for the Discount raw-dict to Transaction converter."""

    def test_none_input_returns_empty_list(self):
        """A None transaction block converts to an empty list."""
        assert _convert_transactions(None, TransactionStatus.COMPLETED) == []

    def test_empty_input_returns_empty_list(self):
        """An empty list converts to an empty list."""
        assert _convert_transactions([], TransactionStatus.PENDING) == []

    def test_fields_are_mapped(self):
        """Dates, amount, identifier, and description map from the raw dict."""
        result = _convert_transactions(
            [_raw_txn()], TransactionStatus.COMPLETED
        )
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.date == "2024-03-01T00:00:00"
        assert txn.processed_date == "2024-03-02T00:00:00"
        assert txn.original_amount == -150.75
        assert txn.charged_amount == -150.75
        assert txn.original_currency == "ILS"
        assert txn.identifier == "456789"
        assert txn.description == "משיכת מזומן"

    def test_status_is_taken_from_argument(self):
        """The caller-provided status is stamped onto every transaction."""
        result = _convert_transactions(
            [_raw_txn()], TransactionStatus.PENDING
        )
        assert result[0].status == TransactionStatus.PENDING

    def test_unparseable_date_passes_through(self):
        """A malformed OperationDate is kept verbatim (stringified)."""
        result = _convert_transactions(
            [_raw_txn(OperationDate="01/03/2024")],
            TransactionStatus.COMPLETED,
        )
        assert result[0].date == "01/03/2024"

    def test_missing_operation_number_gives_none_identifier(self):
        """A missing OperationNumber leaves the identifier as None."""
        result = _convert_transactions(
            [_raw_txn(OperationNumber=None)], TransactionStatus.COMPLETED
        )
        assert result[0].identifier is None


class TestDiscountLoginConfig:
    """Tests for the Discount login detection rules and field builder."""

    def test_login_results_cover_expected_outcomes(self):
        """SUCCESS, INVALID_PASSWORD, and CHANGE_PASSWORD are all mapped."""
        results = _get_possible_login_results()
        assert set(results) == {
            LoginResult.SUCCESS,
            LoginResult.INVALID_PASSWORD,
            LoginResult.CHANGE_PASSWORD,
        }
        assert any(
            "MY_ACCOUNT_HOMEPAGE" in u for u in results[LoginResult.SUCCESS]
        )

    def test_login_fields_map_credentials(self):
        """The three Discount credentials map to their form selectors."""
        fields = _create_login_fields(
            {"id": "123", "password": "pw", "num": "9"}
        )
        assert {"selector": "#tzId", "value": "123"} in fields
        assert {"selector": "#tzPassword", "value": "pw"} in fields
        assert {"selector": "#aidnum", "value": "9"} in fields
