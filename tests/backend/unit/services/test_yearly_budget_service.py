from datetime import date

import pytest


class TestYearlyBudgetView:
    """The yearly view accumulates spend across the whole calendar year."""

    def _seed_expense(self, db_session, unique_id, date, category, tag, amount):
        """Insert a bank transaction (mirrors the seeding pattern in conftest.py)."""
        from backend.models.transaction import BankTransaction

        db_session.add(
            BankTransaction(
                id=unique_id,
                date=date,
                provider="hapoalim",
                account_name="Checking",
                description="x",
                amount=amount,
                category=category,
                tag=tag,
                source="bank_transactions",
                type="normal",
                status="completed",
            )
        )
        db_session.commit()

    def test_view_sums_full_year(self, db_session):
        """Two transactions in different months of the year both count."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2026)
        self._seed_expense(db_session, "y1", "2026-03-02", "Travel", "Hotels", -5900.0)
        self._seed_expense(db_session, "y2", "2026-08-14", "Travel", "Hotels", -3200.0)
        self._seed_expense(
            db_session, "y3", "2025-12-31", "Travel", "Hotels", -1000.0
        )  # prior year excluded

        view = svc.get_yearly_budget_view(2026)
        entry = next(e for e in view if e["rule"]["name"] == "Vacations")
        assert entry["current_amount"] == 9100.0

    def test_view_none_when_no_rules(self, db_session):
        """No yearly rules for the year returns None."""
        from backend.services.budget_service import YearlyBudgetService

        assert YearlyBudgetService(db_session).get_yearly_budget_view(2026) is None


class TestYearSummary:
    """The computed, display-only roll-up."""

    def test_summary_totals(self, db_session):
        """Allocated/spent/remaining and health counts are computed from the view."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2026)
        svc.create_rule("Car", 15000.0, "Transport", ["Insurance"], 2026)
        s = svc.get_year_summary(2026)
        assert s["total_allocated"] == 35000.0
        assert s["total_spent"] == 0.0
        assert s["remaining"] == 35000.0
        assert s["on_track"] == 2 and s["over"] == 0


class TestYearlyValidation:
    """Manual create/edit hard-blocks conflicts with monthly budgets."""

    def test_create_conflict_with_monthly_raises(self, db_session):
        """A yearly rule reusing a monthly tag for the same year is rejected."""
        from backend.services.budget_service import MonthlyBudgetService, YearlyBudgetService

        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 9999.0, "Total Budget", ["all_tags"], 5, 2026
        )
        MonthlyBudgetService(db_session).create_rule(
            "Food M", 500.0, "Food", ["Groceries"], 5, 2026
        )
        with pytest.raises(ValueError, match="Groceries"):
            YearlyBudgetService(db_session).create_rule(
                "Food Y", 6000.0, "Food", ["Groceries"], 2026
            )

    def test_duplicate_name_in_year_raises(self, db_session):
        """Two yearly rules with the same name in one year are rejected."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2026)
        with pytest.raises(ValueError, match="already exists"):
            svc.create_rule("Vacations", 100.0, "Travel", ["Activities"], 2026)


class TestYearlyAlerts:
    """Alerts fire on spend/limit thresholds, mirroring monthly."""

    def test_over_budget_is_critical(self, db_session):
        """A rule at/over 100% is tagged critical."""
        from backend.models.transaction import BankTransaction
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Car", 1000.0, "Transport", ["Insurance"], 2026)
        db_session.add(
            BankTransaction(
                id="y4",
                date="2026-02-01",
                provider="hapoalim",
                account_name="Checking",
                description="x",
                amount=-1200.0,
                category="Transport",
                tag="Insurance",
                source="bank_transactions",
                type="normal",
                status="completed",
            )
        )
        db_session.commit()
        alerts = svc.get_alerts(2026)
        assert alerts and alerts[0]["severity"] == "critical"


class TestYearlyCarryForward:
    """Prior-year rules carry into an empty current/future year, minus conflicts."""

    def test_carries_prior_year_rules(self, db_session, monkeypatch):
        """An empty 2026 inherits 2025's yearly rules."""
        from backend.services.budget_service import YearlyBudgetService
        import backend.services.budget_service as mod
        svc = YearlyBudgetService(db_session)
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2025)

        # Pretend "today" is in 2026 so carry-forward is allowed.
        monkeypatch.setattr(mod, "_today", lambda: date(2026, 1, 1))
        result = svc.auto_carry_forward(2026)
        assert result["copied_from"] == 2025 and result["skipped"] == []
        assert "Vacations" in list(svc.get_year_rules(2026)["name"])

    def test_skips_tags_conflicting_with_monthly(self, db_session, monkeypatch):
        """A carried tag that a 2026 monthly rule owns is skipped and reported."""
        from backend.services.budget_service import YearlyBudgetService, MonthlyBudgetService
        import backend.services.budget_service as mod
        svc = YearlyBudgetService(db_session)
        svc.create_rule("Trips", 20000.0, "Travel", ["Flights", "Hotels"], 2025)
        MonthlyBudgetService(db_session).create_rule("Total Budget", 9999.0, "Total Budget", ["all_tags"], 3, 2026)
        MonthlyBudgetService(db_session).create_rule("Flights M", 4000.0, "Travel", ["Flights"], 3, 2026)

        monkeypatch.setattr(mod, "_today", lambda: date(2026, 1, 1))
        result = svc.auto_carry_forward(2026)
        assert result["skipped"] == ["Flights"]
        carried = svc.get_year_rules(2026)
        trips = carried.loc[carried["name"] == "Trips"].iloc[0]
        assert trips["tags"] == ["Hotels"]  # Flights stripped


