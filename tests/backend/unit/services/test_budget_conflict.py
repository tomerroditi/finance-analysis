class TestFindConflictingTags:
    """Conflict detection between monthly and yearly budgets per year."""

    def test_tag_overlap_same_category_and_year_conflicts(self, db_session):
        """A shared tag in the same category+year is reported as a conflict."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        # existing yearly rule owns Travel/Flights in 2026
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights;Hotels", None, 2026, period_type="yearly")

        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", ["Flights", "Car rental"], 2026, PERIOD_YEARLY)
        assert conflicts == ["Flights"]

    def test_no_conflict_in_different_year(self, db_session):
        """Same tag in a different year does not conflict."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2025, period_type="yearly")
        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", ["Flights"], 2026, PERIOD_YEARLY)
        assert conflicts == []

    def test_all_tags_on_existing_claims_whole_category(self, db_session):
        """An existing all_tags rule conflicts with any tag in that category+year."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "all_tags", None, 2026, period_type="yearly")
        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", ["Flights", "Hotels"], 2026, PERIOD_YEARLY)
        assert conflicts == ["Flights", "Hotels"]

    def test_strip_returns_kept_and_skipped(self, db_session):
        """strip_conflicting_tags splits a tag list into kept vs skipped."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        kept, skipped = BudgetService(db_session).strip_conflicting_tags(
            "Travel", ["Flights", "Hotels"], 2026, PERIOD_YEARLY)
        assert kept == ["Hotels"] and skipped == ["Flights"]

    def test_all_tags_on_incoming_claims_whole_category(self, db_session):
        """An incoming all_tags rule conflicts with any existing rule in that category+year."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", ["all_tags"], 2026, PERIOD_YEARLY)
        assert conflicts == ["all_tags"]

    def test_all_tags_on_incoming_with_no_other_rules_no_conflict(self, db_session):
        """Incoming all_tags does not conflict when no other rule exists in that category+year."""
        from backend.services.budget_service import BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", ["all_tags"], 2026, PERIOD_YEARLY)
        assert conflicts == []

    def test_strip_all_tags_on_incoming_fully_skipped(self, db_session):
        """strip_conflicting_tags treats a conflicting incoming all_tags as fully skipped."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        kept, skipped = BudgetService(db_session).strip_conflicting_tags(
            "Travel", ["all_tags"], 2026, PERIOD_YEARLY)
        assert kept == [] and skipped == ["all_tags"]


class TestFindConflictingTagsExcludeRuleId:
    """exclude_rule_id keeps a rule being edited from conflicting with itself."""

    def test_exclude_rule_id_prevents_self_conflict(self, db_session):
        """A rule does not conflict with itself when its own id is excluded."""
        from backend.services.budget_service import MonthlyBudgetService, BudgetService
        from backend.constants.budget import PERIOD_YEARLY
        from backend.constants.budget import ID

        service = BudgetService(db_session)
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        rule_id = int(service.get_all_rules().iloc[0][ID])

        conflicts = service.find_conflicting_tags(
            "Travel", ["Flights"], 2026, PERIOD_YEARLY, exclude_rule_id=rule_id)
        assert conflicts == []
