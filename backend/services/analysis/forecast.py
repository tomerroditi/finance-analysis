"""
Cash-flow forecasting for the analysis service.

Provides the ``ForecastMixin`` with the current-month cash-flow
projection ("This Month" hero) and the monthly-expense trend helper it
builds on. Mixed into ``AnalysisService`` (see ``core.py``).
"""

import pandas as pd

from backend.utils.dataframe_dates import to_month_series
from backend.constants.tables import TransactionsTableFields


class ForecastMixin:
    """Forecasting methods for ``AnalysisService``."""

    #: Complete months behind the median baselines the forecast falls back on.
    #: Six is long enough for a median to mean something and short enough that
    #: a household whose income changed last spring is not still described by
    #: what it earned before.
    _TREND_MONTHS = 6

    def get_cash_flow_forecast(self) -> dict:
        """Forecast the current month's cash flow from what is due plus actuals.

        Projects where the month will end by combining what has already
        happened this month with what is still *owed* to it — not with an
        average of recent months.

        **Income comes from detected recurring streams.** A salary, an
        allowance, a benefit: money that arrives on a schedule, found by
        :meth:`~backend.services.recurring_service.RecurringService.get_recurring_income`
        and added only for the streams that have not yet paid this month. An
        average cannot do this job, because one windfall poisons it for three
        months — a household that banked a year of wedding gifts in June was
        told all summer that it earned 166k a month and would save 145k this
        month, on a salary of 22k. The median fallback below is only reached
        when no stream is detected at all.

        **Expenses still use a trend**, because discretionary spending has no
        schedule — but the part that *does* is taken out of the trend and
        added back at its own due dates (``committed_remaining``), so a bill
        is counted once, when it falls, rather than smeared across the month.

        Both projections run over the days the data has *not* seen rather than
        the days left on the calendar: accounts are scraped on their own
        schedule, and days after the last transaction are unobserved, not
        spend-free.

        Money-in and money-out are measured on their own terms, and the two
        are not interchangeable. ``actual_expenses`` and the trend behind
        ``expected_expenses`` are itemized, credit-card-deduped spending —
        what the household *bought* this month. ``current_bank_balance`` and
        the ``daily`` trajectory are what the *account* did, where a card
        statement lands as one debit for last month's shopping. Mixing the two
        is what made "expenses so far" read as last month's card bill.

        This is the data behind the dashboard "This Month" hero — the
        month-end balance projection and the "safe to spend" figure that
        Israeli budgeting apps (RiseUp et al.) lead with.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``month`` – current month in ``YYYY-MM`` format.
            - ``days_in_month`` / ``day_of_month`` / ``days_remaining`` – ints.
            - ``observed_through`` – ``YYYY-MM-DD`` of the latest transaction
              the projection could see, or null when the month has none yet.
            - ``actual_income`` – month-to-date income banked.
            - ``actual_expenses`` – month-to-date itemized spend (the same
              figure the Budget page shows).
            - ``expected_income`` / ``expected_expenses`` – projected
              full-month totals.
            - ``projected_net`` – ``expected_income - expected_expenses``.
            - ``income_basis`` – ``recurring`` when income streams were
              detected, ``trend`` when the median fallback was used.
            - ``recurring_income_due`` – recurring income still expected
              before month end.
            - ``recurring_income_items`` – the streams behind it, each
              ``{label, normalized, amount, cadence, expected_date}``.
            - ``current_bank_balance`` – sum of tracked bank balances now.
            - ``projected_end_balance`` – bank balance projected to month end.
            - ``safe_to_spend`` – money left to spend freely this month:
              ``expected_income - actual_expenses - committed_remaining``
              (non-negative).
            - ``safe_to_spend_daily`` – ``safe_to_spend`` spread over the
              remaining days.
            - ``avg_monthly_income`` / ``avg_monthly_expenses`` – the trend
              baselines: a median of complete months for income, the rolling
              mean for expenses.
            - ``committed_remaining`` – confirmed recurring charges whose next
              due date falls in the unobserved remainder of this month.
            - ``daily`` – per-day list of ``{date, actual_balance,
              projected_balance}`` for the trajectory chart (one is null
              depending on whether the day is past or future).
        """
        from backend.services.recurring_service import RecurringService

        today = pd.Timestamp.today().normalize()
        month_str = today.strftime("%Y-%m")
        month_start = today.replace(day=1)
        month_end = today + pd.offsets.MonthEnd(0)
        days_in_month = int(today.days_in_month)
        day_of_month = int(today.day)
        days_remaining = days_in_month - day_of_month
        recurring = RecurringService(self.db)

        # --- Expense trend baseline and month-to-date spend (one basis) ---
        monthly_exp = self.get_monthly_expenses(exclude_pending_refunds=True)
        avg_monthly_expenses = monthly_exp.get("avg_3_months", 0.0) or 0.0
        if avg_monthly_expenses <= 0:
            avg_monthly_expenses = (
                monthly_exp.get("avg_6_months", 0.0)
                or monthly_exp.get("avg_12_months", 0.0)
                or 0.0
            )
        actual_expenses = next(
            (
                float(m["expenses"])
                for m in monthly_exp["months"]
                if m["month"] == month_str
            ),
            0.0,
        )

        # --- Bank-side month-to-date, for the balance trajectory ---
        df = self.repo.get_cashflow_transactions()
        actual_income = 0.0
        cash_out_to_date = 0.0
        per_day_net: dict[int, float] = {}
        if not df.empty:
            df = df.copy()
            df["date_parsed"] = pd.to_datetime(df["date"])
            mtd = df[(df["date_parsed"] >= month_start) & (df["date_parsed"] <= today)]
            if not mtd.empty:
                actual_income, _, cash_out_to_date = (
                    self.get_income_investments_and_expenses(mtd)
                )
                per_day_net = (
                    mtd.groupby(mtd["date_parsed"].dt.day)["amount"].sum().to_dict()
                )

        # --- How much of the month the data has actually seen ---
        # A scrape lags the calendar, and the days between the last
        # transaction and today carry no evidence of anything. Treating them
        # as observed counts them as days of zero spending, which is how a
        # week-old scrape quietly turned into a week of savings.
        observed_through = self._latest_transaction_date(month_start, today)
        observed_day = observed_through.day if observed_through is not None else 0
        unobserved_days = days_in_month - observed_day

        # --- Current bank balance ---
        balances = self.bank_balance_service.get_all_balances()
        current_bank_balance = float(sum(b["balance"] for b in balances)) if balances else 0.0

        # --- Known upcoming recurring charges still due this month ---
        # User-confirmed subscriptions/bills whose next expected charge falls
        # in the part of the month the data has not seen. Candidates awaiting
        # review are excluded — a false positive would quietly shrink
        # safe-to-spend.
        committed_remaining = 0.0
        committed_monthly = 0.0
        observed_edge = observed_through if observed_through is not None else month_start
        for item in recurring.get_confirmed_items():
            if item["status"] == "ended":
                continue
            committed_monthly += item["monthly_equivalent"]
            next_due = pd.Timestamp(item["next_expected_date"])
            if observed_edge < next_due <= month_end:
                committed_remaining += item["amount"]

        # --- Expense projection: trend for the unscheduled part only ---
        # The committed bills are added back at their own due dates just
        # below, so leaving them in the daily trend would bill them twice.
        discretionary_monthly = max(0.0, avg_monthly_expenses - committed_monthly)
        projected_remaining_expenses = (
            discretionary_monthly / days_in_month * unobserved_days
            if days_in_month
            else 0.0
        ) + committed_remaining
        expected_expenses = actual_expenses + projected_remaining_expenses

        # --- Income projection: what is still due, not what is typical ---
        income_due = recurring.get_income_due_remaining(today=today)
        ie_over_time = self.get_income_expenses_over_time()
        complete_months = [m for m in ie_over_time if m["month"] < month_str]
        recent = complete_months[-self._TREND_MONTHS:]
        # Median, not mean: the point of the fallback is to survive the month
        # the household sold a car or married off a child.
        avg_monthly_income = (
            float(pd.Series([m["income"] for m in recent]).median()) if recent else 0.0
        )
        # A stream that has already paid this month owes nothing and still
        # counts as evidence — otherwise the basis would flip to the trend
        # (and the median with it) the moment the salary landed.
        if income_due["has_streams"]:
            income_basis = "recurring"
            expected_income = actual_income + income_due["amount"]
        else:
            income_basis = "trend"
            expected_income = max(actual_income, avg_monthly_income)
        projected_remaining_income = max(0.0, expected_income - actual_income)
        projected_net = expected_income - expected_expenses

        # --- Bank-balance trajectory, on the account's own terms ---
        cash_out_baseline = (
            float(pd.Series([m["expenses"] for m in recent]).median()) if recent else 0.0
        )
        projected_remaining_cash_out = (
            cash_out_baseline / days_in_month * unobserved_days if days_in_month else 0.0
        )
        projected_end_balance = (
            current_bank_balance
            + projected_remaining_income
            - projected_remaining_cash_out
        )

        safe_to_spend = max(0.0, expected_income - actual_expenses - committed_remaining)
        safe_to_spend_daily = (
            safe_to_spend / days_remaining if days_remaining > 0 else safe_to_spend
        )

        # --- Daily trajectory for the chart ---
        month_start_balance = current_bank_balance - (actual_income - cash_out_to_date)
        remaining_daily_net = (
            (projected_remaining_income - projected_remaining_cash_out) / days_remaining
            if days_remaining > 0
            else 0.0
        )
        daily = []
        cumulative = 0.0
        last_actual_balance = month_start_balance
        for d in range(1, days_in_month + 1):
            date_str = month_start.replace(day=d).strftime("%Y-%m-%d")
            if d <= day_of_month:
                cumulative += float(per_day_net.get(d, 0.0))
                bal = month_start_balance + cumulative
                last_actual_balance = bal
                daily.append({
                    "date": date_str,
                    "actual_balance": round(bal, 2),
                    # anchor the projected line to today so the two segments join
                    "projected_balance": round(bal, 2) if d == day_of_month else None,
                })
            else:
                proj = last_actual_balance + remaining_daily_net * (d - day_of_month)
                daily.append({
                    "date": date_str,
                    "actual_balance": None,
                    "projected_balance": round(proj, 2),
                })

        return {
            "month": month_str,
            "days_in_month": days_in_month,
            "day_of_month": day_of_month,
            "days_remaining": days_remaining,
            "observed_through": (
                observed_through.strftime("%Y-%m-%d")
                if observed_through is not None
                else None
            ),
            "actual_income": round(actual_income, 2),
            "actual_expenses": round(actual_expenses, 2),
            "expected_income": round(expected_income, 2),
            "expected_expenses": round(expected_expenses, 2),
            "projected_net": round(projected_net, 2),
            "income_basis": income_basis,
            "recurring_income_due": round(income_due["amount"], 2),
            "recurring_income_items": income_due["items"],
            "current_bank_balance": round(current_bank_balance, 2),
            "projected_end_balance": round(projected_end_balance, 2),
            "safe_to_spend": round(safe_to_spend, 2),
            "safe_to_spend_daily": round(safe_to_spend_daily, 2),
            "avg_monthly_income": round(avg_monthly_income, 2),
            "avg_monthly_expenses": round(avg_monthly_expenses, 2),
            "committed_remaining": round(committed_remaining, 2),
            "daily": daily,
        }

    def _latest_transaction_date(
        self, month_start: pd.Timestamp, today: pd.Timestamp
    ) -> pd.Timestamp | None:
        """Latest transaction date inside the running month, if any.

        The edge of what the projection can see. Only this month counts: data
        that stops before the 1st says nothing about how far through *this*
        month the scrape got, and treating the whole month as unobserved would
        project a full month of spending onto a household that has simply not
        connected an account yet.

        Parameters
        ----------
        month_start : pd.Timestamp
            First day of the running month.
        today : pd.Timestamp
            Upper bound — a future-dated transaction is not evidence that the
            days before it were observed.

        Returns
        -------
        pd.Timestamp or None
            The latest date seen, or None when the month has no transactions.
        """
        df = self.repo.get_itemized_transactions()
        if df.empty:
            return None
        parsed = pd.to_datetime(df[TransactionsTableFields.DATE.value])
        parsed = parsed[(parsed >= month_start) & (parsed <= today)]
        if parsed.empty:
            return None
        return parsed.max().normalize()

    def get_monthly_expenses(
        self,
        exclude_pending_refunds: bool = True,
        include_projects: bool = False,
        net_refunds: bool = False,
    ) -> dict:
        """
        Get monthly expense totals and rolling averages, calculated like the monthly budget.

        Delegates filtering to ``MonthlyBudgetService.get_filtered_expenses``
        so that category exclusions, project exclusions, pending-refund
        handling, and split-parent removal are always consistent with
        the budget view.

        Parameters
        ----------
        exclude_pending_refunds : bool, optional
            When ``True``, excludes transactions marked as pending refunds.
            Default is ``True``.
        include_projects : bool, optional
            When ``True``, includes project expenses as a separate
            ``project_expenses`` field per month. Default is ``False``.
        net_refunds : bool, optional
            When ``True``, net matched refunds against the purchases they pay
            back across any month gap (see
            :meth:`BudgetService.get_filtered_expenses`). Off by default so
            the forecast's own baseline keeps the figure it has always used;
            the dashboard's expense KPI opts in. Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``months`` -- list of ``{month, expenses, project_expenses?}`` dicts.
            - ``avg_3_months`` -- average monthly expenses over the last 3 months.
            - ``avg_6_months`` -- average monthly expenses over the last 6 months.
            - ``avg_12_months`` -- average monthly expenses over the last 12 months.
        """
        from backend.services.budget_service import (
            MonthlyBudgetService,
            ProjectBudgetService,
        )

        empty_result = {
            "months": [],
            "avg_3_months": 0.0,
            "avg_6_months": 0.0,
            "avg_12_months": 0.0,
        }

        budget_service = MonthlyBudgetService(self.db)
        expenses = budget_service.get_filtered_expenses(
            exclude_pending_refunds=exclude_pending_refunds,
            net_refunds=net_refunds,
        )

        if expenses.empty:
            return empty_result

        # Group by month and sum (amounts are negative, multiply by -1)
        expenses = expenses.copy()
        expenses["month"] = to_month_series(
            expenses[TransactionsTableFields.DATE.value]
        )

        monthly = (
            expenses.groupby("month")[TransactionsTableFields.AMOUNT.value]
            .sum()
            .mul(-1)
            .sort_index()
        )

        # Optionally compute project expenses per month
        monthly_project: pd.Series | None = None
        if include_projects:
            project_service = ProjectBudgetService(self.db)
            project_names = project_service.get_all_projects_names()
            if project_names:
                all_data = budget_service.transactions_service.get_data_for_analysis()
                project_txns = all_data.loc[
                    (~all_data[TransactionsTableFields.TYPE.value].isin(["split_parent"]))
                    & all_data[TransactionsTableFields.CATEGORY.value].isin(project_names)
                ].copy()
                if not project_txns.empty:
                    project_txns["month"] = to_month_series(
                        project_txns[TransactionsTableFields.DATE.value]
                    )
                    monthly_project = (
                        project_txns.groupby("month")[TransactionsTableFields.AMOUNT.value]
                        .sum()
                        .mul(-1)
                    )

        # Build months list
        all_months = sorted(set(monthly.index) | (set(monthly_project.index) if monthly_project is not None else set()))
        months_list = []
        for month in all_months:
            entry: dict = {
                "month": month,
                "expenses": round(float(monthly.get(month, 0.0)), 2),
            }
            if include_projects:
                entry["project_expenses"] = round(
                    float(monthly_project.get(month, 0.0)) if monthly_project is not None else 0.0, 2
                )
            months_list.append(entry)

        # Calculate averages relative to current month
        today = pd.Timestamp.today()

        def avg_last_n_months(n: int) -> float:
            # Complete months only — start at i=1. Including the running month
            # divided a few days of spend by a full month and dragged the
            # trend baseline down (a 3-month average of three 3,000 months
            # came out at 2,033 on the 24th). The income baseline in
            # get_cash_flow_forecast already excludes it; these must agree.
            month_keys = [
                (today - pd.DateOffset(months=i)).strftime("%Y-%m")
                for i in range(1, n + 1)
            ]
            total = sum(monthly.get(m, 0.0) for m in month_keys)
            if include_projects and monthly_project is not None:
                total += sum(monthly_project.get(m, 0.0) for m in month_keys)
            return round(float(total / n), 2)

        return {
            "months": months_list,
            "avg_3_months": avg_last_n_months(3),
            "avg_6_months": avg_last_n_months(6),
            "avg_12_months": avg_last_n_months(12),
        }
