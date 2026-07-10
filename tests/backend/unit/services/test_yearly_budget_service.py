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
