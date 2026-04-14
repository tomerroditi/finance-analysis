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

        assert result == "Copied 4 rules from 2024-1"

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
        assert len(view) == 3  # Total Budget + Food + Other Expenses

        # Total Budget should be the first entry
        total_entry = view[0]
        assert total_entry["rule"][NAME] == TOTAL_BUDGET
        # Jan 2024 expenses (non-Ignore/Salary/Other Income/Investments/Liabilities/CC):
        # cc_jan_1(-150) + cc_jan_2(-80) + cc_jan_3(-60) + cc_jan_4(-40) + cc_jan_5(-250)
        # + bank_jan_2(-3000) + cash_jan_1(-15) + cash_jan_2(-10)
        # Ignore transactions net to 0. Total = 3605.0
        assert total_entry["current_amount"] == 3605.0
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
        # Other Expenses = Transport(60+10) + Entertainment(40) + Home(3000) + Other(250) = 3360.0
        assert other_entry["current_amount"] == 3360.0

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
        assert isinstance(analysis["rules"], list)
        assert len(analysis["rules"]) == 3  # Total Budget + Food + Other Expenses
        assert analysis["pending_refunds"]["items"] == []
        assert analysis["pending_refunds"]["total_expected"] == 0.0

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

        # Mock transactions_service.get_data_for_analysis to return controlled test data
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

        service.transactions_service.get_data_for_analysis = (
            lambda include_split_parents: test_transactions
        )

        view_result = service.get_project_budget_view(project_name)

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


