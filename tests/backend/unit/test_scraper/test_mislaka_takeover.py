"""Tests for the pension clearing house taking policies over from HaPhoenix.

HaPhoenix is deprecated in favour of the clearing house (Mislaka), which
reports the same policies under a different spelling (``7-925-053655-0`` for
HaPhoenix's ``007-925-053655``) and only the current year's deposits. A
Mislaka scrape must therefore re-key onto the stored policy, adopt the
HaPhoenix deposits it cannot report itself, and dedup the ones it can — while
a HaPhoenix credential the user keeps scraping may only refresh the balance.
"""

from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

import pandas as pd
from sqlalchemy import select

from backend.models.clearing_house_report import ClearingHouseReport
from backend.models.insurance_account import InsuranceAccount
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.models.transaction import InsuranceTransaction
from backend.repositories.transactions import TransactionsRepository
from backend.scraper.adapter import InsuranceScraperAdapter
from backend.services.investments import InvestmentsService
from scraper.models.account import AccountResult
from scraper.models.result import ScrapingResult
from scraper.models.transaction import Transaction, TransactionStatus, TransactionType

STORED_ID = "007-925-053655"
MISLAKA_ID = "7-925-053655-0"
KEY = "7-925-53655"
PHOENIX_TAG = f"Keren Hishtalmut - hafenix ({STORED_ID})"


def _deposit(day: str, amount: float) -> Transaction:
    """A scraped KH deposit keyed the way both scrapers key it."""
    return Transaction(
        type=TransactionType.NORMAL,
        status=TransactionStatus.COMPLETED,
        date=day,
        processed_date=day,
        original_amount=amount,
        original_currency="ILS",
        charged_amount=amount,
        charged_currency="ILS",
        description="הפקדה",
        identifier=f"{KEY}_{day}_{amount}",
    )


def _meta(provider: str, policy_id: str, **overrides: object) -> dict:
    """KH metadata as a scraper reports it."""
    meta = {
        "provider": provider,
        "policy_id": policy_id,
        "policy_type": "hishtalmut",
        "pension_type": None,
        "account_name": "קרן השתלמות",
        "balance": 12311.0,
        "balance_date": "2026-08-31",
        "investment_tracks": '[{"name": "S&P", "yield_pct": 5.1, "allocation_pct": 100.0, "sum": 12311.0}]',
        "commission_deposits_pct": 0.0,
        "commission_savings_pct": 0.6,
        "liquidity_date": "2032-01-31",
    }
    meta.update(overrides)
    return meta


def _scrape(db_session, provider: str, account_name: str, result: ScrapingResult) -> None:
    """Run the adapter's save pipeline (pre-save, rows, save, post-save)."""
    adapter = InsuranceScraperAdapter(
        "insurances", provider, account_name, {}, date(2026, 1, 1), 1
    )

    @contextmanager
    def db_context():
        yield db_session

    with patch("backend.scraper.adapter.get_db_context", side_effect=db_context):
        adapter._pre_save_hook(result)
        frame = adapter._result_to_dataframe(result, "insurances")
        TransactionsRepository(db_session).add_scraped_transactions(
            frame, "insurance_transactions"
        )
        adapter._post_save_hook(result)


def _seed_haphoenix(db_session) -> None:
    """A HaPhoenix-scraped KH policy with two deposits and its investment."""
    _scrape(
        db_session,
        "hafenix",
        "Phoenix login",
        ScrapingResult(
            success=True,
            accounts=[
                AccountResult(
                    account_number=STORED_ID,
                    transactions=[_deposit("2025-12-10", 1500.0), _deposit("2026-08-05", 1571.2)],
                    metadata=_meta(
                        "hafenix",
                        STORED_ID,
                        balance=13939.0,
                        balance_date="2026-09-15",
                        investment_tracks="[]",
                    ),
                )
            ],
        ),
    )


