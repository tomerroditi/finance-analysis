"""Tests for the adapter's dedup-key construction and final-status decision.

Two independent money-visible behaviours live here:

* ``_result_to_dataframe`` builds the ``id`` column that
  ``TransactionsRepository.add_scraped_transactions`` dedups on
  ``(id, provider, date, amount)``. Two distinct same-day/same-amount rows
  that share a key are permanently dropped on the next overlapping
  re-scrape.
* ``_record_scraping_attempt`` decides SUCCESS vs FAILED. Several providers
  swallow per-request errors (``ignore_errors=True``), so an expired session
  can yield zero accounts — which must not be recorded as a green run,
  because that advances the "last successful scrape" watermark.
"""

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.repositories.scraping_history_repository import (
    ScrapingHistoryRepository,
)
from backend.scraper.adapter import InsuranceScraperAdapter, ScraperAdapter

DUMMY_CREDENTIALS = {"username": "user", "password": "pass123"}
DUMMY_START_DATE = date(2024, 3, 1)


def _adapter(cls=ScraperAdapter, service: str = "credit_cards") -> ScraperAdapter:
    """Build an adapter without running the scrape lifecycle."""
    return cls(
        service, "isracard", "Card1",
        DUMMY_CREDENTIALS, DUMMY_START_DATE, 1,
    )


def _txn(**overrides) -> SimpleNamespace:
    """Build a minimal scraped Transaction stand-in."""
    txn = {
        "date": "2024-03-15",
        "charged_amount": -25.0,
        "description": "coffee",
        "identifier": None,
        "type": SimpleNamespace(value="normal"),
        "status": SimpleNamespace(value="completed"),
        "memo": None,
    }
    txn.update(overrides)
    return SimpleNamespace(**txn)


def _result(*transactions, account_number: str = "1234") -> SimpleNamespace:
    """Wrap transactions in a single-account ScrapingResult stand-in."""
    return SimpleNamespace(
        accounts=[
            SimpleNamespace(
                account_number=account_number,
                transactions=list(transactions),
                metadata=None,
            )
        ]
    )


class TestDedupKeyCollision:
    """Distinct same-day, same-amount rows must not share a dedup key."""

    def test_two_identical_rows_get_distinct_ids(self):
        """Two 25.00 coffees on one day produce two different ``id`` values.

        Sharing an id made the second one invisible to ingestion forever:
        the repo dedups on (id, provider, date, amount), so once the first
        was stored, any overlapping re-scrape dropped the second.
        """
        adapter = _adapter()
        df = adapter._result_to_dataframe(_result(_txn(), _txn()), "credit_cards")
        ids = list(df["id"])
        assert len(set(ids)) == 2

    def test_first_occurrence_keeps_the_legacy_key_format(self):
        """The first row's id is byte-identical to the pre-fix format.

        Changing it would orphan every already-stored identifier-less row
        and re-insert it as a duplicate on the next overlapping scrape.
        """
        adapter = _adapter()
        df = adapter._result_to_dataframe(_result(_txn(), _txn()), "credit_cards")
        assert df["id"].iloc[0] == "1234_2024-03-15_-25.0"

    def test_three_identical_rows_get_three_distinct_ids(self):
        """The discriminator keeps counting past the second duplicate."""
        adapter = _adapter()
        df = adapter._result_to_dataframe(
            _result(_txn(), _txn(), _txn()), "credit_cards"
        )
        assert len(set(df["id"])) == 3

    def test_provider_identifiers_are_left_untouched(self):
        """Rows carrying a provider identifier keep it verbatim."""
        adapter = _adapter()
        df = adapter._result_to_dataframe(
            _result(_txn(identifier="ABC1"), _txn(identifier="ABC2")),
            "credit_cards",
        )
        assert list(df["id"]) == ["ABC1", "ABC2"]

    def test_different_amounts_are_not_discriminated(self):
        """Rows that already differ keep their plain keys."""
        adapter = _adapter()
        df = adapter._result_to_dataframe(
            _result(_txn(), _txn(charged_amount=-30.0)), "credit_cards"
        )
        assert list(df["id"]) == [
            "1234_2024-03-15_-25.0", "1234_2024-03-15_-30.0"
        ]

    def test_same_key_across_accounts_is_not_discriminated(self):
        """Identical rows on different accounts are already distinct."""
        adapter = _adapter()
        result = SimpleNamespace(
            accounts=[
                SimpleNamespace(account_number="1111",
                                transactions=[_txn()], metadata=None),
                SimpleNamespace(account_number="2222",
                                transactions=[_txn()], metadata=None),
            ]
        )
        df = adapter._result_to_dataframe(result, "credit_cards")
        assert list(df["id"]) == [
            "1111_2024-03-15_-25.0", "2222_2024-03-15_-25.0"
        ]