class TestYearlyAnalysisSkippedConflictsDedup:
    """get_yearly_analysis must not repeat a tag skipped by more than one carried rule."""

    def test_skipped_conflicts_deduped_across_rules(self, db_session, monkeypatch):
        """Two prior-year rules skipping the same tag report it only once."""
        from backend.services.budget_service import YearlyBudgetService, MonthlyBudgetService
        import backend.services.budget_service as mod

        svc = YearlyBudgetService(db_session)
        # Two independent 2025 yearly rules in DIFFERENT categories both carry a
        # "Hotels" tag; each collides with its category's 2026 monthly rule when
        # carried forward, so both skip "Hotels". (Same-category overlap is now
        # blocked by the yearly-vs-yearly guard, so the dedup scenario is
        # constructed across categories that happen to share a tag name.)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2025)
        svc.create_rule("VacB", 3000.0, "Leisure", ["Hotels"], 2025)

        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 9999.0, "Total Budget", ["all_tags"], 3, 2026
        )
        MonthlyBudgetService(db_session).create_rule(
            "Travel M", 500.0, "Travel", ["Hotels"], 3, 2026
        )
        MonthlyBudgetService(db_session).create_rule(
            "Leisure M", 500.0, "Leisure", ["Hotels"], 3, 2026
        )

        monkeypatch.setattr(mod, "_today", lambda: date(2026, 1, 1))
        analysis = svc.get_yearly_analysis(2026)
        assert analysis["skipped_conflicts"] == ["Hotels"]


