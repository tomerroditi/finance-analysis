"""Tests for what the app derives from the pension clearing house's data.

Covers the monthly-pension estimate re-derived from the providers' own
forecasts for the user's target retirement age, and the mirroring of loans
taken against a pension/Keren Hishtalmut policy onto the Liabilities page.
The forecast figures are shaped like two real funds' published numbers.
"""

import json

import pytest
from sqlalchemy import select

from backend.models.insurance_account import InsuranceAccount
from backend.models.liability import Liability
from backend.services.liabilities_service import LiabilitiesService
from backend.services.retirement_service import (
    RetirementService,
    project_pension_payout,
)
from backend.services.tagging_service import CategoriesTagsService

COMPREHENSIVE = {
    "balance": 254624.49,
    "retirement_age": 67,
    "capital_no_deposits": 1041302.16,
    "capital_with_deposits": 5755063.0,
    "pension_no_deposits": 5307.35,
    "pension_with_deposits": 29333.0,
}
SUPPLEMENTARY = {
    "balance": 38816.18,
    "retirement_age": 67,
    "capital_no_deposits": 114268.0,
    "capital_with_deposits": 2326919.0,
    "pension_no_deposits": 557.76,
    "pension_with_deposits": 11358.0,
}


def _pension_account(policy_id: str, forecast: dict) -> InsuranceAccount:
    """An insurance account whose details carry a clearing-house forecast."""
    return InsuranceAccount(
        provider="mislaka",
        policy_id=policy_id,
        policy_type="pension",
        pension_type="makifa",
        account_name="Pension",
        balance=forecast["balance"],
        balance_date="2026-08-31",
        details=json.dumps(
            {
                "source_date": "2026-08-31",
                "retirement_age": forecast["retirement_age"],
                "balance_forecast": forecast["capital_with_deposits"],
                "balance_forecast_no_deposits": forecast["capital_no_deposits"],
                "monthly_pension_forecast": forecast["pension_with_deposits"],
                "monthly_pension_forecast_no_deposits": forecast["pension_no_deposits"],
            }
        ),
    )


class TestProjectPensionPayout:
    """The per-fund re-derivation for a given stop age."""

    @pytest.mark.parametrize("fund", [COMPREHENSIVE, SUPPLEMENTARY])
    def test_depositing_to_retirement_age_is_the_providers_own_forecast(self, fund):
        """Verify stopping at retirement age reproduces "deposits continue"."""
        assert project_pension_payout(fund, 30, 67) == pytest.approx(
            fund["pension_with_deposits"]
        )

    @pytest.mark.parametrize("fund", [COMPREHENSIVE, SUPPLEMENTARY])
    def test_stopping_today_is_the_providers_no_deposit_forecast(self, fund):
        """Verify stopping now reproduces "no further deposits"."""
        assert project_pension_payout(fund, 30, 30) == pytest.approx(
            fund["pension_no_deposits"]
        )

    def test_later_stop_ages_pay_more(self):
        """Verify the estimate rises with every extra year of deposits."""
        payouts = [project_pension_payout(COMPREHENSIVE, 30, age) for age in range(30, 68)]

        assert payouts == sorted(payouts)
        assert payouts[0] < payouts[20] < payouts[-1]

    def test_a_fund_without_a_deposit_forecast_pays_its_no_deposit_pension(self):
        """Verify an inactive fund contributes its frozen pension only."""
        frozen = {**COMPREHENSIVE, "pension_with_deposits": 0, "capital_with_deposits": 0}

        assert project_pension_payout(frozen, 30, 60) == frozen["pension_no_deposits"]


class TestGetPensionForecast:
    """``RetirementService.get_pension_forecast`` over stored accounts."""

    def test_no_forecast_without_clearing_house_data(self, db_session):
        """Verify the estimate is None when no pension publishes a forecast."""
        forecast = RetirementService(db_session).get_pension_forecast(30, 50)

        assert forecast["estimate"] is None
        assert forecast["funds"] == 0

    def test_sums_every_fund_for_the_plan_ages(self, db_session):
        """Verify both funds are projected and the totals reported."""
        db_session.add_all(
            [
                _pension_account("1215029099", COMPREHENSIVE),
                _pension_account("7187793018", SUPPLEMENTARY),
            ]
        )
        db_session.commit()

        forecast = RetirementService(db_session).get_pension_forecast(30, 67)

        assert forecast["estimate"] == 40691
        assert (forecast["with_deposits"], forecast["no_deposits"]) == (40691, 5865)
        assert forecast["as_of"] == "2026-08-31"
        assert forecast["funds"] == 2

    def test_without_ages_or_a_plan_the_deposits_continue_figure_is_used(
        self, db_session
    ):
        """Verify the default when there is nothing to take the ages from."""
        db_session.add(_pension_account("1215029099", COMPREHENSIVE))
        db_session.commit()

        forecast = RetirementService(db_session).get_pension_forecast()

        assert forecast["estimate"] == 29333


