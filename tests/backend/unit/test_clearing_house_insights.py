"""Tests for what the app derives from the pension clearing house's data.

Covers the mirroring of loans taken against a pension/Keren Hishtalmut policy
onto the Liabilities page.
"""

import json

from sqlalchemy import select

from backend.models.liability import Liability
from backend.services.liabilities_service import LiabilitiesService
from backend.services.tagging_service import CategoriesTagsService

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