class TestBudgetServiceValidation:
    """Extended tests for budget rule input validation edge cases."""

    def test_validate_null_category_rejected(self, db_session, seed_budget_rules):
        """Verify validation rejects None category."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="New Rule",
            category=None,
            tags=["Groceries"],
            amount=100.0,
            year=2024,
            month=1,
            id_=None,
        )
        assert valid is False
        assert "category" in msg.lower()

    def test_validate_no_tags_rejected(self, db_session, seed_budget_rules):
        """Verify validation rejects empty tags list."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="New Rule",
            category="Food",
            tags=[],
            amount=100.0,
            year=2024,
            month=1,
            id_=None,
        )
        assert valid is False
        assert "tag" in msg.lower()

    def test_validate_all_tags_with_existing_specific_tag_rules(self, db_session):
        """Verify ALL_TAGS rejected when specific tag rules already exist for category."""
        service = BudgetService(db_session)

        # Create Total Budget
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=3,
            year=2024,
        )
        # Create a specific tag rule for Food/Groceries
        service.add_rule(
            name="Food Groceries",
            amount=500.0,
            category="Food",
            tags=["Groceries"],
            month=3,
            year=2024,
        )

        rules = service.get_all_rules()

        # Try to add ALL_TAGS for Food, which already has a specific tag rule
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Food All",
            category="Food",
            tags=[ALL_TAGS],
            amount=1000.0,
            year=2024,
            month=3,
            id_=None,
        )
        assert valid is False
        assert "all_tags" in msg.lower() or ALL_TAGS in msg

    def test_validate_total_budget_below_sum_rejected(self, db_session):
        """Verify Total Budget cannot be set below sum of existing rules."""
        service = BudgetService(db_session)

        # Create Total Budget
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=5000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=4,
            year=2024,
        )
        # Create rules that sum to 3000
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=4,
            year=2024,
        )
        service.add_rule(
            name="Transport",
            amount=1000.0,
            category="Transport",
            tags=[ALL_TAGS],
            month=4,
            year=2024,
        )

        rules = service.get_all_rules()
        total_rule = rules.loc[
            (rules[NAME] == TOTAL_BUDGET)
            & (rules[YEAR] == 2024)
            & (rules[MONTH] == 4)
        ]
        total_id = int(total_rule.iloc[0][ID])

        # Try to set Total Budget to 2000, which is below sum of 3000
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name=TOTAL_BUDGET,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            amount=2000.0,
            year=2024,
            month=4,
            id_=total_id,
        )
        assert valid is False
        assert "greater" in msg.lower()

    def test_validate_update_same_values_returns_true(self, db_session, seed_budget_rules):
        """Verify updating a rule with identical values returns True (no-op)."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()

        food_rule = rules.loc[rules[NAME] == "Food"].iloc[0]
        rule_id = int(food_rule[ID])

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name=food_rule[NAME],
            category=food_rule[CATEGORY],
            tags=food_rule[TAGS],
            amount=food_rule[AMOUNT],
            year=2024,
            month=1,
            id_=rule_id,
        )
        assert valid is True
        assert msg == ""


class TestMonthlyBudgetServiceExtended:
    """Extended tests for MonthlyBudgetService."""

    def test_get_available_tags_removes_all_tags_category(self, db_session):
        """Verify category is removed from available when ALL_TAGS rule exists."""
        service = MonthlyBudgetService(db_session)

        # Create a rule with ALL_TAGS for Food
        service.add_rule(
            name="Food All",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=5,
            year=2024,
        )

        rules = service.get_month_rules(2024, 5)
        available = service.get_available_tags_for_each_category(rules)

        # Food should be completely removed since ALL_TAGS is used
        assert "Food" not in available

    def test_get_available_tags_reduces_specific_tags(self, db_session):
        """Verify specific used tags are excluded from available list."""
        service = MonthlyBudgetService(db_session)

        # Create a rule that uses specific tags
        service.add_rule(
            name="Food Groceries",
            amount=1000.0,
            category="Food",
            tags=["Groceries"],
            month=5,
            year=2024,
        )

        rules = service.get_month_rules(2024, 5)
        available = service.get_available_tags_for_each_category(rules)

        # Food should still be present but without "Groceries"
        assert "Food" in available
        assert "Groceries" not in available["Food"]
        # Remaining tags should still be there
        assert "Restaurants" in available["Food"]
        assert "Coffee" in available["Food"]

    def test_copy_last_month_rules_year_boundary(self, db_session):
        """Verify copying from December of previous year when month is January."""
        service = MonthlyBudgetService(db_session)

        # Create rules for December 2023
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=8000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=12,
            year=2023,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=12,
            year=2023,
        )

        all_rules = service.get_all_rules()
        result = service.copy_last_month_rules(2024, 1, all_rules)

        assert result == "Copied 2 rules from 2023-12"

        jan_rules = service.get_month_rules(2024, 1)
        assert len(jan_rules) == 2
        names = set(jan_rules[NAME].tolist())
        assert names == {TOTAL_BUDGET, "Food"}


class TestProjectBudgetServiceExtended:
    """Extended tests for ProjectBudgetService."""

    def test_get_rules_for_nonexistent_project_raises(self, db_session):
        """Verify ValueError raised when project has no rules."""
        service = ProjectBudgetService(db_session)

        with pytest.raises(ValueError, match="not found"):
            service.get_rules_for_project("Nonexistent Project")

    def test_update_project_total_budget_via_rule(self, db_session):
        """Verify updating the total budget for an existing project via update_rule."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        # Find the Total Budget rule and update it directly via update_rule
        rules = service.get_rules_for_project("Wedding")
        total_rule = rules.loc[
            rules[TAGS].apply(
                lambda x: [t.lower() for t in x] == [ALL_TAGS.lower()]
            )
        ]
        assert not total_rule.empty
        rule_id = int(total_rule.iloc[0][ID])

        service.update_rule(rule_id, amount=75000.0)

        updated_rules = service.get_rules_for_project("Wedding")
        updated_total = updated_rules.loc[
            updated_rules[TAGS].apply(
                lambda x: [t.lower() for t in x] == [ALL_TAGS.lower()]
            )
        ]
        assert not updated_total.empty
        assert updated_total.iloc[0][AMOUNT] == 75000.0

    def test_get_available_categories_for_new_project(self, db_session):
        """Verify available categories exclude existing projects."""
        service = ProjectBudgetService(db_session)

        # Before any projects, all categories should be available
        available_before = service.get_available_categories_for_new_project()
        assert "Wedding" in available_before
        assert "Renovation" in available_before

        # Create a project
        service.create_project("Wedding", 50000.0)

        # Now Wedding should no longer be available
        available_after = service.get_available_categories_for_new_project()
        assert "Wedding" not in available_after
        assert "Renovation" in available_after

    def test_get_available_categories_excludes_all_projects(self, db_session):
        """Verify multiple created projects are all excluded from available list."""
        service = ProjectBudgetService(db_session)

        service.create_project("Wedding", 50000.0)
        service.create_project("Renovation", 25000.0)

        available = service.get_available_categories_for_new_project()
        assert "Wedding" not in available
        assert "Renovation" not in available
        # Other categories should still be available
        assert "Food" in available
        assert "Transport" in available


