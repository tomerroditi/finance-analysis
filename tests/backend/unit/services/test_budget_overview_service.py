"""Tests for the cross-kind budget Overview read model."""

import pytest

from backend.services.budget_service import (
    BudgetOverviewService,
    MonthlyBudgetService,
    ProjectBudgetService,
    YearlyBudgetService,
)


def _seed(db_session, date, category, tag, amount, description="x", ident=None):
    """Seed one bank transaction with the real ORM field shape."""
    from backend.models.transaction import BankTransaction

    db_session.add(
        BankTransaction(
            id=ident or f"tx_{date}_{tag}_{abs(amount)}_{description}",
            date=date,
            provider="p",
            account_name="a",
            description=description,
            amount=amount,
            category=category,
            tag=tag,
            source="bank_transactions",
            type="normal",
            status="completed",
        )
    )
    db_session.commit()


def _confirm_recurring(db_session):
    """Accept every detected recurring candidate.

    Detection only proposes; the Overview acts on confirmed charges alone. A
    test about the fixed/variable split or about commitments is about what
    happens *after* the user has said yes, so it says yes here.
    """
    from backend.services.recurring_service import RecurringService

    service = RecurringService(db_session)
    service.set_decisions([
        {"normalized": item["normalized"], "decision": "confirmed"}
        for item in service.get_recurring()["items"]
    ])


@pytest.fixture
def frozen_today(monkeypatch):
    """Pin today to 2026-03-19, mid-month, for every module that asks.

    The overview composes the monthly service, and rule auto-fill inside
    ``get_monthly_analysis`` reads ``date.today()`` from its own module — so
    pinning only the overview's ``_today`` leaves the two disagreeing about
    which month is current. Patching must target the defining submodule; the
    compatibility shim's re-exports are not consulted at call time.
    """
    from datetime import date

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 19)

    monkeypatch.setattr(
        "backend.services.budget.overview._today", lambda: date(2026, 3, 19)
    )
    monkeypatch.setattr("backend.services.budget.monthly.date", FrozenDate)
    return date(2026, 3, 19)


class TestMonthFraming:
    """Elapsed days, and what they make meaningful."""

    def test_current_month_counts_days_to_today(self, db_session, frozen_today):
        """A live month is elapsed to today, with the rest still to run."""
        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["is_current_month"] is True
        assert result["days_in_month"] == 31
        assert result["days_elapsed"] == 19
        assert result["days_left"] == 12

    def test_closed_month_is_fully_elapsed(self, db_session, frozen_today):
        """A month already past counts every one of its days as spent."""
        result = BudgetOverviewService(db_session).get_overview(2026, 1)
        assert result["is_current_month"] is False
        assert result["days_elapsed"] == 31
        assert result["days_left"] == 0

    def test_closed_month_has_no_projection(self, db_session, frozen_today):
        """A settled month has a final figure, so no projection is offered."""
        assert BudgetOverviewService(db_session).get_overview(2026, 1)["projected"] is None

    def test_future_month_has_no_elapsed_days(self, db_session, frozen_today):
        """A month that has not started has nothing elapsed to extrapolate from."""
        result = BudgetOverviewService(db_session).get_overview(2026, 5)
        assert result["days_elapsed"] == 0
        assert result["variable_per_day"] == 0.0


