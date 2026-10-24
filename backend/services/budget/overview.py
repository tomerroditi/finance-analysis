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

A closed project or a closed yearly envelope drops out of the envelope list
this returns while its spend stays in the month's totals — see
:meth:`BudgetOverviewService._project_envelopes` and
:meth:`BudgetOverviewService._yearly_envelopes`.

**A month's contribution to a long envelope.** Yearly and project envelopes run
on their own clock: their percentage always describes today, never the month
being viewed. ``get_yearly_budget_view`` filters on the year alone and the
project analysis has no date bound at all, so the only figure that is honestly
scoped to a viewed month is what that month *contributed*. Both facts are
returned per envelope so a caller can show them side by side under their own
headings.

Every figure here comes from one read of the claim ledger
(:mod:`backend.services.budget.ledger`), which gives each expense row one
budget month and one owning pool. The three pools are therefore disjoint by
construction, and ``total_out`` — the only figure that adds them together —
is everything the month spent.
"""

from calendar import monthrange
from typing import Any

import pandas as pd

from backend.constants.budget import (
    AMOUNT,
    CATEGORY,
    ID,
    NAME,
    TAGS,
)
from backend.constants.tables import TransactionsTableFields
from backend.services.budget import ledger
from backend.services.budget.core import BudgetService, _today
from backend.services.budget.monthly import MonthlyBudgetService
from backend.services.budget.project import ProjectBudgetService
from backend.services.budget.yearly import YearlyBudgetService
from backend.services.recurring_service import RecurringService
from backend.services.running_month import RunningMonth


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
            Accepted for API compatibility; totals never count a split parent,
            whose splits carry its amount.

        Returns
        -------
        dict
            Keys:

            - ``year``, ``month`` — the period summarised.
            - ``is_current_month`` — whether the month is still open. Committed
              charges and a projection are only meaningful when it is.
            - ``days_in_month``, ``days_elapsed``, ``days_left``.
            - ``monthly_budget`` — the month's Total Budget, or for an empty
              current/future month the one auto-fill would copy in (read, not
              written). ``0.0`` when there is none.
            - ``monthly_spent`` — the month's monthly pool: every row no
              project or yearly envelope owns, whether or not a rule names it.
            - ``fixed_spent``, ``variable_spent`` — the split of
              ``monthly_spent``. They always sum to it.
            - ``fixed_charge_count`` — how many of the month's transactions fell
              on the fixed side. Distinct from ``len(charges_due)``, which counts
              what has not happened yet.
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
            - ``long_envelopes`` — the *open* yearly and project envelopes, each
              with both ``month_contribution`` and its overall
              ``spent``/``budget``. Closed ones are omitted, though their spend
              still counts in ``yearly_month_spent`` /
              ``projects_month_spent`` and ``total_out``.
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

        claims = self.get_claims()
        month_rows = ledger.in_budget_month(claims, year, month)
        pool = ledger.of_kind(month_rows, *ledger.MONTHLY_POOL)
        monthly_spent = ledger.spent(pool)
        monthly_budget = MonthlyBudgetService(self.db).effective_total_budget(
            year, month
        )

        # Confirmed only: an unreviewed guess must never hold money back from
        # free-to-spend or move the projection.
        recurring = RecurringService(self.db).get_confirmed_items(today)

        fixed_spent, variable_spent, fixed_charge_count = self._split_fixed_variable(
            pool.to_dict(orient="records"), recurring
        )
        # The same window the forecast's committed charges use: from the day
        # the data reaches, so a bill a stale sync has not shown yet is still
        # held back rather than counted nowhere.
        charges_due = (
            RunningMonth.read(self.db, today).charges_due(recurring)
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

        long_envelopes = self._yearly_envelopes(
            claims, month_rows, year
        ) + self._project_envelopes(claims, month_rows)
        yearly_month_spent = float(
            sum(
                e["month_contribution"] for e in long_envelopes if e["kind"] == "yearly"
            )
        )
        projects_month_spent = float(
            sum(
                e["month_contribution"]
                for e in long_envelopes
                if e["kind"] == "project"
            )
        )
        # The totals above count every envelope, closed ones included — that
        # money really did leave the accounts this month. The list below is a
        # list of envelopes still worth watching, so closed ones drop out of
        # it, and out of every section built from it.
        open_envelopes = [
            {key: value for key, value in envelope.items() if key != "closed"}
            for envelope in long_envelopes
            if not envelope["closed"]
        ]

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
            "fixed_charge_count": fixed_charge_count,
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
            "total_out": round(ledger.spent(month_rows), 2),
            "long_envelopes": open_envelopes,
        }

    # ------------------------------------------------------------------ #
    # Monthly pool
    # ------------------------------------------------------------------ #

    @staticmethod
    def _split_fixed_variable(
        month_data: list[dict[str, Any]], recurring: list[dict[str, Any]]
    ) -> tuple[float, float, int]:
        """Split a month's transactions into recurring and day-to-day spend.

        A transaction counts as fixed when its description normalises onto a
        detected recurring charge. Detection status is deliberately ignored: a
        subscription that has since ended was still a fixed charge in the months
        it ran, and a past month must not be reclassified by what happens to be
        live today. Everything else is day-to-day. Refunds inside a month can
        make either side negative; both are left signed so the two always sum
        back to the month's total.

        Also returns how many of the month's transactions landed on the fixed
        side, which is what a caption about charges *already taken* needs — not
        the number still due, which is a different figure entirely.
        """
        if not month_data:
            return 0.0, 0.0, 0
        keys = {item["normalized"] for item in recurring if item.get("normalized")}
        description = TransactionsTableFields.DESCRIPTION.value
        amount = TransactionsTableFields.AMOUNT.value
        fixed = 0.0
        variable = 0.0
        fixed_count = 0
        for txn in month_data:
            value = float(txn.get(amount) or 0.0) * -1
            if RecurringService.normalize_description(txn.get(description)) in keys:
                fixed += value
                fixed_count += 1
            else:
                variable += value
        return fixed, variable, fixed_count

    # ------------------------------------------------------------------ #
    # Yearly and project envelopes
    # ------------------------------------------------------------------ #

    def _yearly_envelopes(
        self, claims: pd.DataFrame, month_rows: pd.DataFrame, year: int
    ) -> list[dict[str, Any]]:
        """Return yearly rules with their year-to-date spend and this month's share.

        ``month_contribution`` is scoped to the viewed month; ``spent`` and
        ``budget`` describe the envelope as a whole and therefore always
        describe today. Callers must label the two differently.

        Every rule for the year is measured, closed ones included, and each
        carries a ``closed`` flag :meth:`get_overview` uses to drop it from the
        list it returns — an annual bill the user has marked settled is no
        longer an envelope this month is measured against, and one sitting at
        100% would otherwise stay pinned to the top of "needs attention" for
        the rest of the year. Its spend still counts towards the month's
        totals, and the Yearly tab still shows it in full.
        """
        yearly = YearlyBudgetService(self.db)
        rules = yearly.get_year_rules(year)
        if rules.empty:
            return []
        year_rows = (
            claims.loc[claims[ledger.BUDGET_YEAR] == year]
            if not claims.empty
            else claims
        )
        return [
            {
                "name": str(rule[NAME] or ""),
                "kind": "yearly",
                "category": str(rule[CATEGORY] or ""),
                "month_contribution": round(
                    ledger.spent(ledger.of_rule(month_rows, rule[ID])), 2
                ),
                "spent": round(ledger.spent(ledger.of_rule(year_rows, rule[ID])), 2),
                "budget": round(float(rule[AMOUNT] or 0.0), 2),
                # Measured either way; get_overview is what drops the
                # closed ones, so their spend still reaches the totals.
                "closed": yearly.rule_is_closed(rule),
            }
            for _, rule in rules.iterrows()
        ]

    def _project_envelopes(
        self, claims: pd.DataFrame, month_rows: pd.DataFrame
    ) -> list[dict[str, Any]]:
        """Return projects with their lifetime spend and this month's share.

        A project has no calendar at all, so ``spent`` is lifetime-to-date by
        definition, never bounded to the viewed month.

        Every project is measured, closed ones included, but each carries a
        ``closed`` flag that :meth:`get_overview` uses to drop it from the
        envelope list it returns. A finished renovation is not an envelope the
        current month can still be measured against, and a completed one
        sitting at 100% would otherwise keep itself pinned to the top of "needs
        attention" forever. Its spend still counts towards the month's totals,
        because that money did leave the accounts, and its history is
        untouched — the Projects tab still shows it in full.
        """
        projects = ProjectBudgetService(self.db)
        closed = set(projects.get_closed_projects_names())
        names = projects.get_all_projects_names()
        if not names:
            return []

        rules = projects.get_all_rules()
        category = TransactionsTableFields.CATEGORY.value
        lifetime = ledger.of_kind(claims, ledger.KIND_PROJECT)
        this_month = ledger.of_kind(month_rows, ledger.KIND_PROJECT)
        return [
            {
                "name": str(name),
                "kind": "project",
                "category": str(name),
                "month_contribution": round(
                    ledger.spent(this_month.loc[this_month[category] == name]), 2
                ),
                "spent": round(
                    ledger.spent(lifetime.loc[lifetime[category] == name]), 2
                ),
                "budget": round(
                    self._project_budget(rules[rules[CATEGORY] == name]), 2
                ),
                "closed": name in closed,
            }
            for name in names
        ]

    @staticmethod
    def _project_budget(project_rules: pd.DataFrame) -> float:
        """Return one project's total budget, across both rule shapes in the wild.

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
        anchor = project_rules[project_rules[TAGS].apply(BudgetService._is_all_tags)]
        if not anchor.empty:
            return float(anchor.iloc[0][AMOUNT] or 0.0)
        return float(project_rules[AMOUNT].max() or 0.0)
