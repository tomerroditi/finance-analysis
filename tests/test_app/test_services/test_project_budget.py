import pandas as pd
import pytest

from backend.naming_conventions import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    NAME,
    TAGS,
    TransactionsTableFields,
)
from backend.services.budget_service import ProjectBudgetService


class TestProjectBudgetService:
    """Tests for ProjectBudgetService functionality."""

    def test_get_project_budget_view_with_unmatched_transactions(self, db_session):
        """
        Verify that transactions not matching any specific tag rule are included
        in an "Other" category and counted towards the total.
        """
        service = ProjectBudgetService(db_session)

        # 1. Setup: Create a project "Wedding"
        project_name = "Wedding"
        service.create_project(project_name, 10000.0)

        # Ensure "Other" rule is deleted if it was auto-created, to test unmatched behavior
        service.delete_project_tag_rule(project_name, "Other")

        # Create a specific rule for "Venue"
        service.add_rule(
            name="Venue Rule",
            amount=5000.0,
            category=project_name,
            tags=["Venue"],
            month=None,
            year=None,
        )

        # 2. Data: Insert transactions directly into DB (mocking via table_mock would be ideal,
        # but here we can mock the transactions_service.get_data_for_analysis return value
        # OR insert into the in-memory DB if the service uses real DB calls for transactions)

        # Since ProjectBudgetService uses transactions_service.get_data_for_analysis,
        # and that likely queries the DB, we can insert into the DB table if available.
        # However, looking at the service, it instantiates TransactionsService(db).

        # Let's mock the transactions_service.get_data_for_analysis method specifically
        # to return our test dataframe.
        # This isolates the ProjectBudgetService logic we want to test.

        test_transactions = pd.DataFrame(
            [
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2023-01-01"),
                    TransactionsTableFields.CATEGORY.value: project_name,
                    TransactionsTableFields.TAG.value: "Venue",
                    TransactionsTableFields.AMOUNT.value: -1000.0,  # Expense
                    TransactionsTableFields.UNIQUE_ID.value: "tx1",
                    "type": "credit_card",
                },
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2023-01-02"),
                    TransactionsTableFields.CATEGORY.value: project_name,
                    TransactionsTableFields.TAG.value: "Other",  # Unmatched tag
                    TransactionsTableFields.AMOUNT.value: -200.0,  # Expense
                    TransactionsTableFields.UNIQUE_ID.value: "tx2",
                    "type": "credit_card",
                },
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2023-01-03"),
                    TransactionsTableFields.CATEGORY.value: project_name,
                    TransactionsTableFields.TAG.value: "Random",  # Unmatched tag
                    TransactionsTableFields.AMOUNT.value: -50.0,  # Expense
                    TransactionsTableFields.UNIQUE_ID.value: "tx3",
                    "type": "credit_card",
                },
            ]
        )

        # Mocking the transactions service within the budget service instance
        # We need to monkeypatch the get_data_for_analysis method on the service.transactions_service instance

        service.transactions_service.get_data_for_analysis = (
            lambda include_split_parents: test_transactions
        )

        # 3. Action: Call get_project_budget_view (which we are about to implement)
        # Note: The method get_project_budget_view doesn't exist yet in the code,
        # so this test will fail initially or crash.
        # But we can verify the behavior we expect once implemented.
        # For now, let's call the proposed method name.

        try:
            view_result = service.get_project_budget_view(project_name)
        except AttributeError:
            pytest.fail("Method get_project_budget_view not implemented yet")

        # 4. Assertions

        # Check total spent
        # Total spent should be 1000 + 200 + 50 = 1250
        assert view_result["total_spent"] == 1250.0

        rules_view = view_result["rules"]

        # We expect 4 entries in 'rules':
        # 1. Total Budget Rule (implicit/explicit)
        # 2. Venue Rule
        # 3. "Other" Rule (synthetic)
        # 4. "Random" Rule (synthetic)

        # Find Venue rule
        venue_rule = next(
            (r for r in rules_view if r["rule"][NAME] == "Venue Rule"), None
        )
        assert venue_rule is not None
        assert venue_rule["current_amount"] == 1000.0
        assert len(venue_rule["data"]) == 1

        # Find "Other" tag rule (which should now be auto-created and real)
        other_tag_rule = next(
            (r for r in rules_view if r["rule"][NAME] == "Other"), None
        )
        assert other_tag_rule is not None
        assert other_tag_rule["current_amount"] == 200.0
        assert len(other_tag_rule["data"]) == 1
        assert other_tag_rule["rule"][TAGS] == ["Other"]
        # New assertions for auto-created rules
        assert other_tag_rule["allow_edit"] is True
        assert other_tag_rule["allow_delete"] is True
        # ID should not be the old synthetic format
        assert "Synthetic" not in str(other_tag_rule["rule"][ID])

        # Find "Random" tag rule (which should now be auto-created and real)
        random_tag_rule = next(
            (r for r in rules_view if r["rule"][NAME] == "Random"), None
        )
        assert random_tag_rule is not None
        assert random_tag_rule["current_amount"] == 50.0
        assert len(random_tag_rule["data"]) == 1
        assert random_tag_rule["rule"][TAGS] == ["Random"]
        assert random_tag_rule["allow_edit"] is True
        assert random_tag_rule["allow_delete"] is True
        assert "Synthetic" not in str(random_tag_rule["rule"][ID])

        # Verify NO "Other Expenses" catch-all rule
        catch_all = next(
            (r for r in rules_view if r["rule"][NAME] == "Other Expenses"), None
        )
        assert catch_all is None
