"""
Integration tests for the Budget Pipeline.

Tests the full budget flow: rules creation, transaction aggregation,
monthly/project views, split handling, and pending refund exclusions.
Uses a real in-memory SQLite database with seed fixtures.
"""

from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.constants.budget import ALL_TAGS, TOTAL_BUDGET
from backend.models.transaction import CreditCardTransaction
from backend.services.budget_service import (
    MonthlyBudgetService,
    ProjectBudgetService,
)
from backend.services.pending_refunds_service import PendingRefundsService


@pytest.fixture(autouse=True)
def _mock_categories_cache(sample_categories_yaml):
    """Mock the categories cache for all tests in this module."""
    with patch(
        "backend.services.tagging_service._categories_cache",
        {False: sample_categories_yaml},
    ):
        yield


class TestBudgetPipeline:
    """Integration tests for the full budget pipeline."""

    def test_project_budget_view(
        self, db_session: Session, seed_project_transactions
    ):
        """Verify the project view aggregates seeded spend per tag rule and in total.

        Wedding: Venue = cc_wedding_1(5000) + bank_wedding_1(15000)
        + cc_wedding_3(2500) = 22500; Catering = cc_wedding_2(800)
        + bank_wedding_2(12000) = 12800; total 35300.
        """
        svc = ProjectBudgetService(db_session)

        result = svc.get_project_budget_view("Wedding")

        assert result["name"] == "Wedding"
        assert result["total_spent"] == pytest.approx(35300.0)

        by_name = {r["rule"]["name"]: r for r in result["rules"]}
        assert set(by_name) == {TOTAL_BUDGET, "Venue", "Catering"}
        total = by_name[TOTAL_BUDGET]
        assert total["rule"]["amount"] == 50000.0
        assert total["current_amount"] == pytest.approx(35300.0)
        assert total["allow_delete"] is False
        assert len(total["data"]) == 5
        assert by_name["Venue"]["current_amount"] == pytest.approx(22500.0)
        assert len(by_name["Venue"]["data"]) == 3
        assert by_name["Catering"]["current_amount"] == pytest.approx(12800.0)
        assert len(by_name["Catering"]["data"]) == 2
        # Every tag had a rule already, so nothing was auto-created.
        assert len(svc.get_rules_for_project("Wedding")) == 3

    def test_project_unmatched_auto_creates_rules(
        self, db_session: Session, sample_categories_yaml
    ):
        """Verify unmatched tags in project auto-create budget rules.

        When a project has transactions with tags not covered by existing
        rules, the view should auto-create rules for those tags.
        """
        svc = ProjectBudgetService(db_session)

        # Create project with only a total rule (no tag-specific rules)
        svc.add_rule(
            TOTAL_BUDGET, 10000, "TestProject", [ALL_TAGS], month=None, year=None
        )

        # Insert transactions with tags that have no rules
        txns = [
            CreditCardTransaction(
                id="cc_proj_1",
                date="2024-01-10",
                provider="isracard",
                account_name="Main Card",
                description="Project Item A",
                amount=-500.0,
                category="TestProject",
                tag="TagA",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            ),
            CreditCardTransaction(
                id="cc_proj_2",
                date="2024-01-15",
                provider="isracard",
                account_name="Main Card",
                description="Project Item B",
                amount=-300.0,
                category="TestProject",
                tag="TagB",
                source="credit_card_transactions",
                type="normal",
                status="completed",
            ),
        ]
        db_session.add_all(txns)
        db_session.commit()

        result = svc.get_project_budget_view("TestProject")

        # Should have total rule + auto-created rules for TagA and TagB
        rule_names = [r["rule"]["name"] for r in result["rules"]]
        assert TOTAL_BUDGET in rule_names
        assert "TagA" in rule_names
        assert "TagB" in rule_names

        # Verify rules were actually persisted in the database
        all_rules = svc.get_all_rules()
        project_rules = all_rules[all_rules["category"] == "TestProject"]
        assert len(project_rules) >= 3  # Total + TagA + TagB

    def test_budget_excludes_non_expenses(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify Salary, Ignore, Other Income, Investments, Liabilities excluded from budget.

        Non-expense categories should not appear in the budget view
        spending calculations.
        """
        svc = MonthlyBudgetService(db_session)
        svc.add_rule("Total Budget", 15000, TOTAL_BUDGET, [ALL_TAGS], month=1, year=2024)

        view = svc.get_monthly_budget_view(2024, 1)

        assert view is not None
        total_entry = view[0]
        total_data = total_entry["data"]

        # Verify no non-expense categories in the data
        categories_in_view = {
            tx["category"] for tx in total_data if tx.get("category")
        }
        non_expense = {"Salary", "Other Income", "Investments", "Liabilities"}
        assert categories_in_view.isdisjoint(non_expense), (
            f"Non-expense categories found in budget: {categories_in_view & non_expense}"
        )

        # Feb has Salary(+8500) and Other Income(+3500) which must be excluded
        svc.add_rule("Total Budget Feb", 15000, TOTAL_BUDGET, [ALL_TAGS], month=2, year=2024)
        view_feb = svc.get_monthly_budget_view(2024, 2)
        assert view_feb is not None
        feb_total = view_feb[0]
        feb_categories = {
            tx["category"] for tx in feb_total["data"] if tx.get("category")
        }
        assert "Salary" not in feb_categories
        assert "Other Income" not in feb_categories

    def test_budget_excludes_project_transactions(
        self,
        db_session: Session,
        seed_base_transactions,
        seed_project_transactions,
    ):
        """Verify project category transactions excluded from monthly budget.

        Transactions categorised as project categories (Wedding, Renovation)
        should not appear in the monthly budget view.
        """
        svc = MonthlyBudgetService(db_session)
        svc.add_rule("Total Budget", 50000, TOTAL_BUDGET, [ALL_TAGS], month=1, year=2024)

        view = svc.get_monthly_budget_view(2024, 1)

        assert view is not None
        total_entry = view[0]
        total_data = total_entry["data"]

        categories_in_view = {
            tx["category"] for tx in total_data if tx.get("category")
        }
        assert "Wedding" not in categories_in_view
        assert "Renovation" not in categories_in_view

        # Total should only reflect non-project expenses for Jan
        # Regular Jan expenses: 150+80+60+40+3000+15+10+250 = 3605
        assert total_entry["current_amount"] == pytest.approx(3605.0)

    def test_split_transaction_amounts_in_budget(
        self,
        db_session: Session,
        seed_base_transactions,
        seed_split_transactions,
    ):
        """Verify split children counted correctly, parents excluded.

        When include_split_parents=True, the budget should use split
        children amounts and exclude the parent from calculations.
        """
        svc = MonthlyBudgetService(db_session)
        svc.add_rule("Total Budget", 20000, TOTAL_BUDGET, [ALL_TAGS], month=2, year=2024)
        svc.add_rule("Food", 3000, "Food", [ALL_TAGS], month=2, year=2024)
        svc.add_rule("Home", 5000, "Home", [ALL_TAGS], month=2, year=2024)

        # With split parents included so they appear in data but excluded from calc
        view = svc.get_monthly_budget_view(2024, 2, include_split_parents=True)

        assert view is not None

        # Food rule: cc_feb_1(-180) + cc_feb_2(-120) + cash_feb_1(-18) = 318
        #   + split child cc_split_parent_1 Food/Groceries(-150) = 468
        food_entry = next(e for e in view if e["rule"]["name"] == "Food")
        assert food_entry["current_amount"] == pytest.approx(468.0)

        # Home rule: bank_feb_2(-3000 Rent) + split cc Home/Cleaning(-100) + split bank Home/Maintenance(-120) = 3220
        home_entry = next(e for e in view if e["rule"]["name"] == "Home")
        assert home_entry["current_amount"] == pytest.approx(3220.0)

        # Total should include splits but not double-count parents
        total_entry = next(e for e in view if e["rule"]["name"] == TOTAL_BUDGET)
        # Feb base: cc_feb_1(-180) + cc_feb_2(-120) + cc_feb_3(-55) + cc_feb_4(-45)
        #   + bank_feb_2(-3000) + cash_feb_1(-18) + cash_feb_2(-12) = 3430
        # Split children: (-150) + (-100) + (-50) + (-120) + (-80) = 500
        # Total = 3430 + 500 = 3930
        assert total_entry["current_amount"] == pytest.approx(3930.0)

    def test_pending_refunds_excluded(
        self, db_session: Session, seed_base_transactions
    ):
        """Verify pending refund transactions excluded from budget view.

        When a transaction is marked as pending refund, it should not
        be counted in the monthly budget view totals.
        """
        svc = MonthlyBudgetService(db_session)
        svc.add_rule("Total Budget", 15000, TOTAL_BUDGET, [ALL_TAGS], month=1, year=2024)

        # First get the view without any pending refunds
        view_before = svc.get_monthly_budget_view(2024, 1)
        total_before = view_before[0]["current_amount"]

        # Find the unique_id of cc_jan_5 (Office Depot -250) to mark as pending refund.
        # We use cc_jan_5 because it is the last CC transaction inserted, so its
        # unique_id is high enough not to collide with bank/cash unique_ids.
        from backend.services.transactions_service import TransactionsService

        txn_svc = TransactionsService(db_session)
        all_data = txn_svc.get_data_for_analysis()
        cc_jan_5 = all_data[all_data["id"] == "cc_jan_5"].iloc[0]
        cc_jan_5_uid = int(cc_jan_5["unique_id"])

        # Mark cc_jan_5 (-250) as pending refund
        pending_svc = PendingRefundsService(db_session)
        pending_svc.mark_as_pending_refund(
            source_type="transaction",
            source_id=cc_jan_5_uid,
            source_table="credit_card_transactions",
            expected_amount=250.0,
            notes="Expecting refund for Office Depot",
        )

        # Get view after marking pending refund
        view_after = svc.get_monthly_budget_view(2024, 1)
        total_after = view_after[0]["current_amount"]

        # Total should be reduced by 250 (the pending refund amount)
        assert total_after == pytest.approx(total_before - 250.0)
