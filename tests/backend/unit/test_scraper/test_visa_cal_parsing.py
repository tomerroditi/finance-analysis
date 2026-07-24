"""Tests for the Visa Cal provider's pure parsing helpers."""

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.credit_cards.visa_cal import (
    _convert_parsed_data_to_transactions,
    _is_pending,
)


def _completed_txn(**overrides) -> dict:
    """Build a realistic completed (debited) Visa Cal transaction dict."""
    txn = {
        "trnTypeCode": "5",
        "trnPurchaseDate": "2024-03-10T12:00:00Z",
        "debCrdDate": "2024-04-02T12:00:00Z",
        "trnAmt": 200.0,
        "amtBeforeConvAndIndex": 200.0,
        "trnCurrencySymbol": "ILS",
        "debCrdCurrencySymbol": "ILS",
        "numOfPayments": 0,
        "curPaymentNum": 0,
        "merchantName": "רמי לוי",
        "transTypeCommentDetails": "",
        "branchCodeDesc": "מזון",
        "trnIntId": "ABC123",
    }
    txn.update(overrides)
    return txn


def _month_data(transactions: list[dict]) -> dict:
    """Wrap raw transactions in the monthly API response envelope."""
    return {
        "result": {
            "bankAccounts": [
                {
                    "debitDates": [{"transactions": transactions}],
                    "immidiateDebits": {"debitDays": []},
                }
            ]
        }
    }


def _pending_data(transactions: list[dict]) -> dict:
    """Wrap raw pending transactions in the clearance-requests envelope."""
    return {"result": {"cardsList": [{"authDetalisList": transactions}]}}


class TestIsPending:
    """Tests for pending detection."""

    def test_missing_debit_date_is_pending(self):
        """A transaction without debCrdDate is pending."""
        assert _is_pending({"trnAmt": 10}) is True

    def test_debit_date_present_is_completed(self):
        """A transaction carrying debCrdDate is not pending."""
        assert _is_pending({"debCrdDate": "2024-04-02T12:00:00Z"}) is False


class TestConvertCompletedTransactions:
    """Tests for converting debited (completed) transactions."""

    def test_regular_transaction_fields(self):
        """A regular (type 5) charge maps all fields with negative amounts."""
        result = _convert_parsed_data_to_transactions(
            [_month_data([_completed_txn()])]
        )
        assert len(result) == 1
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.date == "2024-03-10"
        assert txn.processed_date == "2024-04-02"
        assert txn.original_amount == -200.0
        assert txn.charged_amount == -200.0
        assert txn.original_currency == "ILS"
        assert txn.charged_currency == "ILS"
        assert txn.description == "רמי לוי"
        assert txn.category == "מזון"
        assert txn.identifier == "ABC123"
        assert txn.installments is None

    def test_standing_order_is_normal_type(self):
        """Standing orders (type 9) are NORMAL, not installments."""
        result = _convert_parsed_data_to_transactions(
            [_month_data([_completed_txn(trnTypeCode="9")])]
        )
        assert result[0].type == TransactionType.NORMAL

    def test_credit_transaction_keeps_positive_amounts(self):
        """A credit (type 6) is a refund — both amounts stay positive.

        ``charged_amount`` is the field the backend persists, so negating it
        recorded every merchant refund as an expense of the same size.
        """
        result = _convert_parsed_data_to_transactions(
            [_month_data([_completed_txn(trnTypeCode="6")])]
        )
        assert result[0].original_amount == 200.0
        assert result[0].charged_amount == 200.0

    def test_credit_transaction_is_typed_normal(self):
        """A credit is a standalone refund, not an installment plan.

        Typing it as INSTALLMENTS made ``filter_old_transactions`` drop it
        when combining installments, because credits carry no payment count.
        """
        result = _convert_parsed_data_to_transactions(
            [_month_data([_completed_txn(trnTypeCode="6")])]
        )
        assert result[0].type == TransactionType.NORMAL

    def test_credit_survives_installment_combining(self):
        """A refund is not filtered out when installments are combined."""
        from datetime import date

        from scraper.utils.transactions import filter_old_transactions

        result = _convert_parsed_data_to_transactions(
            [_month_data([_completed_txn(trnTypeCode="6")])]
        )
        kept = filter_old_transactions(
            result, date(2020, 1, 1), combine_installments=True
        )
        assert len(kept) == 1

    def test_string_amounts_are_coerced(self):
        """Amounts sent as strings parse to numbers, not empty strings.

        Multiplying a string by -1 is Python string-repetition, which
        silently produced ``''`` instead of raising.
        """
        result = _convert_parsed_data_to_transactions(
            [
                _month_data(
                    [
                        _completed_txn(
                            trnAmt="1,100.50",
                            amtBeforeConvAndIndex="1,100.50",
                        )
                    ]
                )
            ]
        )
        assert result[0].charged_amount == -1100.50
        assert result[0].original_amount == -1100.50

    def test_installments_shift_date_and_set_info(self):
        """Installment N shifts the purchase date N-1 months forward."""
        result = _convert_parsed_data_to_transactions(
            [
                _month_data(
                    [
                        _completed_txn(
                            trnTypeCode="8",
                            numOfPayments=3,
                            curPaymentNum=2,
                        )
                    ]
                )
            ]
        )
        txn = result[0]
        assert txn.type == TransactionType.INSTALLMENTS
        assert txn.installments.number == 2
        assert txn.installments.total == 3
        assert txn.date == "2024-04-10"

    def test_immediate_debits_are_collected(self):
        """Transactions under immidiateDebits/debitDays are converted too."""
        month = {
            "result": {
                "bankAccounts": [
                    {
                        "debitDates": [],
                        "immidiateDebits": {
                            "debitDays": [
                                {"transactions": [_completed_txn()]}
                            ]
                        },
                    }
                ]
            }
        }
        result = _convert_parsed_data_to_transactions([month])
        assert len(result) == 1


class TestConvertPendingTransactions:
    """Tests for converting pending (not-yet-debited) transactions."""

    def test_pending_transaction_fields(self):
        """A pending auth maps to a PENDING transaction with no identifier."""
        pending = {
            "trnTypeCode": "5",
            "trnPurchaseDate": "2024-03-20T12:00:00Z",
            "trnAmt": 50.0,
            "trnCurrencySymbol": "ILS",
            "numberOfPayments": 0,
            "merchantName": "בית קפה",
        }
        result = _convert_parsed_data_to_transactions(
            [], pending_data=_pending_data([pending])
        )
        assert len(result) == 1
        txn = result[0]
        assert txn.status == TransactionStatus.PENDING
        assert txn.charged_amount == -50.0
        assert txn.original_amount == -50.0
        assert txn.date == "2024-03-20"
        assert txn.processed_date == "2024-03-20"
        assert txn.identifier is None
        assert txn.charged_currency is None

    def test_pending_installments_start_at_one(self):
        """Pending installment auths always report installment number 1."""
        pending = {
            "trnTypeCode": "8",
            "trnPurchaseDate": "2024-03-20T12:00:00Z",
            "trnAmt": 90.0,
            "numberOfPayments": 3,
            "merchantName": "חנות",
        }
        result = _convert_parsed_data_to_transactions(
            [], pending_data=_pending_data([pending])
        )
        assert result[0].installments.number == 1
        assert result[0].installments.total == 3

    def test_no_data_yields_empty_list(self):
        """Empty month data and no pending data produce no transactions."""
        assert _convert_parsed_data_to_transactions([]) == []
