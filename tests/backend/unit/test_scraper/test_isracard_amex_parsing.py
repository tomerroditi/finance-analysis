"""Tests for the Isracard/Amex base provider's pure parsing helpers."""

from datetime import date, datetime

from scraper.models.transaction import TransactionStatus, TransactionType
from scraper.providers.credit_cards.isracard_amex_base import (
    _convert_currency,
    _convert_transactions,
    _get_accounts_url,
    _get_installments_info,
    _get_transactions_url,
    _parse_date,
)

BILLING_DATE = "2024-04-02T00:00:00"


def _domestic_txn(**overrides) -> dict:
    """Build a realistic domestic (Israel) raw transaction dict."""
    txn = {
        "dealSumType": "0",
        "voucherNumberRatz": "00123456",
        "fullPurchaseDate": "15/03/2024",
        "fullPaymentDate": "02/04/2024",
        "dealSum": "100.50",
        "paymentSum": 100.50,
        "currencyId": 'ש"ח',
        "currentPaymentCurrency": None,
        "fullSupplierNameHeb": "סופר",
        "moreInfo": "",
    }
    txn.update(overrides)
    return txn


def _outbound_txn(**overrides) -> dict:
    """Build a realistic abroad (outbound) raw transaction dict."""
    txn = {
        "dealSumType": "0",
        "voucherNumberRatzOutbound": "00654321",
        "fullPurchaseDateOutbound": "20/03/2024",
        "fullPaymentDate": "02/04/2024",
        "dealSumOutbound": 50.0,
        "paymentSumOutbound": 185.0,
        "currencyId": "NIS",
        "currentPaymentCurrency": "USD",
        "fullSupplierNameOutbound": "AMAZON",
        "moreInfo": "",
    }
    txn.update(overrides)
    return txn


class TestConvertCurrency:
    """Tests for the Hebrew/alternative currency normalization."""

    def test_hebrew_shekel_maps_to_ils(self):
        """The Hebrew shekel keyword maps to ILS."""
        assert _convert_currency('ש"ח') == "ILS"

    def test_nis_maps_to_ils(self):
        """The NIS alias maps to ILS."""
        assert _convert_currency("NIS") == "ILS"

    def test_other_currency_passes_through(self):
        """Any other currency code passes through unchanged."""
        assert _convert_currency("USD") == "USD"


class TestParseDate:
    """Tests for the DD/MM/YYYY date parser."""

    def test_valid_date_parses(self):
        """A valid DD/MM/YYYY string parses to a datetime."""
        assert _parse_date("15/03/2024") == datetime(2024, 3, 15)

    def test_empty_string_gives_none(self):
        """An empty string yields None."""
        assert _parse_date("") is None

    def test_wrong_format_gives_none(self):
        """An ISO-formatted string does not match and yields None."""
        assert _parse_date("2024-03-15") is None


class TestGetInstallmentsInfo:
    """Tests for installment extraction from the moreInfo field."""

    def test_installments_keyword_with_numbers(self):
        """'תשלום N מתוך M' parses into InstallmentInfo(N, M)."""
        info = _get_installments_info({"moreInfo": "תשלום 2 מתוך 5"})
        assert info.number == 2
        assert info.total == 5

    def test_numbers_without_keyword_give_none(self):
        """Numbers without the installments keyword carry no info."""
        assert _get_installments_info({"moreInfo": "אישור 2 5"}) is None

    def test_empty_more_info_gives_none(self):
        """An empty moreInfo yields None."""
        assert _get_installments_info({"moreInfo": ""}) is None


class TestConvertTransactionsDomestic:
    """Tests for converting domestic (Israel) transactions."""

    def test_fields_are_mapped(self):
        """Dates, amounts, currency, identifier, and description map over."""
        result = _convert_transactions([_domestic_txn()], BILLING_DATE)
        assert len(result) == 1
        txn = result[0]
        assert txn.type == TransactionType.NORMAL
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.date == "2024-03-15T00:00:00"
        assert txn.processed_date == "2024-04-02T00:00:00"
        assert txn.original_amount == -100.50
        assert txn.charged_amount == -100.50
        assert txn.original_currency == "ILS"
        assert txn.charged_currency == "ILS"
        assert txn.description == "סופר"
        assert txn.identifier == "123456"

    def test_missing_payment_date_uses_billing_default(self):
        """Without fullPaymentDate the caller's billing date is used."""
        result = _convert_transactions(
            [_domestic_txn(fullPaymentDate="")], BILLING_DATE
        )
        assert result[0].processed_date == BILLING_DATE

    def test_summary_rows_are_filtered(self):
        """dealSumType '1' rows (summaries) are skipped."""
        result = _convert_transactions(
            [_domestic_txn(dealSumType="1")], BILLING_DATE
        )
        assert result == []

    def test_zero_voucher_rows_are_filtered(self):
        """Rows with the all-zero voucher number are skipped."""
        result = _convert_transactions(
            [_domestic_txn(voucherNumberRatz="000000000")], BILLING_DATE
        )
        assert result == []

    def test_unparseable_purchase_date_skips_row(self):
        """A row whose purchase date cannot parse is dropped."""
        result = _convert_transactions(
            [_domestic_txn(fullPurchaseDate="bad")], BILLING_DATE
        )
        assert result == []

    def test_installments_set_type_and_info(self):
        """An installments moreInfo marks the transaction INSTALLMENTS."""
        result = _convert_transactions(
            [_domestic_txn(moreInfo="תשלום 1 מתוך 3")], BILLING_DATE
        )
        assert result[0].type == TransactionType.INSTALLMENTS
        assert result[0].installments.number == 1
        assert result[0].installments.total == 3
        assert result[0].memo == "תשלום 1 מתוך 3"


class TestConvertTransactionsOutbound:
    """Tests for converting abroad (outbound) transactions."""

    def test_outbound_fields_are_mapped(self):
        """Outbound rows read the *Outbound field variants."""
        result = _convert_transactions([_outbound_txn()], BILLING_DATE)
        assert len(result) == 1
        txn = result[0]
        assert txn.date == "2024-03-20T00:00:00"
        assert txn.original_amount == -50.0
        assert txn.charged_amount == -185.0
        assert txn.original_currency == "USD"
        assert txn.charged_currency == "ILS"
        assert txn.description == "AMAZON"
        assert txn.identifier == "654321"


class TestUrlBuilders:
    """Tests for the services URL builders."""

    def test_accounts_url_contains_billing_date(self):
        """The DashboardMonth URL embeds the ISO billing date."""
        url = _get_accounts_url("https://x/services", date(2024, 3, 1))
        assert "reqName=DashboardMonth" in url
        assert "billingDate=2024-03-01" in url

    def test_transactions_url_contains_zero_padded_month(self):
        """The CardsTransactionsList URL zero-pads the month."""
        url = _get_transactions_url("https://x/services", date(2024, 3, 1))
        assert "reqName=CardsTransactionsList" in url
        assert "month=03" in url
        assert "year=2024" in url
