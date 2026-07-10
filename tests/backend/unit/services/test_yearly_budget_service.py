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
        # Two independent 2025 yearly rules both touch Travel/Hotels — both will
        # collide with the 2026 monthly rule below when carried forward.
        svc.create_rule("VacA", 5000.0, "Travel", ["Hotels"], 2025)
        svc.create_rule("VacB", 3000.0, "Travel", ["Hotels"], 2025)

        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 9999.0, "Total Budget", ["all_tags"], 3, 2026
        )
        MonthlyBudgetService(db_session).create_rule(
            "Travel M", 500.0, "Travel", ["Hotels"], 3, 2026
        )

        monkeypatch.setattr(mod, "_today", lambda: date(2026, 1, 1))
        analysis = svc.get_yearly_analysis(2026)
        assert analysis["skipped_conflicts"] == ["Hotels"]
