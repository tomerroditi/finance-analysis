"""Cross-request caches of derived reads, and the paths that read them.

Each cache here is a ``data_cache`` entry: built once per write, shared by
every service and request on the same database, rebuilt after any commit, and
never handed out in a form a caller could corrupt for the next one. A
file-backed database is required — in-memory ones are never cached (they have
no file identity to version against) — so this module overrides ``db_engine``
and every seed fixture lands in a file.
"""

import copy
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from backend.models import Base
from backend.models.budget import BudgetRule
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.models.transaction import InsuranceTransaction
from backend.services.analysis import AnalysisService
from backend.services.analysis import forecast as forecast_module
from backend.services.budget import ledger
from backend.services.budget.monthly import MonthlyBudgetService
from backend.services.budget.yearly import YearlyBudgetService
from backend.services.investments import InvestmentsService
from backend.services.savings_goals import SavingsGoalService
from backend.services.savings_goals.inputs import InputsMixin
from backend.services.transactions_service import TransactionsService
from backend.utils import data_cache


@pytest.fixture
def db_engine(tmp_path):
    """A fully migrated database file, in place of the in-memory default."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'shared.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    data_cache.clear()
    yield engine
    engine.dispose()
    data_cache.clear()


def _count(monkeypatch, owner, name):
    """Count calls to ``owner.name`` across every instance."""
    calls: list[int] = []
    original = getattr(owner, name)

    def spy(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(owner, name, spy)
    return calls


def _touch(db_session):
    """Commit a no-op write, which discards every cached generation."""
    db_session.execute(text("CREATE TABLE IF NOT EXISTS touched (id INTEGER)"))
    db_session.execute(text("INSERT INTO touched VALUES (1)"))
    db_session.commit()


class TestSavingsGoalContextCache:
    """The savings-goal transaction scan runs once per write, not per request."""

    def test_services_share_one_scan(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """The goal list, the yearly figure and a budget month reuse one build."""
        calls = _count(monkeypatch, InputsMixin, "_compute_context")

        SavingsGoalService(db_session).get_yearly_savings()
        SavingsGoalService(db_session).get_all()
        MonthlyBudgetService(db_session).get_monthly_analysis(2024, 1)

        assert len(calls) == 1

    def test_a_commit_rebuilds_it(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """Any write may change what the goals claim, so it discards the scan."""
        calls = _count(monkeypatch, InputsMixin, "_compute_context")
        SavingsGoalService(db_session).get_yearly_savings()

        _touch(db_session)
        SavingsGoalService(db_session).get_yearly_savings()

        assert len(calls) == 2

    def test_readers_leave_the_shared_context_untouched(
        self, db_session, seed_base_transactions
    ):
        """No read path mutates the context it shares with the next request."""
        service = SavingsGoalService(db_session)
        service.create(name="Trip", target_amount=5000.0)
        context = SavingsGoalService(db_session)._build_context()
        before = copy.deepcopy(context)

        reader = SavingsGoalService(db_session)
        reader.get_all()
        reader.get_yearly_savings()
        reader.get_free_cash()
        reader.get_timeline(months=None)
        reader.get_month(2024, 1)

        assert context == before


class TestDataForAnalysisCache:
    """The merged analysis frame is shared across requests, as copies."""

    def test_services_share_one_build(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """Separate services — separate requests — reuse the first merge."""
        calls = _count(monkeypatch, TransactionsService, "_build_data_for_analysis")

        TransactionsService(db_session).get_data_for_analysis()
        TransactionsService(db_session).get_data_for_analysis()

        assert len(calls) == 1

    def test_a_commit_rebuilds_it(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """A write discards the merged frame."""
        calls = _count(monkeypatch, TransactionsService, "_build_data_for_analysis")
        TransactionsService(db_session).get_data_for_analysis()

        _touch(db_session)
        TransactionsService(db_session).get_data_for_analysis()

        assert len(calls) == 2

    def test_callers_get_their_own_copy(self, db_session, seed_base_transactions):
        """A caller changing its frame must not change what the next one reads."""
        first = TransactionsService(db_session).get_data_for_analysis()
        first["scribble"] = 1
        first.loc[first.index[0], "amount"] = 123456.0

        second = TransactionsService(db_session).get_data_for_analysis()
        assert "scribble" not in second.columns
        assert 123456.0 not in second["amount"].tolist()


class TestForecastCache:
    """The cash-flow forecast is computed once per write and per day."""

    def test_route_and_insights_share_one_forecast(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """Separate analysis services reuse the first computation."""
        calls = _count(monkeypatch, AnalysisService, "_compute_cash_flow_forecast")

        first = AnalysisService(db_session).get_cash_flow_forecast()
        second = AnalysisService(db_session).get_cash_flow_forecast()

        assert len(calls) == 1
        assert first == second

    def test_a_new_day_recomputes_it(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """The forecast reads the clock by the day, so the day is in the key."""
        calls = _count(monkeypatch, AnalysisService, "_compute_cash_flow_forecast")
        AnalysisService(db_session).get_cash_flow_forecast()

        monkeypatch.setattr(forecast_module, "_forecast_day", lambda: "2999-01-01")
        AnalysisService(db_session).get_cash_flow_forecast()

        assert len(calls) == 2

    def test_a_commit_recomputes_it(
        self, db_session, seed_base_transactions, monkeypatch
    ):
        """A write discards the forecast."""
        calls = _count(monkeypatch, AnalysisService, "_compute_cash_flow_forecast")
        AnalysisService(db_session).get_cash_flow_forecast()

        _touch(db_session)
        AnalysisService(db_session).get_cash_flow_forecast()

        assert len(calls) == 2

    def test_callers_get_their_own_copy(self, db_session, seed_base_transactions):
        """Mutating one caller's forecast leaves the next caller's intact."""
        first = AnalysisService(db_session).get_cash_flow_forecast()
        first["daily"].clear()
        first["month"] = "scribbled"

        second = AnalysisService(db_session).get_cash_flow_forecast()
        assert second["month"] != "scribbled"
        assert second["daily"]


@pytest.fixture
def seed_linked_investment(db_session, seed_investments):
    """Add an insurance-linked fund with deposits and snapshots to the seed."""
    service = InvestmentsService(db_session)
    service.sync_from_insurance(
        {
            "policy_id": "POL-CACHE",
            "policy_type": "hishtalmut",
            "provider": "hafenix",
            "account_name": "KH",
            "balance": None,
            "balance_date": None,
        }
    )
    linked = next(
        i for i in service.get_all_investments() if i["insurance_policy_id"]
    )
    for i, day in enumerate(["2024-02-10", "2024-03-10", "2024-04-10"]):
        db_session.add(
            InsuranceTransaction(
                id=f"ins-cache-{i}",
                date=day,
                provider="hafenix",
                account_name="KH",
                account_number="POL-CACHE",
                description="Monthly deposit",
                amount=1000.0,
                source="insurance_transactions",
            )
        )
    for day, balance in (("2024-03-31", 9000.0), ("2024-05-31", 11500.0)):
        db_session.add(
            InvestmentBalanceSnapshot(
                investment_id=linked["id"], date=day, balance=balance, source="scraped"
            )
        )
    db_session.commit()
    return linked["id"]


class TestValuationInputsCache:
    """Every holding's valuation inputs are built in one pass, once per write."""

    @staticmethod
    def _read_everything(db_session):
        """Run every valuation read a page makes."""
        service = InvestmentsService(db_session)
        ids = [i["id"] for i in service.get_all_investments(include_closed=True)]
        return {
            "overview": service.get_portfolio_overview(),
            "history": service.get_portfolio_balance_history(include_closed=True),
            "values": service.get_total_values_at_dates(
                ["2023-12-31", "2024-03-15", "2024-06-30", date.today().isoformat()]
            ),
            "metrics": {i: service.calculate_profit_loss(i) for i in ids},
            "balances": {i: service.calculate_current_balance(i) for i in ids},
            "flows": {i: service._calculate_daily_flows(i) for i in ids},
        }

    def test_shared_inputs_answer_exactly_as_per_holding_reads(
        self, db_session, seed_linked_investment, monkeypatch
    ):
        """The one-pass build values every holding as the old per-holding reads did."""
        cached = self._read_everything(db_session)

        monkeypatch.setattr(data_cache, "is_cacheable", lambda db: False)
        direct = self._read_everything(db_session)

        assert cached == direct

    def test_services_share_one_build(
        self, db_session, seed_linked_investment, monkeypatch
    ):
        """Separate services reuse the first build, however many holdings they value."""
        calls = _count(monkeypatch, InvestmentsService, "_build_valuation_inputs")

        InvestmentsService(db_session).get_portfolio_overview()
        InvestmentsService(db_session).get_portfolio_balance_history()

        assert len(calls) == 1

    def test_a_commit_rebuilds_it(
        self, db_session, seed_linked_investment, monkeypatch
    ):
        """A new snapshot must move the valuation, so a write discards the map."""
        before = InvestmentsService(db_session).calculate_current_balance(
            seed_linked_investment
        )
        db_session.add(
            InvestmentBalanceSnapshot(
                investment_id=seed_linked_investment,
                date=date.today().isoformat(),
                balance=99999.0,
                source="manual",
            )
        )
        db_session.commit()

        after = InvestmentsService(db_session).calculate_current_balance(
            seed_linked_investment
        )
        assert before != after
        assert after == 99999.0

    def test_callers_get_their_own_transactions(
        self, db_session, seed_linked_investment
    ):
        """A caller rewriting its transactions frame must not change the shared one."""
        service = InvestmentsService(db_session)
        inv = service.investments_repo.get_by_id(seed_linked_investment).iloc[0]
        first = service._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=seed_linked_investment
        )
        first["amount"] = 0.0

        second = InvestmentsService(db_session)._get_all_transactions_for_investment(
            inv["category"], inv["tag"], investment_id=seed_linked_investment
        )
        assert (second["amount"] != 0.0).any()