class TestUniqueIdKeyStability:
    """The ``unique_id`` key must be deterministic and collision-free."""

    def test_float_repr_noise_is_normalized(self):
        """0.1 + 0.2 and 0.3 produce the same key, not two different ones."""
        adapter = _adapter()
        noisy = adapter._result_to_dataframe(
            _result(_txn(charged_amount=0.1 + 0.2)), "credit_cards"
        )
        clean = adapter._result_to_dataframe(
            _result(_txn(charged_amount=0.3)), "credit_cards"
        )
        assert noisy["unique_id"].iloc[0] == clean["unique_id"].iloc[0]

    def test_amount_is_formatted_to_two_decimals(self):
        """Amounts are rendered at fixed precision, not raw float repr."""
        adapter = _adapter()
        df = adapter._result_to_dataframe(
            _result(_txn(charged_amount=-25.0)), "credit_cards"
        )
        assert "-25.00" in df["unique_id"].iloc[0]

    def test_identical_rows_get_distinct_unique_ids(self):
        """Two identical rows never share a unique_id."""
        adapter = _adapter()
        df = adapter._result_to_dataframe(_result(_txn(), _txn()), "credit_cards")
        assert len(set(df["unique_id"])) == 2


class TestInsuranceMemoMapping:
    """The insurance memo map must key off the same ids as the base frame."""

    def test_memo_map_follows_the_discriminated_ids(self):
        """Two identical deposits keep their own memos."""
        adapter = _adapter(InsuranceScraperAdapter, "insurance")
        result = _result(
            _txn(memo="first"),
            _txn(memo="second"),
        )
        df = adapter._result_to_dataframe(result, "insurance")
        assert sorted(df["memo"]) == ["first", "second"]


@contextmanager
def _fake_db():
    """Yield a MagicMock session in place of a real DB context."""
    yield MagicMock()


def _record(adapter) -> tuple[str, str | None]:
    """Run _record_scraping_attempt and capture the recorded status."""
    with patch("backend.scraper.adapter.get_db_context", _fake_db), patch(
        "backend.scraper.adapter.ScrapingHistoryRepository"
    ) as repo_cls:
        repo_cls.SUCCESS = ScrapingHistoryRepository.SUCCESS
        repo_cls.FAILED = ScrapingHistoryRepository.FAILED
        repo_cls.CANCELED = ScrapingHistoryRepository.CANCELED
        adapter._record_scraping_attempt(1)
        call = repo_cls.return_value.record_scrape_end.call_args
    return call.args[1], call.args[2]


class TestEmptyScrapeIsNotSuccess:
    """A run that fetched no accounts at all must not be recorded green.

    Isracard, Max and HaPhoenix swallow per-request failures, so an expired
    session returns zero accounts with no error. Recording SUCCESS there
    both hides the breakage and advances the last-successful-scrape
    watermark used to compute the next scrape window.
    """

    def test_zero_accounts_records_failed(self):
        """No accounts fetched → FAILED with an explanatory message."""
        import pandas as pd

        adapter = _adapter()
        adapter._data = pd.DataFrame()
        adapter._accounts_fetched = 0
        status, message = _record(adapter)
        assert status == ScrapingHistoryRepository.FAILED
        assert message

    def test_account_with_no_transactions_still_records_success(self):
        """An account that simply had no activity is a legitimate success."""
        import pandas as pd

        adapter = _adapter()
        adapter._data = pd.DataFrame()
        adapter._accounts_fetched = 1
        status, message = _record(adapter)
        assert status == ScrapingHistoryRepository.SUCCESS
        assert message is None

    def test_normal_run_records_success(self):
        """A run with rows is unaffected."""
        import pandas as pd

        adapter = _adapter()
        adapter._data = pd.DataFrame([{"a": 1}])
        adapter._accounts_fetched = 1
        status, _ = _record(adapter)
        assert status == ScrapingHistoryRepository.SUCCESS

    def test_explicit_error_still_wins(self):
        """An error message keeps producing FAILED regardless of accounts."""
        import pandas as pd

        adapter = _adapter()
        adapter._data = pd.DataFrame([{"a": 1}])
        adapter._accounts_fetched = 1
        adapter._error = "boom"
        status, message = _record(adapter)
        assert status == ScrapingHistoryRepository.FAILED
        assert message == "boom"

    def test_cancel_still_wins(self):
        """A canceled 2FA prompt is still recorded as CANCELED."""
        adapter = _adapter()
        adapter._otp_code = ScraperAdapter.CANCEL
        adapter._accounts_fetched = 0
        status, _ = _record(adapter)
        assert status == ScrapingHistoryRepository.CANCELED
