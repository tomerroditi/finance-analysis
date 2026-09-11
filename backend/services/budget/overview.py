"""Budget overview service — the cross-kind read model behind the Overview tab.

The Overview answers a question none of the per-kind tabs can: how is the whole
budget doing, across monthly envelopes, yearly envelopes and projects at once.
Two of the facts it needs exist nowhere else in the API.

**Fixed vs variable.** A month is not spent evenly — rent, school fees and
insurances land in the first days — so comparing spend against elapsed days
calls every first week an overspend. Instead the month's monthly-pool spend is
split into recurring charges that were always going to happen and day-to-day
spend, and the recurring charges still due before month end are held back as
*committed*. Deciding whether a transaction is one of those recurring charges
relies on :meth:`RecurringService.normalize_description`, so the split has to
happen here rather than in the client, where the normalisation rules would have
to be duplicated and would silently drift.

**A month's contribution to a long envelope.** Yearly and project envelopes run
on their own clock: their percentage always describes today, never the month
being viewed. ``get_yearly_budget_view`` filters on the year alone and the
project analysis has no date bound at all, so the only figure that is honestly
scoped to a viewed month is what that month *contributed*. Both facts are
returned per envelope so a caller can show them side by side under their own
headings.

The three pools are genuinely separate, which is easy to get wrong when they sit
next to each other: :meth:`BudgetService.get_filtered_expenses` drops project
categories and :meth:`MonthlyBudgetService._exclude_yearly_claimed` drops
yearly-claimed spend, so neither is inside the monthly budget. ``total_out`` is
the only figure here that adds the three together.
"""

from calendar import monthrange
from typing import Any, Optional

import pandas as pd

from backend.constants.budget import ALL_TAGS, AMOUNT, CATEGORY, NAME, TAGS, TOTAL_BUDGET
from backend.constants.tables import TransactionsTableFields
from backend.services.budget.core import BudgetService, _today
from backend.services.budget.monthly import MonthlyBudgetService
from backend.services.budget.project import ProjectBudgetService
from backend.services.budget.yearly import YearlyBudgetService
from backend.services.recurring_service import RecurringService


def _is_all_tags(tags: Optional[list[str]]) -> bool:
    """Whether a rule's tags are the ``all_tags`` marker rather than real tags."""
    parsed = list(tags or [])
    return [str(tag).lower() for tag in parsed] == [ALL_TAGS.lower()]


