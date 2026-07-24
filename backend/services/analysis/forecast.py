"""
Cash-flow forecasting for the analysis service.

Provides the ``ForecastMixin`` with the current-month cash-flow
projection ("This Month" hero) and the monthly-expense trend helper it
builds on. Mixed into ``AnalysisService`` (see ``core.py``).
"""

import pandas as pd

from backend.constants.tables import TransactionsTableFields


class ForecastMixin:
    """Forecasting methods for ``AnalysisService``."""

    def get_cash_flow_forecast(self) -> dict:
        """Forecast the current month's cash flow from trend + month-to-date actuals.

        Projects where the month will end by combining what has already
        happened this month (income received, expenses spent) with a
        trend-based estimate of the remaining days. The expense trend is the
        rolling 3-month average (falling back to 6/12-month when sparse); the
        income trend is the average of the last 3 complete months. The
        projection never dips below money already spent.

        This is the data behind the dashboard "This Month" hero — the
        month-end balance projection and the "safe to spend" figure that
        Israeli budgeting apps (RiseUp et al.) lead with.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``month`` – current month in ``YYYY-MM`` format.
            - ``days_in_month`` / ``day_of_month`` / ``days_remaining`` – ints.
            - ``actual_income`` / ``actual_expenses`` – month-to-date totals
              (non-negative; expenses are the absolute value of outflows).
            - ``expected_income`` / ``expected_expenses`` – projected
              full-month totals.
            - ``projected_net`` – ``expected_income - expected_expenses``.
            - ``current_bank_balance`` – sum of tracked bank balances now.
            - ``projected_end_balance`` – bank balance projected to month end.
            - ``safe_to_spend`` – money left to spend freely this month:
              ``expected_income - actual_expenses - committed_remaining``
              (non-negative).
            - ``safe_to_spend_daily`` – ``safe_to_spend`` spread over the
              remaining days.
            - ``avg_monthly_income`` / ``avg_monthly_expenses`` – the trend
              baselines used.
            - ``committed_remaining`` – detected recurring charges whose next
              due date falls in the remainder of this month.
            - ``daily`` – per-day list of ``{date, actual_balance,
              projected_balance}`` for the trajectory chart (one is null
              depending on whether the day is past or future).
        """
        today = pd.Timestamp.today().normalize()
        month_str = today.strftime("%Y-%m")
        month_start = today.replace(day=1)
        days_in_month = int(today.days_in_month)
        day_of_month = int(today.day)
        days_remaining = days_in_month - day_of_month

        # --- Trend baselines (complete months only) ---
        monthly_exp = self.get_monthly_expenses(exclude_pending_refunds=True)
        avg_monthly_expenses = monthly_exp.get("avg_3_months", 0.0) or 0.0
        if avg_monthly_expenses <= 0:
            avg_monthly_expenses = (
                monthly_exp.get("avg_6_months", 0.0)
                or monthly_exp.get("avg_12_months", 0.0)
                or 0.0
            )

        ie_over_time = self.get_income_expenses_over_time()
        complete_months = [m for m in ie_over_time if m["month"] < month_str]
        recent = complete_months[-3:] if len(complete_months) >= 3 else complete_months
        avg_monthly_income = (
            sum(m["income"] for m in recent) / len(recent) if recent else 0.0
        )

        # --- Month-to-date actuals (non-CC cashflow) ---
        df = self.repo.get_cashflow_transactions()
        actual_income = 0.0
        actual_expenses = 0.0
        per_day_net: dict[int, float] = {}
        if not df.empty:
            df = df.copy()
            df["date_parsed"] = pd.to_datetime(df["date"])
            mtd = df[(df["date_parsed"] >= month_start) & (df["date_parsed"] <= today)]
            if not mtd.empty:
                actual_income, _, actual_expenses = self.get_income_investments_and_expenses(mtd)
                per_day_net = (
                    mtd.groupby(mtd["date_parsed"].dt.day)["amount"].sum().to_dict()
                )

        # --- Current bank balance ---
        balances = self.bank_balance_service.get_all_balances()
        current_bank_balance = float(sum(b["balance"] for b in balances)) if balances else 0.0

        # --- Projection ---
        trend_daily_expense = avg_monthly_expenses / days_in_month if days_in_month else 0.0
        projected_remaining_expenses = max(0.0, trend_daily_expense * days_remaining)
        expected_expenses = actual_expenses + projected_remaining_expenses
        expected_income = max(actual_income, avg_monthly_income)
        projected_remaining_income = max(0.0, expected_income - actual_income)
        projected_net = expected_income - expected_expenses
        projected_end_balance = (
            current_bank_balance + projected_remaining_income - projected_remaining_expenses
        )

        # --- Known upcoming recurring charges still due this month ---
        # Detected subscriptions/bills whose next expected charge falls in the
        # remainder of the month. Subtracted from "safe to spend" so the figure
        # reflects money still earmarked for committed bills, not just income
        # minus what's been spent so far.
        from backend.services.recurring_service import RecurringService

        month_end = today + pd.offsets.MonthEnd(0)
        committed_remaining = 0.0
        for item in RecurringService(self.db).get_recurring()["items"]:
            if item["status"] == "ended":
                continue
            next_due = pd.Timestamp(item["next_expected_date"])
            if today < next_due <= month_end:
                committed_remaining += item["amount"]

        safe_to_spend = max(0.0, expected_income - actual_expenses - committed_remaining)
        safe_to_spend_daily = (
            safe_to_spend / days_remaining if days_remaining > 0 else safe_to_spend
        )

        # --- Daily trajectory for the chart ---
        month_start_balance = current_bank_balance - (actual_income - actual_expenses)
        remaining_daily_net = (
            (projected_remaining_income - projected_remaining_expenses) / days_remaining
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
            "actual_income": round(actual_income, 2),
            "actual_expenses": round(actual_expenses, 2),
            "expected_income": round(expected_income, 2),
            "expected_expenses": round(expected_expenses, 2),
            "projected_net": round(projected_net, 2),
            "current_bank_balance": round(current_bank_balance, 2),
            "projected_end_balance": round(projected_end_balance, 2),
            "safe_to_spend": round(safe_to_spend, 2),
            "safe_to_spend_daily": round(safe_to_spend_daily, 2),
            "avg_monthly_income": round(avg_monthly_income, 2),
            "avg_monthly_expenses": round(avg_monthly_expenses, 2),
            "committed_remaining": round(committed_remaining, 2),
            "daily": daily,
        }

    def get_monthly_expenses(
        self,
        exclude_pending_refunds: bool = True,
        include_projects: bool = False,
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
        )

        if expenses.empty:
            return empty_result

        # Group by month and sum (amounts are negative, multiply by -1)
        expenses = expenses.copy()
        expenses["month"] = expenses[
            TransactionsTableFields.DATE.value
        ].dt.strftime("%Y-%m")

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
                    project_txns[TransactionsTableFields.DATE.value] = pd.to_datetime(
                        project_txns[TransactionsTableFields.DATE.value]
                    )
                    project_txns["month"] = project_txns[
                        TransactionsTableFields.DATE.value
                    ].dt.strftime("%Y-%m")
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
