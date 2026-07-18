"""Tests for the Max credit card provider's pure parsing helpers."""

import pytest

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.credit_cards import max as max_module
from scraper.providers.credit_cards.max import (
    _get_charged_currency,
    _get_installments_info,
    _get_memo,
    _get_transaction_type,
    _map_transaction,
)


@pytest.fixture(autouse=True)
def clear_categories_cache():
    """Keep the module-level category cache empty between tests."""
    max_module._categories.clear()
    yield
    max_module._categories.clear()


def _raw_txn(**overrides) -> dict:
    """Build a realistic raw Max API transaction dict."""
    raw = {
        "planName": "רגילה",
        "planTypeId": 5,
        "purchaseDate": "2024-03-15T10:00:00Z",
        "paymentDate": "2024-04-02T10:00:00Z",
        "originalAmount": 120.5,
        "originalCurrency": "ILS",
        "actualPaymentAmount": 120.5,
        "paymentCurrency": 376,
        "merchantName": " שופרסל ",
        "comments": "",
        "categoryId": 7,
        "dealData": {"arn": "ARN123"},
    }
    raw.update(overrides)
    return raw


class TestGetTransactionType:
    """Tests for plan-name / plan-type transaction classification."""

    def test_known_normal_plan_name(self):
        """A known normal plan name maps to NORMAL."""
        assert _get_transaction_type("רגילה", 0) == TransactionType.NORMAL

    def test_known_installments_plan_name(self):
        """A known installments plan name maps to INSTALLMENTS."""
        assert (
            _get_transaction_type("תשלומים", 0)
            == TransactionType.INSTALLMENTS
        )

    def test_plan_name_whitespace_and_tabs_cleaned(self):
        """Tabs and surrounding whitespace are stripped before lookup."""
        assert _get_transaction_type("\tקרדיט ", 0) == TransactionType.INSTALLMENTS

    def test_unknown_name_falls_back_to_plan_type_id(self):
        """Unknown plan names classify via the numeric plan type."""
        assert _get_transaction_type("חדש", 2) == TransactionType.INSTALLMENTS
        assert _get_transaction_type("חדש", 3) == TransactionType.INSTALLMENTS
        assert _get_transaction_type("חדש", 5) == TransactionType.NORMAL

    def test_unknown_name_and_type_raises(self):
        """A fully unknown plan name/type combination raises ValueError."""
        with pytest.raises(ValueError, match="Unknown transaction type"):
            _get_transaction_type("מסלול עלום", 42)


class TestGetInstallmentsInfo:
    """Tests for installment parsing from the comments field."""

    def test_two_numbers_parse_into_installments(self):
        """'payment N of M' comments yield an InstallmentInfo(N, M)."""
        info = _get_installments_info("תשלום 3 מתוך 12")
        assert info.number == 3
        assert info.total == 12

    def test_empty_comments_gives_none(self):
        """Empty comments carry no installment info."""
        assert _get_installments_info("") is None

    def test_single_number_gives_none(self):
        """A comment with fewer than two numbers carries no installments."""
        assert _get_installments_info("תשלום 3") is None


class TestGetChargedCurrency:
    """Tests for the numeric currency-code mapping."""

    def test_known_codes_map_to_iso(self):
        """376/840/978 map to ILS/USD/EUR."""
        assert _get_charged_currency(376) == "ILS"
        assert _get_charged_currency(840) == "USD"
        assert _get_charged_currency(978) == "EUR"

    def test_unknown_code_gives_none(self):
        """Unknown or missing codes map to None."""
        assert _get_charged_currency(999) is None
        assert _get_charged_currency(None) is None


class TestGetMemo:
    """Tests for memo composition from comment/transfer fields."""

    def test_comments_only(self):
        """Plain comments are returned as the memo."""
        assert _get_memo("הערה") == "הערה"

    def test_empty_comments_gives_none(self):
        """No comments and no transfer data yields None."""
        assert _get_memo("") is None

    def test_receiver_appended_to_comments(self):
        """A funds-transfer receiver is appended after the comments."""
        assert _get_memo("הערה", "ישראל") == "הערה ישראל"

    def test_receiver_and_transfer_comment(self):
        """A transfer comment is appended after a colon."""
        assert _get_memo("", "ישראל", "תודה") == "ישראל: תודה"


class TestMapTransaction:
    """Tests for the full raw-dict to Transaction mapping."""

    def test_amounts_are_negated(self):
        """Charge amounts flip negative (expense convention)."""
        txn = _map_transaction(_raw_txn())
        assert txn.original_amount == -120.5
        assert txn.charged_amount == -120.5

    def test_completed_when_payment_date_present(self):
        """A transaction with a payment date is COMPLETED."""
        txn = _map_transaction(_raw_txn())
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.date == "2024-03-15"
        assert txn.processed_date == "2024-04-02"

    def test_pending_when_payment_date_missing(self):
        """A missing payment date marks the transaction PENDING."""
        txn = _map_transaction(_raw_txn(paymentDate=None))
        assert txn.status == TransactionStatus.PENDING
        assert txn.processed_date == "2024-03-15"

    def test_description_is_stripped_merchant_name(self):
        """The merchant name is whitespace-stripped into the description."""
        txn = _map_transaction(_raw_txn())
        assert txn.description == "שופרסל"

    def test_identifier_is_arn_without_installments(self):
        """Without installments the identifier is the bare ARN."""
        txn = _map_transaction(_raw_txn())
        assert txn.identifier == "ARN123"

    def test_identifier_includes_installment_number(self):
        """With installments the identifier is ARN_installmentNumber."""
        txn = _map_transaction(
            _raw_txn(planName="תשלומים", comments="תשלום 2 מתוך 6")
        )
        assert txn.identifier == "ARN123_2"
        assert txn.installments.number == 2
        assert txn.installments.total == 6
        assert txn.type == TransactionType.INSTALLMENTS

    def test_missing_deal_data_gives_none_identifier(self):
        """Without dealData there is no ARN, so identifier is None."""
        txn = _map_transaction(_raw_txn(dealData=None))
        assert txn.identifier is None

    def test_charged_currency_mapped_from_numeric_code(self):
        """The numeric payment currency maps to an ISO code."""
        txn = _map_transaction(_raw_txn(paymentCurrency=840))
        assert txn.charged_currency == "USD"

    def test_category_resolved_from_cache(self):
        """The category id resolves through the module category cache."""
        max_module._categories[7] = "מזון"
        txn = _map_transaction(_raw_txn())
        assert txn.category == "מזון"

    def test_unknown_category_gives_none(self):
        """An id absent from the cache leaves the category as None."""
        txn = _map_transaction(_raw_txn())
        assert txn.category is None
