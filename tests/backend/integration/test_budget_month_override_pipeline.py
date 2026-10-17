"""
Integration tests for the budget month override feature.

Verifies that reassigning a transaction to an adjacent month moves it
between monthly budget views, that movement is capped at +/- one month,
and that reverting to the real month clears the override. Uses a real
in-memory SQLite database with seed fixtures.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.constants.budget import ALL_TAGS, TOTAL_BUDGET
from backend.services.budget_month_override_service import (
    BudgetMonthOverrideService,
)
from backend.services.budget import MonthlyBudgetService
from backend.services.budget.ledger import budget_months
from backend.services.transactions_service import TransactionsService


@pytest.fixture(autouse=True)
def _mock_categories_cache(sample_categories_yaml):
    """Mock the categories cache for all tests in this module."""
    from backend.services.tagging_service import cache_key

    with patch(
        "backend.services.tagging_service._categories_cache",
        {cache_key(): sample_categories_yaml},
    ):
        yield


def _cc_jan_5_uid(db_session: Session) -> int:
    """Return the unique_id of the seeded cc_jan_5 (-250, 2024-01-20) transaction."""
    all_data = TransactionsService(db_session).get_data_for_analysis()
    cc_jan_5 = all_data[all_data["id"] == "cc_jan_5"].iloc[0]
    return int(cc_jan_5["unique_id"])


def _project_tx_ids(summary: dict) -> dict:
    """Map each project category to the sorted ids of its transactions."""
    return {
        p["category"]: sorted(t["id"] for t in p["transactions"])
        for p in summary["projects"]
    }


class TestBudgetMonthOverridePipeline:
    """Integration tests for moving transactions between budget months."""

    def test_move_next_month_shifts_transaction_between_views(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify moving a Jan transaction to Feb removes it from Jan and adds it to Feb.

        cc_jan_5 (-250) is moved from January to February; the January total
        must drop by 250 and the February total must rise by 250.
        """
        budget_svc = MonthlyBudgetService(db_session)
        budget_svc.add_rule(
            "Total Budget", 15000, TOTAL_BUDGET, [ALL_TAGS], month=1, year=2024
        )
        budget_svc.add_rule(
            "Total Budget", 15000, TOTAL_BUDGET, [ALL_TAGS], month=2, year=2024
        )

        jan_before = budget_svc.get_monthly_budget_view(2024, 1)[0]["current_amount"]
        feb_before = budget_svc.get_monthly_budget_view(2024, 2)[0]["current_amount"]

        override_svc = BudgetMonthOverrideService(db_session)
        override_svc.set_override(
            source_type="transaction",
            source_id=_cc_jan_5_uid(db_session),
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=2,
        )

        jan_after = budget_svc.get_monthly_budget_view(2024, 1)[0]["current_amount"]
        feb_after = budget_svc.get_monthly_budget_view(2024, 2)[0]["current_amount"]

        assert jan_after == pytest.approx(jan_before - 250.0)
        assert feb_after == pytest.approx(feb_before + 250.0)

    def test_reverting_to_real_month_clears_override(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify targeting the real month removes the override and restores totals."""
        budget_svc = MonthlyBudgetService(db_session)
        budget_svc.add_rule(
            "Total Budget", 15000, TOTAL_BUDGET, [ALL_TAGS], month=1, year=2024
        )
        jan_before = budget_svc.get_monthly_budget_view(2024, 1)[0]["current_amount"]

        override_svc = BudgetMonthOverrideService(db_session)
        uid = _cc_jan_5_uid(db_session)
        override_svc.set_override(
            source_type="transaction",
            source_id=uid,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=2,
        )

        # Move it back to its real month (January) — should clear the override.
        result = override_svc.set_override(
            source_type="transaction",
            source_id=uid,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=1,
        )

        assert result == {"removed": True}
        assert override_svc.get_all() == []
        jan_after = budget_svc.get_monthly_budget_view(2024, 1)[0]["current_amount"]
        assert jan_after == pytest.approx(jan_before)

    def test_override_moves_the_row_in_every_pool(
        self, db_session: Session, seed_base_transactions, seed_project_transactions
    ):
        """One budget month per row: yearly and project pools follow the override.

        A December 2023 -> January 2024 boundary case used to stay in its real
        year's envelope while the monthly view moved it, so the two counted it
        in different years. Every pool now reads the row's budget month.
        """
        from backend.services.budget import YearlyBudgetService

        yearly_svc = YearlyBudgetService(db_session)
        yearly_svc.create_rule("Other Y", 5000.0, "Other", ["all_tags"], 2024)
        yearly_before = yearly_svc.get_yearly_budget_view(2024)[0]["current_amount"]

        override_svc = BudgetMonthOverrideService(db_session)
        # cc_jan_5 (Other, -250, 2024-01-20) -> December 2023.
        override_svc.set_override(
            source_type="transaction",
            source_id=_cc_jan_5_uid(db_session),
            source_table="credit_card_transactions",
            override_year=2023,
            override_month=12,
        )
        yearly_after = yearly_svc.get_yearly_budget_view(2024)[0]["current_amount"]
        assert yearly_before == pytest.approx(250.0)
        assert yearly_after == pytest.approx(0.0)

        # cc_wedding_1 (Wedding/Venue, -5000, 2024-01-15) -> February 2024.
        budget_svc = MonthlyBudgetService(db_session)
        all_data = TransactionsService(db_session).get_data_for_analysis()
        wedding_uid = int(all_data[all_data["id"] == "cc_wedding_1"].iloc[0]["unique_id"])
        jan_before = budget_svc.get_monthly_project_spending_summary(2024, 1)
        feb_before = budget_svc.get_monthly_project_spending_summary(2024, 2)
        override_svc.set_override(
            source_type="transaction",
            source_id=wedding_uid,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=2,
        )
        jan_after = budget_svc.get_monthly_project_spending_summary(2024, 1)
        feb_after = budget_svc.get_monthly_project_spending_summary(2024, 2)
        assert jan_before["total_spent"] == pytest.approx(8200.0)
        assert jan_after["total_spent"] == pytest.approx(3200.0)
        assert feb_after.get("total_spent", 0.0) == pytest.approx(
            feb_before.get("total_spent", 0.0) + 5000.0
        )
        assert "cc_wedding_1" not in _project_tx_ids(jan_after).get("Wedding", [])

    def test_override_does_not_leak_across_tables_with_same_uid(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify an override only moves the row in its own table.

        ``unique_id`` is a per-table auto-increment, so the same integer
        exists in the bank and credit-card tables. An override stored for a
        credit-card transaction must not re-month the bank transaction that
        happens to share its unique_id.
        """
        import pandas as pd

        override_svc = BudgetMonthOverrideService(db_session)
        uid = _cc_jan_5_uid(db_session)

        # Stored for the credit-card table only (repo-level to keep the
        # colliding bank uid fully synthetic and independent of seed dates).
        override_svc.repo.upsert(
            source_type="transaction",
            source_id=uid,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=2,
        )

        expenses = pd.DataFrame(
            [
                {
                    "unique_id": uid,
                    "source": "credit_card_transactions",
                    "date": "2024-01-20",
                    "amount": -250.0,
                },
                {
                    "unique_id": uid,
                    "source": "bank_transactions",
                    "date": "2024-01-20",
                    "amount": -99.0,
                },
            ]
        )
        _, months = budget_months(expenses, override_svc.get_override_map())

        assert months.tolist() == [2, 1]