class BudgetOverviewService(BudgetService):
    """Cross-kind roll-up of a single month for the budget Overview."""

    def get_overview(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict[str, Any]:
        """Summarise one month across monthly, yearly and project budgets.

        Parameters
        ----------
        year : int
            Calendar year of the month to summarise.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include the original parent transactions of splits
            alongside the split rows. Defaults to ``False``.

        Returns
        -------
        dict
            Keys:

            - ``year``, ``month`` — the period summarised.
            - ``is_current_month`` — whether the month is still open. Committed
              charges and a projection are only meaningful when it is.
            - ``days_in_month``, ``days_elapsed``, ``days_left``.
            - ``monthly_budget``, ``monthly_spent`` — the Total Budget rule and
              spend against it. Both ``0.0`` when no Total Budget rule exists.
            - ``fixed_spent``, ``variable_spent`` — the split of
              ``monthly_spent``. They always sum to it.
            - ``committed_remaining`` — recurring charges still due this month.
              ``0.0`` for any month that is not current.
            - ``free_to_spend`` — budget less spend less commitments. Negative
              when the month is already past its budget.
            - ``variable_per_day`` — variable spend over elapsed days.
            - ``projected`` — spend plus commitments plus the variable rate for
              the days left. ``None`` when the month is not current, because a
              settled month has a final figure rather than a projection.
            - ``charges_due`` — the individual charges behind
              ``committed_remaining``, each ``{label, amount, expected_date}``.
            - ``projects_month_spent``, ``yearly_month_spent`` — what the month
              put into the other two pools, neither of which is inside
              ``monthly_spent``.
            - ``total_out`` — the three pools added up: what actually left the
              accounts in the month.
            - ``long_envelopes`` — yearly and project envelopes, each with both
              ``month_contribution`` and its overall ``spent``/``budget``.
        """
        today = _today()
        days_in_month = monthrange(year, month)[1]
        is_current = year == today.year and month == today.month
        if is_current:
            days_elapsed = today.day
        elif (year, month) < (today.year, today.month):
            days_elapsed = days_in_month
        else:
            days_elapsed = 0
        days_left = days_in_month - days_elapsed

        monthly_spent, monthly_budget, month_data = self._monthly_totals(
            year, month, include_split_parents
        )

        recurring = RecurringService(self.db).get_recurring().get("items", [])

        fixed_spent, variable_spent = self._split_fixed_variable(month_data, recurring)
        charges_due = (
            self._charges_due(recurring, year, month, today.isoformat())
            if is_current
            else []
        )
        committed_remaining = float(sum(charge["amount"] for charge in charges_due))

        variable_per_day = variable_spent / days_elapsed if days_elapsed else 0.0
        projected = (
            monthly_spent + committed_remaining + variable_per_day * days_left
            if is_current
            else None
        )

        long_envelopes = self._long_envelopes(year, month, include_split_parents)
        yearly_month_spent = float(
            sum(e["month_contribution"] for e in long_envelopes if e["kind"] == "yearly")
        )
        projects_month_spent = float(
            sum(
                e["month_contribution"] for e in long_envelopes if e["kind"] == "project"
            )
        )

        return {
            "year": year,
            "month": month,
            "is_current_month": is_current,
            "days_in_month": days_in_month,
            "days_elapsed": days_elapsed,
            "days_left": days_left,
            "monthly_budget": round(monthly_budget, 2),
            "monthly_spent": round(monthly_spent, 2),
            "fixed_spent": round(fixed_spent, 2),
            "variable_spent": round(variable_spent, 2),
            "committed_remaining": round(committed_remaining, 2),
            "free_to_spend": round(
                monthly_budget - monthly_spent - committed_remaining, 2
            ),
            "variable_per_day": round(variable_per_day, 2),
            "projected": None if projected is None else round(projected, 2),
            "charges_due": charges_due,
            "projects_month_spent": round(projects_month_spent, 2),
            "yearly_month_spent": round(yearly_month_spent, 2),
            "total_out": round(
                monthly_spent + projects_month_spent + yearly_month_spent, 2
            ),
            "long_envelopes": long_envelopes,
        }

    # ------------------------------------------------------------------ #
    # Monthly pool
    # ------------------------------------------------------------------ #

    def _monthly_totals(
        self, year: int, month: int, include_split_parents: bool
    ) -> tuple[float, float, list[dict]]:
        """Return ``(spent, budget, transactions)`` for the monthly pool.

        The Total Budget row already carries the month's monthly-pool
        transactions — project categories and yearly-claimed spend removed — so
        it is both the figure the page shows and the exact set the fixed/variable
        split must run over. A month with no Total Budget rule has no monthly
        budget to speak of, and yields zeroes rather than an error.

        Goes through ``get_monthly_analysis`` rather than the raw view because
        only the analysis auto-fills an empty current month from the last month
        that had rules. Reading the view directly made the Overview report a
        zero budget for the live month until the user happened to open the
        Monthly tab and trigger the fill.
        """
        analysis = MonthlyBudgetService(self.db).get_monthly_analysis(
            year, month, include_split_parents
        )
        view = analysis.get("rules") or []
        if not view:
            return 0.0, 0.0, []
        for entry in view:
            rule = entry.get("rule") or {}
            if rule.get(CATEGORY) == TOTAL_BUDGET:
                return (
                    float(entry.get("current_amount") or 0.0),
                    float(rule.get(AMOUNT) or 0.0),
                    entry.get("data") or [],
                )
        return 0.0, 0.0, []

    @staticmethod
    def _split_fixed_variable(
        month_data: list[dict], recurring: list[dict]
    ) -> tuple[float, float]:
        """Split a month's transactions into recurring and day-to-day spend.

        A transaction counts as fixed when its description normalises onto a
        detected recurring charge. Detection status is deliberately ignored: a
        subscription that has since ended was still a fixed charge in the months
        it ran, and a past month must not be reclassified by what happens to be
        live today. Everything else is day-to-day. Refunds inside a month can
        make either side negative; both are left signed so the two always sum
        back to the month's total.
        """
        if not month_data:
            return 0.0, 0.0
        keys = {item["normalized"] for item in recurring if item.get("normalized")}
        description = TransactionsTableFields.DESCRIPTION.value
        amount = TransactionsTableFields.AMOUNT.value
        fixed = 0.0
        variable = 0.0
        for txn in month_data:
            value = float(txn.get(amount) or 0.0) * -1
            if RecurringService.normalize_description(txn.get(description)) in keys:
                fixed += value
            else:
                variable += value
        return fixed, variable

    @staticmethod
    def _charges_due(
        recurring: list[dict], year: int, month: int, today_iso: str
    ) -> list[dict]:
        """List recurring charges expected between today and the month's end.

        ``next_expected_date`` is the detector's last sighting plus one period,
        so a charge that already landed this month has rolled on to the next and
        is correctly absent — it is already counted as fixed spend.

        The date window is the only liveness test needed. A charge the detector
        calls ``ended`` was last seen more than one and a half periods ago, which
        puts its next expected date in the past by at least half a period, so it
        can never fall inside this window.
        """
        last_day = monthrange(year, month)[1]
        month_end = f"{year:04d}-{month:02d}-{last_day:02d}"
        due = []
        for item in recurring:
            expected = item.get("next_expected_date")
            if not expected or not (today_iso <= expected <= month_end):
                continue
            due.append(
                {
                    "label": item.get("label") or item.get("normalized") or "",
                    "amount": round(float(item.get("amount") or 0.0), 2),
                    "expected_date": expected,
                }
            )
        due.sort(key=lambda charge: charge["expected_date"])
        return due

    # ------------------------------------------------------------------ #
    # Yearly and project envelopes
    # ------------------------------------------------------------------ #

    def _long_envelopes(
        self, year: int, month: int, include_split_parents: bool
    ) -> list[dict]:
        """Yearly and project envelopes, each with its month share and standing.

        ``month_contribution`` is scoped to the viewed month; ``spent`` and
        ``budget`` describe the envelope as a whole and therefore always
        describe today. Callers must label the two differently — that pairing is
        the whole reason this method exists.
        """
        return self._yearly_envelopes(
            year, month, include_split_parents
        ) + self._project_envelopes(year, month, include_split_parents)

    def _yearly_envelopes(
        self, year: int, month: int, include_split_parents: bool
    ) -> list[dict]:
        """Yearly rules with their year-to-date spend and this month's share.

        The month share is taken on the transaction's own date rather than its
        budget month: a month override moves spend between *monthly* envelopes,
        and must not shuffle a yearly envelope's history.
        """
        yearly = YearlyBudgetService(self.db)
        rules = yearly.get_year_rules(year)
        if rules.empty:
            return []

        expenses = self.get_filtered_expenses(
            exclude_pending_refunds=True, include_split_parents=include_split_parents
        )
        month_data = self._rows_in_month(expenses, year, month)

        view = yearly.get_yearly_budget_view(year, include_split_parents) or []
        spent_by_name = {
            (entry.get("rule") or {}).get(NAME): float(entry.get("current_amount") or 0.0)
            for entry in view
        }

        envelopes = []
        for _, rule in rules.iterrows():
            matched = self._rows_for_rule(month_data, rule[CATEGORY], rule[TAGS])
            envelopes.append(
                {
                    "name": str(rule[NAME] or ""),
                    "kind": "yearly",
                    "category": str(rule[CATEGORY] or ""),
                    "month_contribution": round(self._sum_expenses(matched), 2),
                    "spent": round(spent_by_name.get(rule[NAME], 0.0), 2),
                    "budget": round(float(rule[AMOUNT] or 0.0), 2),
                }
            )
        return envelopes

    def _project_envelopes(
        self, year: int, month: int, include_split_parents: bool
    ) -> list[dict]:
        """Projects with their lifetime spend and this month's share.

        A project has no calendar at all, so ``spent`` is lifetime-to-date by
        definition, never bounded to the viewed month.
        """
        projects = ProjectBudgetService(self.db)
        names = projects.get_all_projects_names()
        if not names:
            return []

        rules = projects.get_all_rules()

        all_data = projects.transactions_service.get_data_for_analysis(
            include_split_parents
        )
        if not all_data.empty and "type" in all_data.columns:
            all_data = all_data[all_data["type"] != "split_parent"]

        category = TransactionsTableFields.CATEGORY.value
        envelopes = []
        for name in names:
            budget = self._project_budget(rules[rules[CATEGORY] == name])
            rows = (
                all_data[all_data[category] == name]
                if not all_data.empty
                else all_data
            )
            envelopes.append(
                {
                    "name": str(name),
                    "kind": "project",
                    "category": str(name),
                    "month_contribution": round(
                        self._sum_expenses(self._rows_in_month(rows, year, month)), 2
                    ),
                    "spent": round(self._sum_expenses(rows), 2),
                    "budget": round(budget, 2),
                }
            )
        return envelopes

    @staticmethod
    def _project_budget(project_rules: pd.DataFrame) -> float:
        """The total budget for one project, across both rule shapes in the wild.

        ``create_project`` writes an anchor rule tagged ``all_tags`` holding the
        whole budget, with a zero-budget rule per tag beside it — that anchor is
        what :meth:`ProjectBudgetService.get_project_budget_view` looks for.
        Projects that predate it (the demo database among them) instead carry a
        single rule tagged with every tag in the project, holding the budget.
        Matching only the anchor reports those projects as having no budget at
        all, and summing the rules would double-count a project whose per-tag
        budgets have been filled in. So: take the anchor when there is one, and
        otherwise the largest rule, which is the one covering the project.
        """
        if project_rules.empty:
            return 0.0
        anchor = project_rules[project_rules[TAGS].apply(_is_all_tags)]
        if not anchor.empty:
            return float(anchor.iloc[0][AMOUNT] or 0.0)
        return float(project_rules[AMOUNT].max() or 0.0)

    # ------------------------------------------------------------------ #
    # Frame helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rows_in_month(rows: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
        """Restrict rows to one calendar month by transaction date."""
        if rows is None or rows.empty:
            return rows
        dates = pd.to_datetime(rows[TransactionsTableFields.DATE.value])
        return rows.loc[(dates.dt.year == year) & (dates.dt.month == month)]

    @staticmethod
    def _rows_for_rule(
        rows: pd.DataFrame, category: str, tags: Optional[list[str]]
    ) -> pd.DataFrame:
        """Restrict rows to those a ``(category, tags)`` envelope claims."""
        if rows is None or rows.empty:
            return rows
        matched = rows[rows[TransactionsTableFields.CATEGORY.value] == category]
        if not _is_all_tags(tags):
            matched = matched[
                matched[TransactionsTableFields.TAG.value].isin(list(tags or []))
            ]
        return matched

    @staticmethod
    def _sum_expenses(rows: pd.DataFrame) -> float:
        """Sum a frame's amounts as positive expense values."""
        if rows is None or rows.empty:
            return 0.0
        return float(rows[TransactionsTableFields.AMOUNT.value].sum() * -1)
