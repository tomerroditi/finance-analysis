"""Tests for the Bank Hapoalim provider's pure parsing helpers."""

import re

from scraper.models.result import LoginResult
from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.banks.hapoalim import (
    _convert_transactions,
    _get_possible_login_results,
)


def _raw_txn(**overrides) -> dict:
    """Build a realistic raw Hapoalim API transaction dict."""
    raw = {
        "eventActivityTypeCode": 2,
        "eventAmount": 250.5,
        "eventDate": 20240315,
        "valueDate": 20240316,
        "serialNumber": 7,
        "referenceNumber": 123456,
        "activityDescription": "העברה לאחר",
        "beneficiaryDetailsData": None,
    }
    raw.update(overrides)
    return raw


class TestHapoalimConvertTransactions:
    """Tests for the raw-dict to Transaction converter."""

    def test_outbound_amount_is_negated(self):
        """eventActivityTypeCode 2 (outbound) flips the amount negative."""
        result = _convert_transactions([_raw_txn()])
        assert result[0].original_amount == -250.5
        assert result[0].charged_amount == -250.5

    def test_inbound_amount_stays_positive(self):
        """A non-outbound activity code keeps the amount positive."""
        result = _convert_transactions(
            [_raw_txn(eventActivityTypeCode=1)]
        )
        assert result[0].original_amount == 250.5

    def test_dates_parsed_from_yyyymmdd(self):
        """eventDate/valueDate in YYYYMMDD form become ISO timestamps."""
        result = _convert_transactions([_raw_txn()])
        assert result[0].date == "2024-03-15T00:00:00"
        assert result[0].processed_date == "2024-03-16T00:00:00"

    def test_unparseable_date_row_is_dropped(self):
        """A malformed eventDate drops the row instead of passing raw text.

        The raw string landed in the DB date column, breaking date filters
        and sorts, and was later re-parsed month-first.
        """
        result = _convert_transactions([_raw_txn(eventDate="15/03/2024")])
        assert result == []

    def test_missing_value_date_falls_back_to_the_event_date(self):
        """An absent valueDate reuses the event date, not an empty string."""
        result = _convert_transactions([_raw_txn(valueDate="")])
        assert result[0].processed_date == result[0].date

    def test_serial_number_zero_marks_pending(self):
        """serialNumber 0 means the transaction is still pending."""
        result = _convert_transactions([_raw_txn(serialNumber=0)])
        assert result[0].status == TransactionStatus.PENDING

    def test_nonzero_serial_number_marks_completed(self):
        """Any non-zero serial number means the transaction completed."""
        result = _convert_transactions([_raw_txn(serialNumber=42)])
        assert result[0].status == TransactionStatus.COMPLETED

    def test_identifier_is_stringified_reference_number(self):
        """The referenceNumber is stringified into the identifier."""
        result = _convert_transactions([_raw_txn(referenceNumber=99887766)])
        assert result[0].identifier == "99887766"

    def test_missing_reference_number_gives_none_identifier(self):
        """A missing referenceNumber leaves the identifier as None."""
        result = _convert_transactions([_raw_txn(referenceNumber=None)])
        assert result[0].identifier is None

    def test_type_is_always_normal(self):
        """Bank account transactions are always NORMAL (no installments)."""
        result = _convert_transactions([_raw_txn()])
        assert result[0].type == TransactionType.NORMAL

    def test_currency_is_ils(self):
        """Hapoalim current-account transactions are shekel-denominated."""
        result = _convert_transactions([_raw_txn()])
        assert result[0].original_currency == "ILS"

    def test_memo_assembled_from_beneficiary_details(self):
        """Beneficiary details are joined into the memo in order."""
        beneficiary = {
            "partyHeadline": "מוטב",
            "partyName": "ישראל ישראלי",
            "messageHeadline": "הודעה",
            "messageDetail": "פרטים",
        }
        result = _convert_transactions(
            [_raw_txn(beneficiaryDetailsData=beneficiary)]
        )
        assert result[0].memo == "מוטב ישראל ישראלי. הודעה פרטים."

    def test_partial_beneficiary_details_skips_missing_parts(self):
        """Only present beneficiary fields end up in the memo."""
        beneficiary = {"partyName": "ישראל ישראלי"}
        result = _convert_transactions(
            [_raw_txn(beneficiaryDetailsData=beneficiary)]
        )
        assert result[0].memo == "ישראל ישראלי."

    def test_no_beneficiary_details_gives_none_memo(self):
        """Without beneficiary data the memo is None."""
        result = _convert_transactions([_raw_txn()])
        assert result[0].memo is None

    def test_empty_input_gives_empty_output(self):
        """No raw transactions yields an empty list."""
        assert _convert_transactions([]) == []


class TestHapoalimLoginResults:
    """Tests for the login result detection table."""

    def test_success_contains_homepage_urls(self):
        """The SUCCESS entry lists the known Hapoalim homepage URLs."""
        results = _get_possible_login_results()
        success = results[LoginResult.SUCCESS]
        assert any("HomePage" in str(u) for u in success)
        assert any("homepage" in str(u) for u in success)

    def test_change_password_matches_abouttoexpire_url(self):
        """The ABOUTTOEXPIRE regex flags password-expiry redirects."""
        results = _get_possible_login_results()
        patterns = results[LoginResult.CHANGE_PASSWORD]
        regexes = [p for p in patterns if isinstance(p, re.Pattern)]
        assert any(
            r.search("https://login.bankhapoalim.co.il/ABOUTTOEXPIRE/START")
            for r in regexes
        )

    def test_all_keys_are_login_results(self):
        """Every key in the mapping is a LoginResult member."""
        results = _get_possible_login_results()
        assert set(results) == {
            LoginResult.SUCCESS,
            LoginResult.INVALID_PASSWORD,
            LoginResult.CHANGE_PASSWORD,
        }
