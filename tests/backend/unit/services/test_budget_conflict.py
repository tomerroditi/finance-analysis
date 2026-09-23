import pytest

from backend.constants.budget import PERIOD_YEARLY
from backend.services.budget import BudgetService, MonthlyBudgetService


class TestFindConflictingTags:
    """Conflict detection between monthly and yearly budgets per year."""

    @pytest.mark.parametrize(
        "existing, incoming, expected",
        [
            (("Flights;Hotels", 2026), ["Flights", "Car rental"], ["Flights"]),
            (("Flights", 2025), ["Flights"], []),
            (("all_tags", 2026), ["Flights", "Hotels"], ["Flights", "Hotels"]),
            (("Flights", 2026), ["all_tags"], ["all_tags"]),
            (None, ["all_tags"], []),
        ],
        ids=[
            "shared-tag-same-year",
            "same-tag-other-year",
            "existing-all-tags-claims-category",
            "incoming-all-tags-claims-category",
            "incoming-all-tags-alone",
        ],
    )
    def test_find_conflicting_tags(self, db_session, existing, incoming, expected):
        """A tag conflicts with a yearly rule on the same category and year.

        ``all_tags`` on either side claims the whole category, and a rule in
        a different year never conflicts.
        """
        if existing is not None:
            tags, year = existing
            MonthlyBudgetService(db_session).budget_repository.add(
                "Y", 20.0, "Travel", tags, None, year, period_type="yearly")

        conflicts = BudgetService(db_session).find_conflicting_tags(
            "Travel", incoming, 2026, PERIOD_YEARLY)
        assert conflicts == expected

    @pytest.mark.parametrize(
        "incoming, kept, skipped",
        [
            (["Flights", "Hotels"], ["Hotels"], ["Flights"]),
            (["all_tags"], [], ["all_tags"]),
        ],
        ids=["split-tag-list", "conflicting-all-tags-fully-skipped"],
    )
    def test_strip_conflicting_tags(self, db_session, incoming, kept, skipped):
        """strip_conflicting_tags splits a tag list into kept vs skipped.

        A conflicting incoming ``all_tags`` is skipped whole.
        """
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        result = BudgetService(db_session).strip_conflicting_tags(
            "Travel", incoming, 2026, PERIOD_YEARLY)
        assert result == (kept, skipped)


class TestFindConflictingTagsExcludeRuleId:
    """exclude_rule_id keeps a rule being edited from conflicting with itself."""

    def test_exclude_rule_id_prevents_self_conflict(self, db_session):
        """A rule does not conflict with itself when its own id is excluded."""
        from backend.constants.budget import ID

        service = BudgetService(db_session)
        MonthlyBudgetService(db_session).budget_repository.add(
            "Y", 20.0, "Travel", "Flights", None, 2026, period_type="yearly")
        rule_id = int(service.get_all_rules().iloc[0][ID])

        conflicts = service.find_conflicting_tags(
            "Travel", ["Flights"], 2026, PERIOD_YEARLY, exclude_rule_id=rule_id)
        assert conflicts == []


class TestProjectCategoryHelpers:
    """Category-level project ↔ monthly/yearly detection helpers."""

    def test_is_category_project_owned(self, db_session):
        """A category with a project rule is project-owned; others are not."""
        from backend.services.budget import ProjectBudgetService

        ProjectBudgetService(db_session).budget_repository.add(
            "Total Budget", 100.0, "Reno", "all_tags", None, None, period_type="project")
        svc = BudgetService(db_session)
        assert svc.is_category_project_owned("Reno") is True
        assert svc.is_category_project_owned("Food") is False

    def test_category_used_by_monthly_or_yearly(self, db_session):
        """Monthly and yearly rules mark a category budget-used; Total Budget is excluded."""
        svc = BudgetService(db_session)
        svc.budget_repository.add("m", 10.0, "Food", "Groceries", 5, 2026, period_type="monthly")
        svc.budget_repository.add("y", 20.0, "Travel", "Hotels", None, 2026, period_type="yearly")
        svc.budget_repository.add("Total Budget", 999.0, "Total Budget", "all_tags", 5, 2026, period_type="monthly")
        assert svc.category_used_by_monthly_or_yearly("Food") is True
        assert svc.category_used_by_monthly_or_yearly("Travel") is True
        assert svc.category_used_by_monthly_or_yearly("Total Budget") is False
        assert svc.category_used_by_monthly_or_yearly("Reno") is False

    def test_find_category_overlaps(self, db_session):
        """Overlaps list categories that are both project-owned and budget-used."""
        svc = BudgetService(db_session)
        svc.budget_repository.add("Total Budget", 100.0, "Reno", "all_tags", None, None, period_type="project")
        svc.budget_repository.add("m", 10.0, "Reno", "Materials", 5, 2026, period_type="monthly")
        overlaps = svc.find_category_overlaps()
        assert overlaps == [{"category": "Reno", "kinds": ["monthly"]}]