class TestAutoFillEmptyMonths:
    """Tests for auto_fill_empty_months method."""

    def test_fills_current_month_from_previous(self, db_session):
        """Verify rules are copied from the latest month with rules to the current month."""
        service = MonthlyBudgetService(db_session)

        # Create rules for January 2026
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 1, 2026)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 1, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)

        assert result is not None
        assert "January 2026" in result

        # February and March should both have rules now
        feb_rules = service.get_month_rules(2026, 2)
        mar_rules = service.get_month_rules(2026, 3)
        assert len(feb_rules) == 2
        assert len(mar_rules) == 2
        assert set(feb_rules[NAME].tolist()) == {TOTAL_BUDGET, "Food"}
        assert set(mar_rules[NAME].tolist()) == {TOTAL_BUDGET, "Food"}

    def test_no_rules_anywhere_returns_none(self, db_session):
        """Verify None returned when no monthly rules exist at all."""
        service = MonthlyBudgetService(db_session)
        budget_rules = service.get_all_rules()

        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None

    def test_current_month_has_rules_returns_none(self, db_session):
        """Verify no-op when the current month already has rules."""
        service = MonthlyBudgetService(db_session)

        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 3, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None

    def test_skips_months_that_already_have_rules(self, db_session):
        """Verify months with existing rules are not overwritten."""
        service = MonthlyBudgetService(db_session)

        # Jan has 2 rules, Feb has 1 custom rule, Mar is empty
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 1, 2026)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 1, 2026)
        service.add_rule(TOTAL_BUDGET, 9000.0, TOTAL_BUDGET, [ALL_TAGS], 2, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)

        assert result is not None
        # Feb should still have its 1 custom rule, not overwritten
        feb_rules = service.get_month_rules(2026, 2)
        assert len(feb_rules) == 1
        assert feb_rules.iloc[0][AMOUNT] == 9000.0

        # Mar gets 1 rule copied from Feb (the latest month with rules
        # before current_month).
        mar_rules = service.get_month_rules(2026, 3)
        assert len(mar_rules) == 1
        assert mar_rules.iloc[0][AMOUNT] == 9000.0

    def test_year_boundary_fill(self, db_session):
        """Verify filling across year boundary (Dec -> Jan)."""
        service = MonthlyBudgetService(db_session)

        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 11, 2025)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 11, 2025)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 2, budget_rules)

        assert result is not None
        assert "November 2025" in result

        dec_rules = service.get_month_rules(2025, 12)
        jan_rules = service.get_month_rules(2026, 1)
        feb_rules = service.get_month_rules(2026, 2)
        assert len(dec_rules) == 2
        assert len(jan_rules) == 2
        assert len(feb_rules) == 2

    def test_ignores_future_months(self, db_session):
        """Verify rules in future months are not used as source."""
        service = MonthlyBudgetService(db_session)

        # Only rules in a future month (Dec 2026), none before current (Mar 2026)
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 12, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None


class TestUpdateRuleTagConversion:
    """Tests for update_rule tag list-to-string conversion (line 128)."""

    def test_update_rule_converts_tags_list_to_string(self, db_session, seed_budget_rules):
        """Verify update_rule joins a tags list with semicolons before storage."""
        service = BudgetService(db_session)
        rules = service.get_all_rules()
        food_rule_id = int(rules.loc[rules[NAME] == "Food"].iloc[0][ID])

        service.update_rule(food_rule_id, tags=["Groceries", "Restaurants"])

        raw = service.budget_repository.read_all()
        stored_tags = raw.loc[raw[NAME] == "Food"].iloc[0][TAGS]
        assert stored_tags == "Groceries;Restaurants"


