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
from backend.errors import ValidationException
from backend.services.budget_month_override_service import (
    BudgetMonthOverrideService,
)
from backend.services.budget_service import MonthlyBudgetService
from backend.services.transactions_service import TransactionsService


@pytest.fixture(autouse=True)
def _mock_categories_cache(sample_categories_yaml):
    """Mock the categories cache for all tests in this module."""
    with patch(
        "backend.services.tagging_service._categories_cache",
        sample_categories_yaml,
    ):
        yield


def _cc_jan_5_uid(db_session: Session) -> int:
    """Return the unique_id of the seeded cc_jan_5 (-250, 2024-01-20) transaction."""
    all_data = TransactionsService(db_session).get_data_for_analysis()
    cc_jan_5 = all_data[all_data["id"] == "cc_jan_5"].iloc[0]
    return int(cc_jan_5["unique_id"])


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

    def test_move_more_than_one_month_rejected(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify moving a transaction two months away raises ValidationException."""
        override_svc = BudgetMonthOverrideService(db_session)
        with pytest.raises(ValidationException):
            override_svc.set_override(
                source_type="transaction",
                source_id=_cc_jan_5_uid(db_session),
                source_table="credit_card_transactions",
                override_year=2024,
                override_month=3,
            )

    def test_override_map_returns_active_overrides(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify get_override_map exposes the stored override for budget filtering."""
        override_svc = BudgetMonthOverrideService(db_session)
        uid = _cc_jan_5_uid(db_session)
        override_svc.set_override(
            source_type="transaction",
            source_id=uid,
            source_table="credit_card_transactions",
            override_year=2024,
            override_month=2,
        )

        mapping = override_svc.get_override_map()
        assert mapping["transaction"][uid] == (2024, 2)