LOAN = {
    "amount": 30000.0,
    "balance": 18000.0,
    "interest_pct": 3.5,
    "monthly_payment": 670.0,
    "payments_months": 48,
    "received": "2025-01-15",
    "ends": "2029-01-15",
}


def _liabilities(db_session) -> list[Liability]:
    """Every stored liability."""
    return list(db_session.execute(select(Liability)).scalars().all())


class TestSyncInsuranceLoans:
    """``LiabilitiesService.sync_insurance_loans``."""

    def test_a_loan_becomes_a_tagged_liability(self, db_session):
        """Verify the liability, its terms and its Liabilities tag."""
        LiabilitiesService(db_session).sync_insurance_loans(
            "7-925-053655", "Keren Hishtalmut", "Some Fund Ltd", [LOAN]
        )

        [liability] = _liabilities(db_session)
        assert liability.tag == "Pension Loan 7-925-053655"
        assert (liability.principal_amount, liability.interest_rate) == (30000.0, 3.5)
        assert (liability.term_months, liability.start_date) == (48, "2025-01-15")
        assert liability.lender == "Some Fund Ltd"
        assert not liability.is_paid_off
        tags = CategoriesTagsService(db_session).categories_and_tags["Liabilities"]
        assert "Pension Loan 7-925-053655" in tags

    def test_a_rescrape_updates_rather_than_duplicates(self, db_session):
        """Verify the loan key keeps one liability per loan."""
        service = LiabilitiesService(db_session)
        service.sync_insurance_loans("7-925-053655", "KH", None, [LOAN])

        service.sync_insurance_loans(
            "007-925-053655", "KH", None, [{**LOAN, "interest_pct": 3.9}]
        )

        [liability] = _liabilities(db_session)
        assert liability.interest_rate == 3.9

    def test_a_repaid_loan_is_marked_paid_off(self, db_session):
        """Verify a zero balance closes the liability on the loan's end date."""
        service = LiabilitiesService(db_session)
        service.sync_insurance_loans("7-925-053655", "KH", None, [LOAN])

        service.sync_insurance_loans("7-925-053655", "KH", None, [{**LOAN, "balance": 0}])

        [liability] = _liabilities(db_session)
        assert liability.is_paid_off
        assert liability.paid_off_date == "2029-01-15"

    def test_loans_without_an_amount_or_start_are_ignored(self, db_session):
        """Verify incomplete loan rows never create a liability."""
        LiabilitiesService(db_session).sync_insurance_loans(
            "7-925-053655", "KH", None, [{**LOAN, "amount": 0}, {**LOAN, "received": None}]
        )

        assert _liabilities(db_session) == []


class TestScrapeMirrorsLoans:
    """A clearing-house scrape carrying a loan puts it on the Liabilities page."""

    def test_post_save_syncs_loans_from_details(self, db_session):
        """Verify the adapter hands each policy's loans to the liability sync."""
        from contextlib import contextmanager
        from datetime import date
        from types import SimpleNamespace
        from unittest.mock import patch

        from backend.scraper.adapter import InsuranceScraperAdapter

        adapter = InsuranceScraperAdapter(
            "insurances", "mislaka", "Clearing house", {}, date(2026, 1, 1), 1
        )
        meta = {
            "provider": "mislaka",
            "policy_id": "7-925-053655",
            "policy_type": "hishtalmut",
            "account_name": "Keren Hishtalmut",
            "balance": 12000.0,
            "balance_date": "2026-08-31",
            "details": json.dumps({"manufacturer": "Some Fund Ltd", "loans": [LOAN]}),
        }

        @contextmanager
        def db_context():
            yield db_session

        with patch("backend.scraper.adapter.get_db_context", side_effect=db_context):
            adapter._post_save_hook(
                SimpleNamespace(accounts=[SimpleNamespace(metadata=meta)], extras={})
            )

        [liability] = _liabilities(db_session)
        assert liability.name == "Keren Hishtalmut — loan"
        assert liability.lender == "Some Fund Ltd"
