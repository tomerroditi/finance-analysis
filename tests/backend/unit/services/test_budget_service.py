import pandas as pd
import pytest

from backend.constants.budget import (
    ALL_TAGS,
    AMOUNT,
    CATEGORY,
    ID,
    MONTH,
    NAME,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.models.budget import BudgetRule
from backend.services.budget_service import (
    BudgetService,
    MonthlyBudgetService,
    ProjectBudgetService,
)


@pytest.fixture(autouse=True)
def mock_categories_cache(sample_categories_yaml, monkeypatch):
    """Mock the categories cache to avoid filesystem dependency."""
    import backend.services.tagging_service as ts

    monkeypatch.setattr(ts, "_categories_cache", sample_categories_yaml)
    yield
    monkeypatch.setattr(ts, "_categories_cache", None)


class TestBudgetServiceBase:
    """Tests for the base BudgetService class."""

    def test_get_all_rules_parses_tags(self, db_session, seed_budget_rules):
        """Verify tags are parsed from semicolon-separated strings to lists."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        # The Food rule has tags="All Tags" which should become ["All Tags"]
        food_rule = rules.loc[rules[NAME] == "Food"]
        assert not food_rule.empty
        parsed_tags = food_rule.iloc[0][TAGS]
        assert isinstance(parsed_tags, list)
        assert parsed_tags == ["All Tags"]

    def test_add_rule_converts_tags_list(self, db_session):
        """Verify tags list is joined with semicolons before storage."""
        service = BudgetService(db_session)
        service.add_rule(
            name="Test Rule",
            amount=100.0,
            category="Food",
            tags=["Groceries", "Restaurants"],
            month=1,
            year=2024,
        )

        # Read raw from repository (tags stored as string)
        raw = service.budget_repository.read_all()
        stored_tags = raw.loc[raw[NAME] == "Test Rule"].iloc[0][TAGS]
        assert stored_tags == "Groceries;Restaurants"

    def test_update_rule_valid_fields(self, db_session, seed_budget_rules):
        """Verify update accepts name, amount, category, tags fields."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()
        food_rule_id = int(rules.loc[rules[NAME] == "Food"].iloc[0][ID])

        service.update_rule(food_rule_id, name="Food & Drink", amount=2500.0)

        updated_rules = service.get_all_rules()
        updated = updated_rules.loc[updated_rules[ID] == food_rule_id].iloc[0]
        assert updated[NAME] == "Food & Drink"
        assert updated[AMOUNT] == 2500.0

    def test_update_rule_invalid_field_raises(self, db_session, seed_budget_rules):
        """Verify AssertionError is raised for invalid field names."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()
        rule_id = int(rules.iloc[0][ID])

        with pytest.raises(AssertionError, match="Invalid fields"):
            service.update_rule(rule_id, invalid_field="value")

    def test_validate_rule_inputs_empty_name(self, db_session, seed_budget_rules):
        """Verify validation rejects empty name."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="",
            category="Food",
            tags=["Groceries"],
            amount=100.0,
            year=2024,
            month=1,
            id_=None,
        )
        assert valid is False
        assert "name" in msg.lower()

    def test_validate_rule_inputs_zero_amount(self, db_session, seed_budget_rules):
        """Verify validation rejects zero amount."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="New Rule",
            category="Food",
            tags=["Groceries"],
            amount=0,
            year=2024,
            month=1,
            id_=None,
        )
        assert valid is False
        assert "positive" in msg.lower()

    def test_validate_rule_inputs_duplicate_name(self, db_session, seed_budget_rules):
        """Verify validation rejects duplicate names in same month."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Food",
            category="Food",
            tags=["Groceries"],
            amount=100.0,
            year=2024,
            month=1,
            id_=None,
        )
        assert valid is False
        assert "already exists" in msg.lower()

    def test_validate_rule_inputs_exceeds_total(self, db_session):
        """Verify validation rejects when rules exceed total budget."""
        service = BudgetService(db_session)

        # Create a Total Budget rule with category="Total Budget"
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=1000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=6,
            year=2024,
        )
        # Create an existing rule using 800 of the budget
        service.add_rule(
            name="Existing",
            amount=800.0,
            category="Food",
            tags=["Groceries"],
            month=6,
            year=2024,
        )

        rules = service.get_all_rules()

        # Try to add another rule for 300, which would exceed 1000 total
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Over Budget",
            category="Transport",
            tags=["Gas"],
            amount=300.0,
            year=2024,
            month=6,
            id_=None,
        )
        assert valid is False
        assert "exceeded" in msg.lower()