def _mislaka_scrape(db_session) -> None:
    """A Mislaka scrape of the same policy: one overlapping, one new deposit."""
    _scrape(
        db_session,
        "mislaka",
        "Clearing house",
        ScrapingResult(
            success=True,
            accounts=[
                AccountResult(
                    account_number=MISLAKA_ID,
                    transactions=[_deposit("2026-07-08", 1571.2), _deposit("2026-08-05", 1571.2)],
                    metadata=_meta(
                        "mislaka",
                        MISLAKA_ID,
                        balance_history=[
                            {"date": "2026-07-31", "balance": 10700.0},
                            {"date": "2026-08-31", "balance": 12311.0},
                        ],
                    ),
                )
            ],
        ),
    )


def _transactions(db_session) -> pd.DataFrame:
    """Every stored insurance transaction."""
    rows = db_session.execute(select(InsuranceTransaction)).scalars().all()
    return pd.DataFrame(
        [
            {
                "date": r.date,
                "amount": r.amount,
                "provider": r.provider,
                "account_name": r.account_name,
                "account_number": r.account_number,
            }
            for r in rows
        ]
    ).sort_values("date", ignore_index=True)


class TestMislakaTakeover:
    """A Mislaka scrape of a HaPhoenix policy adopts rather than forks it."""

    def test_history_is_adopted_and_overlap_deduped(self, db_session):
        """Verify one row per deposit, all owned by the Mislaka credential."""
        _seed_haphoenix(db_session)

        _mislaka_scrape(db_session)

        txns = _transactions(db_session)
        assert list(txns["date"]) == ["2025-12-10", "2026-07-08", "2026-08-05"]
        assert set(txns["provider"]) == {"mislaka"}
        assert set(txns["account_name"]) == {"Clearing house"}
        assert set(txns["account_number"]) == {STORED_ID}

    def test_account_keeps_its_id_and_newer_balance_but_changes_owner(self, db_session):
        """Verify re-keying, the ownership move and the balance-date guard."""
        _seed_haphoenix(db_session)

        _mislaka_scrape(db_session)

        [account] = db_session.execute(select(InsuranceAccount)).scalars().all()
        assert account.policy_id == STORED_ID
        assert account.provider == "mislaka"
        assert (account.balance, account.balance_date) == (13939.0, "2026-09-15")
        assert "S&P" in account.investment_tracks

    def test_investment_is_kept_with_its_tag_and_gains_month_end_snapshots(
        self, db_session
    ):
        """Verify the KH investment is not renamed or forked by the takeover."""
        _seed_haphoenix(db_session)

        _mislaka_scrape(db_session)

        [investment] = db_session.execute(select(Investment)).scalars().all()
        assert investment.tag == PHOENIX_TAG
        snapshots = db_session.execute(
            select(InvestmentBalanceSnapshot.date, InvestmentBalanceSnapshot.balance)
        ).all()
        assert sorted(snapshots) == [
            ("2026-07-31", 10700.0),
            ("2026-08-31", 12311.0),
            ("2026-09-15", 13939.0),
        ]

    def test_rerunning_the_mislaka_scrape_changes_nothing(self, db_session):
        """Verify the takeover is idempotent."""
        _seed_haphoenix(db_session)
        _mislaka_scrape(db_session)
        before = _transactions(db_session)

        _mislaka_scrape(db_session)

        pd.testing.assert_frame_equal(_transactions(db_session), before)