class TestMonthTotals:
    """The trend and the alerts sum rule spend without listing transactions."""

    @pytest.fixture
    def other_expenses_month(self, db_session, seed_budget_rules):
        """Leave January spend unclaimed so the ``Other Expenses`` row appears."""
        db_session.add(
            BudgetRule(
                name="Tiny",
                amount=1.0,
                category="Transport",
                tags="Gas",
                year=2024,
                month=2,
                period_type="monthly",
            )
        )
        db_session.add(
            BudgetRule(
                name="Total Budget",
                amount=8000.0,
                category="Total Budget",
                tags="Total Budget",
                year=2024,
                month=2,
                period_type="monthly",
            )
        )
        db_session.commit()

    def test_totals_match_the_full_view_without_its_lists(
        self, db_session, seed_base_transactions, other_expenses_month
    ):
        """Every entry matches the rule view's, figure for figure."""
        service = MonthlyBudgetService(db_session)
        claims, rules = service.get_claims(), service.get_all_rules()
        compared = 0
        names: set[str] = set()
        for year, month in ((2024, 1), (2024, 2), (2024, 3), (2023, 12)):
            view = service._month_view(claims, rules, year, month)
            totals = service._month_totals(claims, rules, year, month)
            if view is None:
                assert totals is None
                continue
            assert totals == [
                {k: v for k, v in entry.items() if k != "data"} for entry in view
            ]
            compared += len(view)
            names.update(entry["rule"]["name"] for entry in view)
        assert compared > 0
        assert "Other Expenses" in names

    def test_the_trend_narrowed_to_the_pool_sums_the_same(
        self, db_session, seed_base_transactions, other_expenses_month
    ):
        """Narrowing the ledger to the monthly pool first changes no figure."""
        service = MonthlyBudgetService(db_session)
        claims, rules = service.get_claims(), service.get_all_rules()
        pool = ledger.of_kind(claims, *ledger.MONTHLY_POOL)
        for month in (1, 2, 3):
            assert service._month_totals(
                pool, rules, 2024, month
            ) == service._month_totals(claims, rules, 2024, month)

    def test_alerts_read_the_view_s_figures(
        self, db_session, seed_base_transactions, other_expenses_month
    ):
        """An alert's spend is exactly the rule's spend in the full view."""
        service = MonthlyBudgetService(db_session)
        view = {
            entry["rule"]["id"]: entry["current_amount"]
            for entry in service.get_monthly_budget_view(2024, 2) or []
        }
        alerts = service.get_alerts(2024, 2, warning_threshold=0.0)

        assert alerts
        for alert in alerts:
            assert alert["spent"] == view[alert["rule_id"]]