class TestFixedVariableSplit:
    """Recurring charges are separated from day-to-day spend."""

    def _seed_recurring_rent(self, db_session):
        """Six months of an identically described charge, enough to be detected."""
        for month in range(1, 7):
            _seed(
                db_session,
                f"2026-0{month}-02",
                "Household",
                "Rent",
                -6000.0,
                description="MORTGAGE 4471",
            )

    def test_recurring_charge_counts_as_fixed(self, db_session, frozen_today):
        """A detected recurring charge lands on the fixed side of the split.

        Detection status is irrelevant here — these sightings are long stale
        against the real clock, and a past month's charge is fixed regardless.
        """
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        self._seed_recurring_rent(db_session)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0, description="SUPER A")
        _confirm_recurring(db_session)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["fixed_spent"] == 6000.0
        assert result["variable_spent"] == 400.0

    def test_unconfirmed_candidate_is_still_variable(self, db_session, frozen_today):
        """Detection alone does not move spend to the fixed side.

        The whole point of the confirmation gate: until the user agrees the
        charge is recurring, it is ordinary day-to-day spend.
        """
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        self._seed_recurring_rent(db_session)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0, description="SUPER A")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["fixed_spent"] == 0.0
        assert result["variable_spent"] == 6400.0

    def test_split_always_sums_to_the_month_total(self, db_session, frozen_today):
        """Fixed plus variable is the month's spend, whatever the detector found."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        self._seed_recurring_rent(db_session)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0, description="SUPER A")
        _seed(db_session, "2026-03-14", "Food", "Restaurants", -250.0, description="CAFE B")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["fixed_spent"] + result["variable_spent"] == pytest.approx(
            result["monthly_spent"]
        )

    def test_one_off_spend_is_all_variable(self, db_session, frozen_today):
        """With nothing recurring detected, every shekel is day-to-day."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0, description="SUPER A")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["fixed_spent"] == 0.0
        assert result["variable_spent"] == 400.0

    def test_variable_rate_divides_by_elapsed_days_only(self, db_session, frozen_today):
        """The daily rate uses days lived, not the whole month."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        _seed(db_session, "2026-03-11", "Food", "Groceries", -1900.0, description="SUPER A")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["variable_per_day"] == pytest.approx(100.0)


class TestCommitments:
    """Recurring charges still due are held back from what is free to spend."""

    def test_free_to_spend_excludes_what_is_still_committed(
        self, db_session, frozen_today
    ):
        """Money already spoken for is not offered as spendable."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        # Three sightings ending 22 February put the next one around 24 March,
        # still ahead of the frozen 19th. Detection needs at least three.
        for seen in ("2025-12-22", "2026-01-22", "2026-02-22"):
            _seed(
                db_session,
                seen,
                "Household",
                "Utilities",
                -780.0,
                description="ELECTRIC CO",
            )
        _seed(db_session, "2026-03-05", "Food", "Groceries", -1000.0, description="SUPER A")
        _confirm_recurring(db_session)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["committed_remaining"] == 780.0
        assert [c["label"] for c in result["charges_due"]] == ["ELECTRIC CO"]
        assert result["free_to_spend"] == pytest.approx(20000.0 - 1000.0 - 780.0)

    def test_unconfirmed_candidate_commits_nothing(self, db_session, frozen_today):
        """An unreviewed guess never holds money back from free-to-spend."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        for seen in ("2025-12-22", "2026-01-22", "2026-02-22"):
            _seed(
                db_session,
                seen,
                "Household",
                "Utilities",
                -780.0,
                description="ELECTRIC CO",
            )
        _seed(db_session, "2026-03-05", "Food", "Groceries", -1000.0, description="SUPER A")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["committed_remaining"] == 0.0
        assert result["charges_due"] == []
        assert result["free_to_spend"] == pytest.approx(20000.0 - 1000.0)

    def test_closed_month_commits_nothing(self, db_session, frozen_today):
        """A settled month has nothing left to land."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 1, 2026
        )
        result = BudgetOverviewService(db_session).get_overview(2026, 1)
        assert result["committed_remaining"] == 0.0
        assert result["charges_due"] == []

    def test_projection_adds_commitments_and_the_variable_rate(
        self, db_session, frozen_today
    ):
        """The projection is spend, plus what is owed, plus the rate for days left."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        _seed(db_session, "2026-03-05", "Food", "Groceries", -1900.0, description="SUPER A")

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        expected = 1900.0 + 0.0 + (1900.0 / 19) * 12
        assert result["projected"] == pytest.approx(expected, abs=0.02)


class TestSeparatePools:
    """Project and yearly spend is not inside the monthly budget."""

    def test_project_spend_stays_out_of_the_monthly_total(self, db_session, frozen_today):
        """A project transaction never counts against the monthly budget."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        ProjectBudgetService(db_session).add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-03-08", "Home Renovation", "Materials", -4200.0)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["monthly_spent"] == 400.0
        assert result["projects_month_spent"] == 4200.0

    def test_yearly_claimed_spend_stays_out_of_the_monthly_total(
        self, db_session, frozen_today
    ):
        """A yearly-claimed tag never counts against the monthly budget."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        YearlyBudgetService(db_session).create_rule(
            "Vacations", 20000.0, "Travel", ["Hotels"], 2026
        )
        _seed(db_session, "2026-03-08", "Travel", "Hotels", -3000.0)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["monthly_spent"] == 400.0
        assert result["yearly_month_spent"] == 3000.0

    def test_total_out_adds_the_three_pools(self, db_session, frozen_today):
        """Only ``total_out`` describes everything that left the accounts."""
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        YearlyBudgetService(db_session).create_rule(
            "Vacations", 20000.0, "Travel", ["Hotels"], 2026
        )
        ProjectBudgetService(db_session).add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-03-08", "Travel", "Hotels", -3000.0)
        _seed(db_session, "2026-03-09", "Home Renovation", "Materials", -4200.0)
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["total_out"] == 7600.0


class TestLongEnvelopes:
    """Yearly and project envelopes carry a month share and an overall standing."""

    def test_project_reports_month_share_and_lifetime_standing(
        self, db_session, frozen_today
    ):
        """The month's contribution is scoped; the standing is lifetime-to-date."""
        ProjectBudgetService(db_session).add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-01-08", "Home Renovation", "Materials", -9000.0)
        _seed(db_session, "2026-03-09", "Home Renovation", "Materials", -4200.0)

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Home Renovation"
        )
        assert envelope["kind"] == "project"
        assert envelope["month_contribution"] == 4200.0
        assert envelope["spent"] == 13200.0
        assert envelope["budget"] == 30000.0

    def test_yearly_reports_month_share_and_year_to_date_standing(
        self, db_session, frozen_today
    ):
        """A yearly envelope's standing covers the year, not the viewed month."""
        YearlyBudgetService(db_session).create_rule(
            "Gifts", 4000.0, "Shopping", ["Gifts"], 2026
        )
        _seed(db_session, "2026-01-08", "Shopping", "Gifts", -900.0)
        _seed(db_session, "2026-03-09", "Shopping", "Gifts", -350.0)

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Gifts"
        )
        assert envelope["kind"] == "yearly"
        assert envelope["month_contribution"] == 350.0
        assert envelope["spent"] == 1250.0

    def test_standing_is_unchanged_by_the_month_being_viewed(
        self, db_session, frozen_today
    ):
        """Stepping back a month must not rewrite a long envelope's standing.

        This is the trap the Overview exists to avoid: the standing always
        describes today, so only the contribution may move with the viewed month.
        """
        ProjectBudgetService(db_session).add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-01-08", "Home Renovation", "Materials", -9000.0)
        _seed(db_session, "2026-03-09", "Home Renovation", "Materials", -4200.0)

        service = BudgetOverviewService(db_session)
        march = next(
            e for e in service.get_overview(2026, 3)["long_envelopes"] if e["name"] == "Home Renovation"
        )
        january = next(
            e for e in service.get_overview(2026, 1)["long_envelopes"] if e["name"] == "Home Renovation"
        )
        assert march["spent"] == january["spent"] == 13200.0
        assert march["month_contribution"] == 4200.0
        assert january["month_contribution"] == 9000.0