class TestMonthlyBudgetService:
    """Tests for MonthlyBudgetService functionality."""

    def test_get_all_rules_monthly_only(
        self, db_session, seed_budget_rules, seed_project_transactions
    ):
        """Verify only monthly rules returned (not project rules)."""
        service = MonthlyBudgetService(db_session)
        rules = service.get_all_rules()

        # All returned rules should have non-null year and month
        assert not rules.empty
        assert rules[YEAR].notna().all()
        assert rules[MONTH].notna().all()

        # Project rules (Wedding Budget, Renovation Budget) should not appear
        names = rules[NAME].tolist()
        assert "Wedding Budget" not in names
        assert "Renovation Budget" not in names

    def test_get_month_rules(self, db_session, seed_budget_rules):
        """Verify filtering rules by year and month."""
        service = MonthlyBudgetService(db_session)
        rules = service.get_month_rules(2024, 1)

        assert len(rules) == 4
        assert set(rules[NAME].tolist()) == {
            "Total Budget",
            "Food",
            "Transport",
            "Entertainment",
        }

        # No rules for a different month
        empty_rules = service.get_month_rules(2024, 2)
        assert empty_rules.empty

    def test_create_rule_with_validation(self, db_session):
        """Verify create_rule validates before adding."""
        service = MonthlyBudgetService(db_session)

        # Set up Total Budget with proper category for validation to work
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )

        # Valid rule should succeed (within budget)
        service.create_rule(
            name="Home Expenses",
            amount=500.0,
            category="Home",
            tags=["Rent"],
            month=1,
            year=2024,
        )
        rules = service.get_month_rules(2024, 1)
        assert "Home Expenses" in rules[NAME].tolist()

        # Invalid rule (exceeds total budget) should raise ValueError
        with pytest.raises(ValueError, match="exceeded"):
            service.create_rule(
                name="Way Too Much",
                amount=50000.0,
                category="Other",
                tags=["Misc"],
                month=1,
                year=2024,
            )

    def test_copy_last_month_rules(self, db_session, seed_budget_rules):
        """Verify rules copied from previous month."""
        service = MonthlyBudgetService(db_session)
        all_rules = service.get_all_rules()

        result = service.copy_last_month_rules(2024, 2, all_rules)

        assert result is not None
        assert "Copied" in result
        assert "4" in result  # 4 rules from Jan

        feb_rules = service.get_month_rules(2024, 2)
        assert len(feb_rules) == 4
        feb_names = set(feb_rules[NAME].tolist())
        assert feb_names == {"Total Budget", "Food", "Transport", "Entertainment"}

    def test_copy_last_month_rules_none_when_empty(self, db_session):
        """Verify None returned when previous month has no rules."""
        service = MonthlyBudgetService(db_session)
        all_rules = service.get_all_rules()

        result = service.copy_last_month_rules(2024, 5, all_rules)
        assert result is None

    def test_get_monthly_budget_view(self, db_session, seed_base_transactions):
        """Verify budget view computes current_amount per rule."""
        service = MonthlyBudgetService(db_session)

        # Create budget rules with category="Total Budget" for the Total Budget rule
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )

        view = service.get_monthly_budget_view(2024, 1)
        assert view is not None
        assert len(view) >= 2

        # Total Budget should be the first entry
        total_entry = view[0]
        assert total_entry["rule"][NAME] == TOTAL_BUDGET
        assert total_entry["current_amount"] > 0
        assert total_entry["allow_delete"] is False

        # Food rule
        food_entry = next(
            (v for v in view if v["rule"][NAME] == "Food"), None
        )
        assert food_entry is not None
        # Jan 2024 food: cc_jan_1(-150) + cc_jan_2(-80) + cash_jan_1(-15) = 245
        assert food_entry["current_amount"] == 245.0
        assert food_entry["allow_edit"] is True
        assert food_entry["allow_delete"] is True

    def test_get_monthly_budget_view_other_expenses(
        self, db_session, seed_base_transactions
    ):
        """Verify 'Other Expenses' catch-all created for unmatched transactions."""
        service = MonthlyBudgetService(db_session)

        # Create Total Budget + Food rule only; other categories will become "Other Expenses"
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )

        view = service.get_monthly_budget_view(2024, 1)
        assert view is not None

        # There should be an "Other Expenses" entry for Transport, Entertainment, Home, Other, etc.
        other_entry = next(
            (v for v in view if v["rule"][NAME] == "Other Expenses"), None
        )
        assert other_entry is not None
        assert other_entry["allow_edit"] is False
        assert other_entry["allow_delete"] is False
        assert other_entry["current_amount"] > 0

    def test_get_monthly_analysis(self, db_session, seed_base_transactions):
        """Verify full analysis includes rules, project spending, pending refunds."""
        service = MonthlyBudgetService(db_session)

        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=1,
            year=2024,
        )

        analysis = service.get_monthly_analysis(2024, 1)
        assert "rules" in analysis
        assert "project_spending" in analysis
        assert "pending_refunds" in analysis
        assert "items" in analysis["pending_refunds"]
        assert "total_expected" in analysis["pending_refunds"]
        assert isinstance(analysis["rules"], list)
        assert len(analysis["rules"]) > 0

    def test_delete_rules_by_month(self, db_session, seed_budget_rules):
        """Verify all rules for a month are deleted."""
        service = MonthlyBudgetService(db_session)

        # Confirm rules exist for Jan 2024
        jan_rules = service.get_month_rules(2024, 1)
        assert len(jan_rules) == 4

        service.delete_rules_by_month(2024, 1)

        # Confirm rules are gone
        jan_rules_after = service.get_month_rules(2024, 1)
        assert jan_rules_after.empty


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

    def test_create_project(self, db_session):
        """Verify creating a project creates total budget + tag rules."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        rules = service.get_all_rules()
        wedding_rules = rules.loc[rules[CATEGORY] == "Wedding"]
        assert not wedding_rules.empty

        # Total Budget rule
        total = wedding_rules.loc[wedding_rules[NAME] == TOTAL_BUDGET]
        assert not total.empty
        assert total.iloc[0][AMOUNT] == 50000.0
        assert total.iloc[0][TAGS] == [ALL_TAGS]

        # Tag rules: one per tag in sample_categories_yaml["Wedding"] = ["Venue", "Catering"]
        tag_names = wedding_rules.loc[wedding_rules[NAME] != TOTAL_BUDGET][NAME].tolist()
        assert "Venue" in tag_names
        assert "Catering" in tag_names
        # Each tag rule starts with amount 0
        for _, rule in wedding_rules.loc[wedding_rules[NAME] != TOTAL_BUDGET].iterrows():
            assert rule[AMOUNT] == 0

    def test_get_all_projects_names(self, db_session):
        """Verify project names list is returned correctly."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)
        service.create_project("Renovation", 25000.0)

        names = service.get_all_projects_names()
        assert "Wedding" in names
        assert "Renovation" in names
        assert len(names) == 2

    def test_delete_project(self, db_session):
        """Verify deleting removes all project rules."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        # Confirm rules exist
        rules_before = service.get_all_rules()
        assert not rules_before.loc[rules_before[CATEGORY] == "Wedding"].empty

        service.delete_project("Wedding")

        rules_after = service.get_all_rules()
        wedding_after = rules_after.loc[rules_after[CATEGORY] == "Wedding"]
        assert wedding_after.empty

    def test_get_project_transactions(
        self, db_session, seed_project_transactions
    ):
        """Verify filtering transactions by project category."""
        service = ProjectBudgetService(db_session)

        wedding_txns = service.get_project_transactions("Wedding")
        assert not wedding_txns.empty

        # All returned transactions should have category "Wedding"
        categories = wedding_txns[TransactionsTableFields.CATEGORY.value].unique()
        assert list(categories) == ["Wedding"]

        # Verify transaction count: 5 wedding transactions in seed
        assert len(wedding_txns) == 5

        reno_txns = service.get_project_transactions("Renovation")
        assert not reno_txns.empty
        assert len(reno_txns) == 5