class TestHaPhoenixAfterTakeover:
    """A HaPhoenix credential still scraping after the takeover."""

    def _late_haphoenix_scrape(self, db_session) -> None:
        """HaPhoenix re-reports an adopted deposit plus a newer one."""
        _scrape(
            db_session,
            "hafenix",
            "Phoenix login",
            ScrapingResult(
                success=True,
                accounts=[
                    AccountResult(
                        account_number=STORED_ID,
                        transactions=[
                            _deposit("2026-08-05", 1571.2),
                            _deposit("2026-09-08", 1571.2),
                        ],
                        metadata=_meta(
                            "hafenix",
                            STORED_ID,
                            account_name="Renamed by HaPhoenix",
                            balance=14500.0,
                            balance_date="2026-09-20",
                            investment_tracks="[]",
                        ),
                    )
                ],
            ),
        )

    def test_only_the_balance_is_refreshed(self, db_session):
        """Verify the superseded provider cannot take the policy back."""
        _seed_haphoenix(db_session)
        _mislaka_scrape(db_session)

        self._late_haphoenix_scrape(db_session)

        [account] = db_session.execute(select(InsuranceAccount)).scalars().all()
        assert account.provider == "mislaka"
        assert account.account_name == "קרן השתלמות"
        assert "S&P" in account.investment_tracks
        assert (account.balance, account.balance_date) == (14500.0, "2026-09-20")

    def test_adopted_deposits_are_not_reinserted(self, db_session):
        """Verify dedup ignores the provider, and the next takeover adopts the rest."""
        _seed_haphoenix(db_session)
        _mislaka_scrape(db_session)

        self._late_haphoenix_scrape(db_session)
        txns = _transactions(db_session)
        assert list(txns["date"]) == ["2025-12-10", "2026-07-08", "2026-08-05", "2026-09-08"]
        assert txns.loc[3, "provider"] == "hafenix"

        _mislaka_scrape(db_session)
        assert set(_transactions(db_session)["provider"]) == {"mislaka"}


class TestClearingHouseReports:
    """The household summaries a clearing-house scrape hands back."""

    def _scrape_reports(self, db_session, forecast: float) -> None:
        """Run a scrape whose extras carry two monthly reports."""
        result = ScrapingResult(
            success=True,
            accounts=[],
            extras={
                "clearing_house_reports": [
                    {"calc_date": "2026-07-31", "forecast_monthly_pension": 40490.0},
                    {
                        "calc_date": "2026-08-31",
                        "forecast_monthly_pension": forecast,
                        "subscription_expires": "2027-04-11",
                    },
                ]
            },
        )
        _scrape(db_session, "mislaka", "Clearing house", result)

    def test_each_report_month_is_stored_once(self, db_session):
        """Verify a re-scrape updates a month rather than duplicating it."""
        self._scrape_reports(db_session, 40691.0)
        self._scrape_reports(db_session, 40700.0)

        rows = db_session.execute(
            select(ClearingHouseReport).order_by(ClearingHouseReport.calc_date)
        ).scalars().all()
        assert [(r.calc_date, r.forecast_monthly_pension) for r in rows] == [
            ("2026-07-31", 40490.0),
            ("2026-08-31", 40700.0),
        ]
        assert rows[1].subscription_expires == "2027-04-11"
        assert {(r.provider, r.account_name) for r in rows} == {
            ("mislaka", "Clearing house")
        }


class TestSyncFromInsuranceAccount:
    """``InvestmentsService.sync_from_insurance_account`` on its own."""

    def test_manual_snapshots_survive_history_points(self, db_session):
        """Verify a month-end point never overwrites a user's manual value."""
        service = InvestmentsService(db_session)
        account = InsuranceAccount(**_meta("mislaka", STORED_ID))
        db_session.add(account)
        db_session.commit()
        service.sync_from_insurance_account(account)
        [investment] = db_session.execute(select(Investment)).scalars().all()
        service.snapshots_repo.upsert_snapshot(
            investment.id, "2026-07-31", 99999.0, source="manual"
        )

        service.sync_from_insurance_account(
            account, [{"date": "2026-07-31", "balance": 10700.0}]
        )

        manual = db_session.execute(
            select(InvestmentBalanceSnapshot.balance).where(
                InvestmentBalanceSnapshot.date == "2026-07-31"
            )
        ).scalar_one()
        assert manual == 99999.0