class TestClosedProjects:
    """A closed project leaves the envelope list without losing its spend."""

    @staticmethod
    def _open_project(db_session):
        """Seed one project envelope with spend in and before the viewed month."""
        service = ProjectBudgetService(db_session)
        service.add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-01-08", "Home Renovation", "Materials", -9000.0)
        _seed(db_session, "2026-03-09", "Home Renovation", "Materials", -4200.0)
        return service

    def test_closed_project_drops_out_of_the_envelope_list(
        self, db_session, frozen_today
    ):
        """A finished project is no longer an envelope the month is measured against."""
        service = self._open_project(db_session)
        service.set_project_closed("Home Renovation", True)

        envelopes = BudgetOverviewService(db_session).get_overview(2026, 3)[
            "long_envelopes"
        ]
        assert [e["name"] for e in envelopes if e["kind"] == "project"] == []

    def test_closed_project_still_counts_in_the_month_totals(
        self, db_session, frozen_today
    ):
        """Its spend left the accounts, so the pool totals must still include it."""
        service = self._open_project(db_session)
        service.set_project_closed("Home Renovation", True)

        overview = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert overview["projects_month_spent"] == 4200.0
        assert overview["total_out"] == 4200.0

    def test_reopened_project_returns_to_the_envelope_list(
        self, db_session, frozen_today
    ):
        """Closing is reversible — reopening restores the envelope unchanged."""
        service = self._open_project(db_session)
        service.set_project_closed("Home Renovation", True)
        service.set_project_closed("Home Renovation", False)

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Home Renovation"
        )
        assert envelope["spent"] == 13200.0
        assert envelope["budget"] == 30000.0

    def test_envelopes_never_expose_the_closed_flag(self, db_session, frozen_today):
        """The flag is an internal filter — every listed envelope is open."""
        self._open_project(db_session)
        envelopes = BudgetOverviewService(db_session).get_overview(2026, 3)[
            "long_envelopes"
        ]
        assert envelopes
        assert all("closed" not in envelope for envelope in envelopes)

    def test_open_project_is_unaffected_by_a_closed_sibling(
        self, db_session, frozen_today
    ):
        """Closing one project must not take the others with it."""
        service = self._open_project(db_session)
        service.add_rule(
            name="Total Budget",
            amount=10000.0,
            category="Wedding",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-03-11", "Wedding", "Venue", -2500.0)
        service.set_project_closed("Home Renovation", True)

        envelopes = BudgetOverviewService(db_session).get_overview(2026, 3)[
            "long_envelopes"
        ]
        assert [e["name"] for e in envelopes if e["kind"] == "project"] == ["Wedding"]


class TestClosedYearlyEnvelopes:
    """A closed yearly envelope leaves the list without losing its spend."""

    @staticmethod
    def _open_envelope(db_session):
        """Seed one yearly envelope with spend in and before the viewed month."""
        service = YearlyBudgetService(db_session)
        service.create_rule("Gifts", 4000.0, "Shopping", ["Gifts"], 2026)
        _seed(db_session, "2026-01-08", "Shopping", "Gifts", -900.0)
        _seed(db_session, "2026-03-09", "Shopping", "Gifts", -350.0)
        rules = service.get_year_rules(2026)
        return service, int(rules.iloc[0]["id"])

    def test_closed_envelope_drops_out_of_the_envelope_list(
        self, db_session, frozen_today
    ):
        """A settled annual commitment is not something this month is measured against."""
        service, rule_id = self._open_envelope(db_session)
        service.set_rule_closed(rule_id, True)

        envelopes = BudgetOverviewService(db_session).get_overview(2026, 3)[
            "long_envelopes"
        ]
        assert [e["name"] for e in envelopes if e["kind"] == "yearly"] == []

    def test_closed_envelope_still_counts_in_the_month_totals(
        self, db_session, frozen_today
    ):
        """Its spend left the accounts, so the pool totals must still include it."""
        service, rule_id = self._open_envelope(db_session)
        service.set_rule_closed(rule_id, True)

        overview = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert overview["yearly_month_spent"] == 350.0
        assert overview["total_out"] == 350.0

    def test_reopened_envelope_returns_unchanged(self, db_session, frozen_today):
        """Closing is reversible — reopening restores the envelope as it was."""
        service, rule_id = self._open_envelope(db_session)
        service.set_rule_closed(rule_id, True)
        service.set_rule_closed(rule_id, False)

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Gifts"
        )
        assert envelope["spent"] == 1250.0
        assert envelope["budget"] == 4000.0

    def test_open_envelope_is_unaffected_by_a_closed_sibling(
        self, db_session, frozen_today
    ):
        """Closing one yearly rule must not take the others with it."""
        service, rule_id = self._open_envelope(db_session)
        service.create_rule("Vacations", 20000.0, "Travel", ["Hotels"], 2026)
        _seed(db_session, "2026-03-11", "Travel", "Hotels", -2500.0)
        service.set_rule_closed(rule_id, True)

        envelopes = BudgetOverviewService(db_session).get_overview(2026, 3)[
            "long_envelopes"
        ]
        assert [e["name"] for e in envelopes if e["kind"] == "yearly"] == ["Vacations"]

    def test_closed_envelope_still_keeps_its_spend_out_of_the_monthly_pool(
        self, db_session, frozen_today
    ):
        """The rule goes on claiming its tag, so the monthly budget is untouched.

        This is the failure closing must not cause: a closed envelope whose
        spend fell back into the monthly pool would blow the month's budget
        for money the user had already accounted for elsewhere.
        """
        service, rule_id = self._open_envelope(db_session)
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 9000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        service.set_rule_closed(rule_id, True)

        overview = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert overview["monthly_spent"] == 0.0