class TestValidateProjectRuleNameUniqueness:
    """Tests for project rule name uniqueness check (lines 198-206)."""

    def test_duplicate_project_rule_name_rejected(self, db_session):
        """Verify validation rejects duplicate names among project rules."""
        service = BudgetService(db_session)
        service.add_rule(
            name="Venue",
            amount=5000.0,
            category="Wedding",
            tags=["Venue"],
            month=None,
            year=None,
        )
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Venue",
            category="Wedding",
            tags=["Venue"],
            amount=3000.0,
            year=None,
            month=None,
            id_=None,
        )
        assert valid is False
        assert "already exists" in msg.lower()

    def test_duplicate_project_rule_name_allowed_for_same_id(self, db_session):
        """Verify updating a project rule with same name passes uniqueness check."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=50000.0,
            category="Wedding",
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )
        service.add_rule(
            name="Venue",
            amount=5000.0,
            category="Wedding",
            tags=["Venue"],
            month=None,
            year=None,
        )
        rules = service.get_all_rules()
        venue_id = int(
            rules.loc[
                (rules[NAME] == "Venue") & rules[YEAR].isnull()
            ].iloc[0][ID]
        )

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Venue",
            category="Wedding",
            tags=["Venue"],
            amount=8000.0,
            year=None,
            month=None,
            id_=venue_id,
        )
        assert valid is True


class TestValidateProjectBudgetHierarchy:
    """Tests for project budget hierarchy validation (lines 231-253)."""

    def test_project_total_budget_below_tag_rules_sum_rejected(self, db_session):
        """Verify project total budget cannot be set below sum of tag rules."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category="Wedding",
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )
        service.add_rule(
            name="Venue",
            amount=5000.0,
            category="Wedding",
            tags=["Venue"],
            month=None,
            year=None,
        )
        service.add_rule(
            name="Catering",
            amount=4000.0,
            category="Wedding",
            tags=["Catering"],
            month=None,
            year=None,
        )
        rules = service.get_all_rules()
        total_id = int(
            rules.loc[
                (rules[NAME] == TOTAL_BUDGET)
                & rules[YEAR].isnull()
                & (rules[CATEGORY] == "Wedding")
            ].iloc[0][ID]
        )

        # Try to set total to 5000, below sum of 9000
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name=TOTAL_BUDGET,
            category="Wedding",
            tags=[ALL_TAGS],
            amount=5000.0,
            year=None,
            month=None,
            id_=total_id,
        )
        assert valid is False
        assert "greater" in msg.lower()

    def test_project_tag_rule_exceeds_total_rejected(self, db_session):
        """Verify project tag rule that would exceed total budget is rejected."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category="Wedding",
            tags=[ALL_TAGS],
            month=None,
            year=None,
        )
        service.add_rule(
            name="Venue",
            amount=6000.0,
            category="Wedding",
            tags=["Venue"],
            month=None,
            year=None,
        )
        rules = service.get_all_rules()
        venue_id = int(
            rules.loc[
                (rules[NAME] == "Venue") & rules[YEAR].isnull()
            ].iloc[0][ID]
        )

        # Try to update Venue to 11000, exceeding total of 10000
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Venue",
            category="Wedding",
            tags=["Venue"],
            amount=11000.0,
            year=None,
            month=None,
            id_=venue_id,
        )
        assert valid is False
        assert "exceeded" in msg.lower()


class TestValidateMonthlyBudgetHierarchyAndCap:
    """Tests for monthly budget hierarchy and cap checks (lines 271, 284)."""

    def test_update_monthly_rule_subtracts_old_amount(self, db_session):
        """Verify updating a monthly rule subtracts old amount before checking cap."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=5000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=7,
            year=2024,
        )
        service.add_rule(
            name="Food",
            amount=2000.0,
            category="Food",
            tags=[ALL_TAGS],
            month=7,
            year=2024,
        )
        service.add_rule(
            name="Transport",
            amount=2000.0,
            category="Transport",
            tags=[ALL_TAGS],
            month=7,
            year=2024,
        )
        rules = service.get_all_rules()
        food_id = int(
            rules.loc[
                (rules[NAME] == "Food")
                & (rules[YEAR] == 2024)
                & (rules[MONTH] == 7)
            ].iloc[0][ID]
        )

        # Update Food from 2000 to 2500 -- total would be 2500+2000=4500 < 5000
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Food",
            category="Food",
            tags=[ALL_TAGS],
            amount=2500.0,
            year=2024,
            month=7,
            id_=food_id,
        )
        assert valid is True

    def test_monthly_all_tags_rejected_when_category_has_rules(self, db_session):
        """Verify ALL_TAGS rejected when other rules exist for same monthly category."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=8,
            year=2024,
        )
        service.add_rule(
            name="Food Groceries",
            amount=500.0,
            category="Food",
            tags=["Groceries"],
            month=8,
            year=2024,
        )
        rules = service.get_all_rules()

        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Food All",
            category="Food",
            tags=[ALL_TAGS],
            amount=1000.0,
            year=2024,
            month=8,
            id_=None,
        )
        assert valid is False
        assert ALL_TAGS in msg

    def test_monthly_all_tags_allowed_when_updating_self(self, db_session):
        """Verify ALL_TAGS rule can update itself without triggering the mixing check."""
        service = BudgetService(db_session)
        service.add_rule(
            name=TOTAL_BUDGET,
            amount=10000.0,
            category=TOTAL_BUDGET,
            tags=[ALL_TAGS],
            month=8,
            year=2024,
        )
        service.add_rule(
            name="Food All",
            amount=500.0,
            category="Food",
            tags=[ALL_TAGS],
            month=8,
            year=2024,
        )
        rules = service.get_all_rules()
        food_id = int(
            rules.loc[
                (rules[NAME] == "Food All")
                & (rules[YEAR] == 2024)
                & (rules[MONTH] == 8)
            ].iloc[0][ID]
        )

        # Updating existing ALL_TAGS rule should pass (only that rule for Food)
        valid, msg = BudgetService.validate_rule_inputs(
            budget_rules=rules,
            name="Food All",
            category="Food",
            tags=[ALL_TAGS],
            amount=800.0,
            year=2024,
            month=8,
            id_=food_id,
        )
        assert valid is True


class TestGetAvailableTagsCategoryRemoval:
    """Tests for category removal when all tags used (line 351)."""

    def test_category_removed_when_all_specific_tags_used(self, db_session):
        """Verify category is removed when all its specific tags are allocated to rules."""
        service = MonthlyBudgetService(db_session)

        # Food has tags: Groceries, Restaurants, Coffee
        # Use all three with individual rules
        service.add_rule("Food Groceries", 500.0, "Food", ["Groceries"], 9, 2024)
        service.add_rule("Food Restaurants", 500.0, "Food", ["Restaurants"], 9, 2024)
        service.add_rule("Food Coffee", 200.0, "Food", ["Coffee"], 9, 2024)

        rules = service.get_month_rules(2024, 9)
        available = service.get_available_tags_for_each_category(rules)

        # All Food tags used, so Food category should be removed entirely
        assert "Food" not in available


class TestGetMonthlyAnalysisAutoFill:
    """Tests for get_monthly_analysis auto-fill empty months (lines 599-602)."""

    def test_monthly_analysis_auto_fills_current_month(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """Verify get_monthly_analysis auto-fills the current calendar month."""
        from datetime import date as date_cls
        from unittest.mock import patch

        service = MonthlyBudgetService(db_session)

        # Create rules for a past month
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 2, 2026)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 2, 2026)

        # Patch date.today() to return March 2026 (the current month for the test)
        fake_today = date_cls(2026, 3, 15)
        with patch("backend.services.budget_service.date") as mock_date:
            mock_date.today.return_value = fake_today
            mock_date.side_effect = lambda *args, **kw: date_cls(*args, **kw)

            analysis = service.get_monthly_analysis(2026, 3)

        assert analysis["copied_from"] is not None
        assert "February 2026" in analysis["copied_from"]
        assert analysis["rules"] is not None


class TestGetFilteredExpensesDateConversion:
    """Tests for get_filtered_expenses date conversion (line 657)."""

    def test_expense_dates_are_converted_to_datetime(self, db_session, seed_base_transactions):
        """Verify get_filtered_expenses returns dates as pandas Timestamps."""
        service = MonthlyBudgetService(db_session)
        expenses = service.get_filtered_expenses()

        assert not expenses.empty
        date_col = TransactionsTableFields.DATE.value
        assert pd.api.types.is_datetime64_any_dtype(expenses[date_col])


class TestGetMonthlyBudgetViewNoRulesExit:
    """Tests for no rules early exit in get_monthly_budget_view (line 744)."""

    def test_returns_none_when_no_rules_for_month(self, db_session, seed_base_transactions):
        """Verify get_monthly_budget_view returns None when no rules exist for the month."""
        service = MonthlyBudgetService(db_session)

        # No budget rules created for February 2024
        result = service.get_monthly_budget_view(2024, 2)
        assert result is None


class TestGetMonthlyProjectTransactionsNoProjects:
    """Tests for no projects early exit (lines 858-864)."""

    def test_returns_none_when_no_project_categories(self, db_session, seed_base_transactions):
        """Verify get_monthly_project_transactions returns None without project rules."""
        service = MonthlyBudgetService(db_session)

        # No project rules exist (seed_base_transactions has no project budget rules)
        result = service.get_monthly_project_transactions(2024, 1)
        assert result is None

    def test_returns_transactions_when_projects_exist(
        self, db_session, seed_base_transactions, seed_project_transactions
    ):
        """Verify project transactions returned when project rules and matching data exist."""
        service = MonthlyBudgetService(db_session)

        result = service.get_monthly_project_transactions(2024, 1)
        assert result is not None
        # January 2024 has wedding (cc_wedding_1) and renovation (cc_reno_1) project txns
        assert len(result) == 2


class TestGetMonthlyProjectSpendingSummary:
    """Tests for project summary construction (lines 897-913)."""

    def test_project_spending_summary_groups_by_category(
        self, db_session, seed_base_transactions, seed_project_transactions
    ):
        """Verify project spending summary groups transactions by project category."""
        service = MonthlyBudgetService(db_session)

        summary = service.get_monthly_project_spending_summary(2024, 2)

        assert "projects" in summary
        assert len(summary["projects"]) > 0
        assert "total_spent" in summary

        # February 2024 has wedding (cc_wedding_2, bank_wedding_1) and
        # renovation (bank_reno_1, cc_reno_2) transactions
        project_names = [p["category"] for p in summary["projects"]]
        assert "Wedding" in project_names
        assert "Renovation" in project_names

        wedding = next(p for p in summary["projects"] if p["category"] == "Wedding")
        # cc_wedding_2(-800) + bank_wedding_1(-15000) = 15800 spent
        assert wedding["spent"] == 15800.0

    def test_project_spending_summary_empty_when_no_projects(
        self, db_session, seed_base_transactions
    ):
        """Verify empty projects list returned when no project budget rules exist."""
        service = MonthlyBudgetService(db_session)

        summary = service.get_monthly_project_spending_summary(2024, 1)
        assert summary == {"projects": []}


class TestUpdateProject:
    """Tests for update_project total rule lookup and update (lines 1004-1007)."""

    def test_update_project_changes_total_budget(self, db_session):
        """Verify update_project finds and updates the total budget rule amount."""
        service = ProjectBudgetService(db_session)
        service.create_project("Other", 50000.0)

        service.update_project("Other", 75000.0)

        rules = service.get_rules_for_project("Other")
        total_rule = rules.loc[rules["tags"].apply(lambda x: x == ["all_tags"])]
        assert len(total_rule) == 1
        assert total_rule.iloc[0]["amount"] == 75000.0


class TestGetAvailableCategoriesFiltering:
    """Tests for available categories filtering (line 1136)."""

    def test_available_categories_excludes_existing_projects(self, db_session):
        """Verify categories used by existing projects are filtered out."""
        service = ProjectBudgetService(db_session)

        all_cats = service.get_available_categories_for_new_project()
        assert "Wedding" in all_cats

        service.create_project("Wedding", 50000.0)

        filtered_cats = service.get_available_categories_for_new_project()
        assert "Wedding" not in filtered_cats
        # Other categories remain
        assert "Renovation" in filtered_cats
        assert "Food" in filtered_cats


class TestGetProjectBudgetViewConstruction:
    """Tests for project budget rule view construction (lines 1171, 1208, 1229)."""

    def test_project_view_constructs_tag_rule_entries(self, db_session):
        """Verify project budget view includes per-tag rule entries with correct amounts."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        # Create test transactions matching the project
        test_transactions = pd.DataFrame(
            [
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2024-01-15"),
                    TransactionsTableFields.CATEGORY.value: "Wedding",
                    TransactionsTableFields.TAG.value: "Venue",
                    TransactionsTableFields.AMOUNT.value: -5000.0,
                    TransactionsTableFields.UNIQUE_ID.value: "tx_w1",
                    "type": "normal",
                },
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2024-02-10"),
                    TransactionsTableFields.CATEGORY.value: "Wedding",
                    TransactionsTableFields.TAG.value: "Catering",
                    TransactionsTableFields.AMOUNT.value: -3000.0,
                    TransactionsTableFields.UNIQUE_ID.value: "tx_w2",
                    "type": "normal",
                },
            ]
        )
        service.transactions_service.get_data_for_analysis = (
            lambda include_split_parents: test_transactions
        )

        view = service.get_project_budget_view("Wedding")

        assert view["total_spent"] == 8000.0
        assert view["name"] == "Wedding"

        rules_view = view["rules"]
        # Should have Total Budget + Venue + Catering
        rule_names = [r["rule"][NAME] for r in rules_view]
        assert TOTAL_BUDGET in rule_names

        venue_entry = next(r for r in rules_view if r["rule"][NAME] == "Venue")
        assert venue_entry["current_amount"] == 5000.0
        assert venue_entry["allow_edit"] is True
        assert venue_entry["allow_delete"] is True

        catering_entry = next(r for r in rules_view if r["rule"][NAME] == "Catering")
        assert catering_entry["current_amount"] == 3000.0

    def test_project_view_without_type_column(self, db_session):
        """Verify project budget view handles DataFrames missing the type column."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        # Create test transactions without 'type' column (line 1171, 1208)
        test_transactions = pd.DataFrame(
            [
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2024-01-15"),
                    TransactionsTableFields.CATEGORY.value: "Wedding",
                    TransactionsTableFields.TAG.value: "Venue",
                    TransactionsTableFields.AMOUNT.value: -2000.0,
                    TransactionsTableFields.UNIQUE_ID.value: "tx_notype",
                },
            ]
        )
        service.transactions_service.get_data_for_analysis = (
            lambda include_split_parents: test_transactions
        )

        view = service.get_project_budget_view("Wedding")
        assert view["total_spent"] == 2000.0

    def test_project_view_auto_creates_rules_for_unmatched_tags(self, db_session):
        """Verify project view auto-creates rules for tags without existing rules."""
        service = ProjectBudgetService(db_session)
        service.create_project("Wedding", 50000.0)

        # Transaction with a tag not matching any existing rule
        test_transactions = pd.DataFrame(
            [
                {
                    TransactionsTableFields.DATE.value: pd.Timestamp("2024-01-20"),
                    TransactionsTableFields.CATEGORY.value: "Wedding",
                    TransactionsTableFields.TAG.value: "Photography",
                    TransactionsTableFields.AMOUNT.value: -1500.0,
                    TransactionsTableFields.UNIQUE_ID.value: "tx_photo",
                    "type": "normal",
                },
            ]
        )
        service.transactions_service.get_data_for_analysis = (
            lambda include_split_parents: test_transactions
        )

        view = service.get_project_budget_view("Wedding")

        # "Photography" rule should be auto-created
        photo_entry = next(
            (r for r in view["rules"] if r["rule"][NAME] == "Photography"), None
        )
        assert photo_entry is not None
        assert photo_entry["current_amount"] == 1500.0
        assert photo_entry["rule"][TAGS] == ["Photography"]