class TestForceCopyFromPriorYear:
    """Explicit user-triggered "Copy from previous year" — must never lose data."""

    def test_copies_prior_year_rules_stripping_conflicts(self, db_session):
        """Target year's rules become the source year's, minus conflicting tags."""
        from backend.services.budget_service import MonthlyBudgetService, YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Trips", 20000.0, "Travel", ["Flights", "Hotels"], 2025)
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 9999.0, "Total Budget", ["all_tags"], 3, 2026
        )
        MonthlyBudgetService(db_session).create_rule(
            "Flights M", 4000.0, "Travel", ["Flights"], 3, 2026
        )

        result = svc.force_copy_from_prior_year(2026)
        assert result == {"copied_from": 2025, "skipped": ["Flights"]}
        carried = svc.get_year_rules(2026)
        trips = carried.loc[carried["name"] == "Trips"].iloc[0]
        assert trips["tags"] == ["Hotels"]

    def test_no_prior_year_returns_none_and_does_not_delete_target(self, db_session):
        """Data-loss regression: no source year -> 404-worthy None, target rules survive.

        This is the exact bug the fix targets: previously the route deleted
        the target year's existing rules *before* checking whether a prior
        year existed to copy from, silently destroying data when there was
        no source. ``force_copy_from_prior_year`` must resolve the source
        first and leave the target untouched when none is found.
        """
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        # Target year already has rules of its own — there is no earlier
        # year with yearly rules anywhere in the DB.
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2026)

        result = svc.force_copy_from_prior_year(2026)

        assert result is None
        survivors = svc.get_year_rules(2026)
        assert list(survivors["name"]) == ["Vacations"]

    def test_overwrites_non_empty_target_when_source_exists(self, db_session):
        """Unlike auto_carry_forward, this explicit action may overwrite a non-empty year."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("OldRule", 1000.0, "Food", ["Groceries"], 2026)
        svc.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2025)

        result = svc.force_copy_from_prior_year(2026)

        assert result == {"copied_from": 2025, "skipped": []}
        names = list(svc.get_year_rules(2026)["name"])
        assert names == ["Vacations"]
        assert "OldRule" not in names


class TestYearlyVsYearlyExclusion:
    """A (category, tag) cannot be covered by two yearly rules in the same year."""

    def test_create_conflicting_tag_with_another_yearly_raises(self, db_session):
        """A second yearly rule sharing a tag in the same category+year is rejected."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels", "Flights"], 2026)
        with pytest.raises(ValueError, match="Hotels"):
            svc.create_rule("VacB", 3000.0, "Travel", ["Hotels"], 2026)

    def test_non_overlapping_tags_same_category_ok(self, db_session):
        """Two yearly rules in one category+year with disjoint tags coexist."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        svc.create_rule("VacB", 3000.0, "Travel", ["Flights"], 2026)
        assert len(svc.get_year_rules(2026)) == 2

    def test_new_all_tags_conflicts_with_existing_yearly(self, db_session):
        """An all_tags yearly rule collides with any existing yearly rule in the category+year."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        with pytest.raises(ValueError, match="Travel"):
            svc.create_rule("VacAll", 3000.0, "Travel", ["all_tags"], 2026)

    def test_existing_all_tags_blocks_new_specific(self, db_session):
        """A specific-tag yearly rule is rejected when an all_tags rule already covers the category+year."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacAll", 5000.0, "Travel", ["all_tags"], 2026)
        with pytest.raises(ValueError, match="Hotels"):
            svc.create_rule("VacB", 3000.0, "Travel", ["Hotels"], 2026)

    def test_same_tag_different_category_ok(self, db_session):
        """The same tag name in a different category does not conflict."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        svc.create_rule("StayB", 3000.0, "Leisure", ["Hotels"], 2026)
        assert len(svc.get_year_rules(2026)) == 2

    def test_same_category_tag_different_year_ok(self, db_session):
        """The same (category, tag) in a different year does not conflict."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("Vac25", 5000.0, "Travel", ["Hotels"], 2025)
        svc.create_rule("Vac26", 3000.0, "Travel", ["Hotels"], 2026)
        assert not svc.get_year_rules(2026).empty

    def test_edit_amount_does_not_conflict_with_itself(self, db_session):
        """Editing a yearly rule's amount does not trip the self-overlap guard."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        rid = int(svc.get_year_rules(2026).iloc[0]["id"])
        svc.update_rule(rid, amount=6000.0)
        assert float(svc.get_year_rules(2026).iloc[0]["amount"]) == 6000.0

    def test_edit_to_add_conflicting_tag_raises(self, db_session):
        """Editing a yearly rule to add a tag owned by another yearly rule is rejected."""
        from backend.services.budget_service import YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        svc.create_rule("VacB", 3000.0, "Travel", ["Flights"], 2026)
        rules = svc.get_year_rules(2026)
        rid_b = int(rules.loc[rules["name"] == "VacB"].iloc[0]["id"])
        with pytest.raises(ValueError, match="Hotels"):
            svc.update_rule(rid_b, tags=["Flights", "Hotels"])


class TestYearlyProjectCategoryExclusion:
    """A yearly rule can't target a category already owned by a project budget."""

    def test_yearly_create_on_project_category_raises(self, db_session):
        """A yearly rule on a project-owned category is rejected."""
        from backend.services.budget_service import ProjectBudgetService, YearlyBudgetService

        ProjectBudgetService(db_session).budget_repository.add(
            "Total Budget", 5000.0, "Renovation", "all_tags", None, None, period_type="project")
        with pytest.raises(ValueError, match="project"):
            YearlyBudgetService(db_session).create_rule("Reno Y", 3000.0, "Renovation", ["Materials"], 2026)

    def test_yearly_edit_into_project_category_raises(self, db_session):
        """Editing a yearly rule to a project-owned category is rejected."""
        from backend.services.budget_service import ProjectBudgetService, YearlyBudgetService

        svc = YearlyBudgetService(db_session)
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2026)
        ProjectBudgetService(db_session).budget_repository.add(
            "Total Budget", 5000.0, "Renovation", "all_tags", None, None, period_type="project")
        rid = int(svc.get_year_rules(2026).iloc[0]["id"])
        with pytest.raises(ValueError, match="project"):
            svc.update_rule(rid, category="Renovation", tags=["Materials"])