class TestReadsThatMightAutoFill:
    """Reading an empty current month or year writes nothing when nothing can be copied.

    Auto-fill re-reads committed state with ``rollback()`` before copying,
    and every rollback discards the cross-request cache — so it must not run
    when there is no earlier month or year to copy from.
    """

    def test_empty_month_without_a_source_keeps_the_cache(self, db_session):
        """No monthly rules anywhere: the analysis read leaves the cache alone."""
        today = date.today()
        service = MonthlyBudgetService(db_session)
        before = data_cache._write_counter

        result = service.get_monthly_analysis(today.year, today.month)

        assert result["copied_from"] is None
        assert data_cache._write_counter == before

    def test_empty_month_with_a_source_still_fills(self, db_session):
        """An earlier month with rules is still copied into the current one."""
        today = date.today()
        source_year, source_month = (
            (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        )
        db_session.add(
            BudgetRule(
                name="Total Budget",
                amount=5000.0,
                category="Total Budget",
                tags="Total Budget",
                year=source_year,
                month=source_month,
                period_type="monthly",
            )
        )
        db_session.commit()

        result = MonthlyBudgetService(db_session).get_monthly_analysis(
            today.year, today.month
        )

        assert result["copied_from"] is not None
        assert result["rules"]

    def test_empty_year_without_a_source_keeps_the_cache(self, db_session):
        """No yearly rules anywhere: the yearly read leaves the cache alone."""
        service = YearlyBudgetService(db_session)
        before = data_cache._write_counter

        result = service.get_yearly_analysis(date.today().year)

        assert result["carried_from"] is None
        assert data_cache._write_counter == before


class TestOrderedGoals:
    """Goals come back in list order from one query."""

    def test_goals_follow_priority_then_id(self, db_session):
        """Priority orders the list; the id breaks ties."""
        service = SavingsGoalService(db_session)
        service.create(name="A", target_amount=100.0)
        service.create(name="B", target_amount=100.0)
        first, second = service.repo.get_all_ordered()
        service.reorder([second.id, first.id])

        names = [g.name for g in SavingsGoalService(db_session)._goals_in_order()]

        assert names == ["B", "A"]

