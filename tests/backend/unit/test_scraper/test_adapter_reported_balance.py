"""Tests for which scraped balances the adapter hands to the bank balance."""

from backend.scraper.adapter import ScraperAdapter
from scraper.models.account import AccountResult
from scraper.models.result import ScrapingResult


def _result(*accounts: AccountResult) -> ScrapingResult:
    """A successful scrape of ``accounts``."""
    return ScrapingResult(success=True, accounts=list(accounts))


class TestReportedBankBalance:
    """Only a complete set of checking-account balances is used."""

    def test_checking_accounts_are_summed(self):
        """Two checking accounts under one login report one combined balance."""
        result = _result(
            AccountResult(account_number="1", balance=1000.5),
            AccountResult(account_number="2", balance=-200.25),
        )

        assert ScraperAdapter._reported_bank_balance(result) == 800.25

    def test_savings_deposits_are_left_out(self):
        """A deposit's balance is an investment, not bank cash."""
        result = _result(
            AccountResult(account_number="1", balance=1000.0),
            AccountResult(account_number="1-9", balance=50000.0, savings_account=True),
        )

        assert ScraperAdapter._reported_bank_balance(result) == 1000.0

    def test_a_missing_balance_means_none_is_used(self):
        """One account without a balance would make the sum look short."""
        result = _result(
            AccountResult(account_number="1", balance=1000.0),
            AccountResult(account_number="2"),
        )

        assert ScraperAdapter._reported_bank_balance(result) is None

    def test_no_accounts_means_none_is_used(self):
        """A scrape with nothing in it reports no balance."""
        assert ScraperAdapter._reported_bank_balance(_result()) is None