class TestEmptyState:
    """A month with nothing configured still answers."""

    def test_no_rules_yields_zeroes_rather_than_an_error(self, db_session, frozen_today):
        """An untouched month reports zeroes, not a failure."""
        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["monthly_budget"] == 0.0
        assert result["monthly_spent"] == 0.0
        assert result["long_envelopes"] == []


class TestRuleShapesInTheWild:
    """Regressions found only against the demo database, not synthetic fixtures."""

    def test_project_budget_on_a_covering_rule_is_found(self, db_session, frozen_today):
        """A project whose budget sits on a tag-covering rule still reports it.

        ``create_project`` writes an ``all_tags`` anchor, but projects that
        predate it — the demo database included — carry a single rule tagged
        with every tag in the project. Matching only the anchor reported every
        such project as having no budget at all.
        """
        ProjectBudgetService(db_session).add_rule(
            name="Home Renovation",
            amount=30000.0,
            category="Home Renovation",
            tags=["Materials", "Labor", "Furniture"],
            month=None,
            year=None,
        )
        _seed(db_session, "2026-03-09", "Home Renovation", "Materials", -4200.0)

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Home Renovation"
        )
        assert envelope["budget"] == 30000.0

    def test_all_tags_anchor_wins_over_a_larger_tag_rule(self, db_session, frozen_today):
        """With an anchor present, per-tag budgets never inflate the total."""
        projects = ProjectBudgetService(db_session)
        projects.add_rule(
            name="Total Budget",
            amount=30000.0,
            category="Home Renovation",
            tags=["all_tags"],
            month=None,
            year=None,
        )
        projects.add_rule(
            name="Materials",
            amount=44000.0,
            category="Home Renovation",
            tags=["Materials"],
            month=None,
            year=None,
        )

        envelope = next(
            e
            for e in BudgetOverviewService(db_session).get_overview(2026, 3)[
                "long_envelopes"
            ]
            if e["name"] == "Home Renovation"
        )
        assert envelope["budget"] == 30000.0

    def test_current_month_inherits_rules_from_the_previous_month(
        self, db_session, frozen_today
    ):
        """A live month with no rules yet still shows a budget.

        Rules auto-fill forward, but only through ``get_monthly_analysis``.
        Reading the raw view meant the Overview reported a zero budget for the
        current month until the user happened to open the Monthly tab.
        """
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 2, 2026
        )
        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["monthly_budget"] == 20000.0

    def test_fixed_charge_count_counts_what_landed_not_what_is_due(
        self, db_session, frozen_today
    ):
        """The fixed count describes charges already taken, not ones still owed.

        A caption about what has been charged must not be handed the number of
        charges still pending — they are different figures and were briefly
        conflated.
        """
        MonthlyBudgetService(db_session).create_rule(
            "Total Budget", 20000.0, "Total Budget", ["all_tags"], 3, 2026
        )
        for month in range(1, 7):
            _seed(
                db_session,
                f"2026-0{month}-02",
                "Household",
                "Rent",
                -6000.0,
                description="MORTGAGE 4471",
            )
        _seed(db_session, "2026-03-11", "Food", "Groceries", -400.0, description="SUPER A")
        _confirm_recurring(db_session)

        result = BudgetOverviewService(db_session).get_overview(2026, 3)
        assert result["fixed_charge_count"] == 1
        assert result["charges_due"] == []
