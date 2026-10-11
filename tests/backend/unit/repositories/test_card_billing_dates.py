"""Tests for keeping each card purchase's billing date as scrapes report it."""

from datetime import date
from types import SimpleNamespace

import pandas as pd

from backend.models.transaction import CreditCardTransaction
from backend.repositories.transactions import TransactionsRepository
from backend.scraper.adapter import ScraperAdapter


def _scraped(rows: list[dict]) -> pd.DataFrame:
    """Scraped card rows, with defaults for what a test does not care about."""
    base = {
        "id": "p-1",
        "date": "2026-08-20",
        "provider": "isracard",
        "account_name": "Card",
        "account_number": "1234",
        "description": "shop",
        "amount": -100.0,
        "category": None,
        "tag": None,
        "source": "credit_card_transactions",
        "type": "normal",
        "status": "completed",
        "billing_date": "2026-09-02",
    }
    return pd.DataFrame([{**base, **row} for row in rows])


class TestScrapedCardRowsKeepTheirBillingDate:
    """A scrape stores the charge day and fills it on rows it sees again."""

    def test_a_new_row_is_stored_with_it(self, db_session):
        """The billing date is written with the row."""
        TransactionsRepository(db_session).add_scraped_transactions(
            _scraped([{}]), "credit_card_transactions"
        )

        row = db_session.query(CreditCardTransaction).one()
        assert row.billing_date == "2026-09-02"

    def test_an_old_row_gets_it_when_scraped_again(self, db_session):
        """A row stored before the column existed is filled, not duplicated."""
        repo = TransactionsRepository(db_session)
        repo.add_scraped_transactions(
            _scraped([{"billing_date": None}]), "credit_card_transactions"
        )

        repo.add_scraped_transactions(_scraped([{}]), "credit_card_transactions")

        rows = db_session.query(CreditCardTransaction).all()
        assert [r.billing_date for r in rows] == ["2026-09-02"]

    def test_a_stored_billing_date_is_left_alone(self, db_session):
        """Only missing dates are filled."""
        repo = TransactionsRepository(db_session)
        repo.add_scraped_transactions(_scraped([{}]), "credit_card_transactions")

        repo.add_scraped_transactions(
            _scraped([{"billing_date": "2026-10-02"}]), "credit_card_transactions"
        )

        row = db_session.query(CreditCardTransaction).one()
        assert row.billing_date == "2026-09-02"


class TestAdapterReadsTheBillingDate:
    """The adapter carries the card's processed date into the billing date."""

    def test_card_rows_carry_the_processed_date(self):
        """The date part of the provider's processed date is kept."""
        adapter = ScraperAdapter(
            "credit_cards", "isracard", "Card", {}, date(2026, 8, 1), 1
        )
        txn = SimpleNamespace(
            date="2026-08-20",
            processed_date="2026-09-02T00:00:00",
            charged_amount=-100.0,
            description="shop",
            identifier="abc",
            type=SimpleNamespace(value="normal"),
            status=SimpleNamespace(value="completed"),
        )
        result = SimpleNamespace(
            accounts=[SimpleNamespace(account_number="1234", transactions=[txn])]
        )

        df = adapter._result_to_dataframe(result, "credit_cards")

        assert df["billing_date"].tolist() == ["2026-09-02"]

    def test_bank_rows_have_none(self):
        """Banks report no billing date."""
        adapter = ScraperAdapter("banks", "hapoalim", "Main", {}, date(2026, 8, 1), 1)
        txn = SimpleNamespace(
            date="2026-08-20",
            processed_date="2026-08-20",
            charged_amount=-100.0,
            description="shop",
            identifier="abc",
            type=SimpleNamespace(value="normal"),
            status=SimpleNamespace(value="completed"),
        )
        result = SimpleNamespace(
            accounts=[SimpleNamespace(account_number="1234", transactions=[txn])]
        )

        df = adapter._result_to_dataframe(result, "banks")

        assert "billing_date" not in df.columns
