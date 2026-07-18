"""Tests for the Bank Leumi provider's pure parsing helpers."""

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.leumi import (
    _extract_transactions_from_page,
    _remove_special_characters,
)


def _raw_txn(**overrides) -> dict:
    """Build a realistic raw Leumi transaction dict."""
    raw = {
        "DateUTC": "2024-03-15T10:00:00Z",
        "Amount": -320.4,
        "Description": "שופרסל",
        "ReferenceNumberLong": "12345678901",
        "AdditionalData": "הערה",
    }
    raw.update(overrides)
    return raw


class TestLeumiExtractTransactions:
    """Tests for the Leumi raw-response to Transaction converter."""

    def test_none_input_returns_empty_list(self):
        """A missing transaction block converts to an empty list."""
        assert _extract_transactions_from_page(
            None, TransactionStatus.COMPLETED
        ) == []

    def test_empty_input_returns_empty_list(self):
        """An empty transaction list converts to an empty list."""
        assert _extract_transactions_from_page(
            [], TransactionStatus.PENDING
        ) == []

    def test_fields_are_mapped(self):
        """Amount, description, identifier, and memo map from the raw dict."""
        result = _extract_transactions_from_page(
            [_raw_txn()], TransactionStatus.COMPLETED
        )
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.original_amount == -320.4
        assert txn.charged_amount == -320.4
        assert txn.original_currency == "ILS"
        assert txn.description == "שופרסל"
        assert txn.identifier == "12345678901"
        assert txn.memo == "הערה"

    def test_status_is_taken_from_argument(self):
        """The caller-provided status is stamped onto every transaction."""
        result = _extract_transactions_from_page(
            [_raw_txn()], TransactionStatus.PENDING
        )
        assert result[0].status == TransactionStatus.PENDING

    def test_utc_date_converted_to_israel_local_date(self):
        """The UTC timestamp becomes an Israel-local YYYY-MM-DD string."""
        result = _extract_transactions_from_page(
            [_raw_txn(DateUTC="2024-03-15T10:00:00Z")],
            TransactionStatus.COMPLETED,
        )
        assert result[0].date == "2024-03-15"
        assert result[0].processed_date == "2024-03-15"

    def test_late_night_utc_rolls_to_next_israel_day(self):
        """A UTC time near midnight lands on the next day in Israel time."""
        result = _extract_transactions_from_page(
            [_raw_txn(DateUTC="2024-03-15T22:30:00Z")],
            TransactionStatus.COMPLETED,
        )
        assert result[0].date == "2024-03-16"

    def test_empty_additional_data_becomes_none_memo(self):
        """An empty AdditionalData string is normalized to None."""
        result = _extract_transactions_from_page(
            [_raw_txn(AdditionalData="")], TransactionStatus.COMPLETED
        )
        assert result[0].memo is None

    def test_missing_amount_defaults_to_zero(self):
        """A transaction without an Amount field defaults to 0."""
        raw = _raw_txn()
        del raw["Amount"]
        result = _extract_transactions_from_page(
            [raw], TransactionStatus.COMPLETED
        )
        assert result[0].original_amount == 0


class TestRemoveSpecialCharacters:
    """Tests for the account-number sanitizer."""

    def test_keeps_digits_dash_and_slash(self):
        """Digits, dashes, and slashes survive; everything else is removed."""
        assert _remove_special_characters("12-345/67 ab•") == "12-345/67"

    def test_empty_string_stays_empty(self):
        """An empty input stays empty."""
        assert _remove_special_characters("") == ""
