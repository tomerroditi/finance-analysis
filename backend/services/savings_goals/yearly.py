"""How much each calendar year saved, against the target set for it.

Provides ``YearlySavingsMixin``. Saving is measured, not earmarked: it never
depends on goal order and never touches the allocation ledger. Mixed into
``SavingsGoalService`` (see ``core.py``), because it reads the same
transaction context the waterfall does — the same card deduplication, and the
same goal rules deciding which money belongs to a goal.

What a month saved is its income minus its spending:

- **Investing is saving.** Money moved into an investment stays saved, and a
  withdrawal is neutral until it is spent. Investment gains and losses are not
  saving and never appear.
- **Loans** count as the rest of the app counts them: a loan received is
  income, a repayment is spending.
- **Money a goal's own income pays for is left out on both sides.** Income a
  goal's "saved into" rule claims (wedding gifts) is that goal's money, not the
  year's savings, and so are the bills the goal pays with it. Only bills
  beyond that income — paid with the household's own money — count as
  spending.
- **Bills paid out of a goal without an income of its own** (a trip paid for
  from savings set aside earlier) are spending in the month they happen: the
  money was saved before, and is being spent now.
"""

from datetime import date
from typing import Any

from backend.errors import ValidationException
from backend.services.savings_goals.common import iter_months, month_str


class YearlySavingsMixin:
    """Yearly savings and their targets for ``SavingsGoalService``."""

    def get_yearly_savings(self) -> dict[str, Any]:
        """Return what each year saved, its target, and this year's pace.

        Returns
        -------
        dict
            ``current_year``; ``years`` (oldest first), each with ``year``,
            ``saved``, ``target`` (``None`` when unset), ``is_current`` and
            ``months`` (``{"month": "YYYY-MM", "saved": float}`` for every
            month on record); and ``pace`` for the current year — ``None``
            without a target, else ``expected_by_today``, ``ahead_by``
            (negative when behind), ``needed_per_month`` and ``months_left``.
        """
        today = date.today()
        current = (today.year, today.month)
        monthly = self._saved_by_month(current)
        targets = self.repo.get_yearly_targets()

        by_year: dict[int, list[dict[str, Any]]] = {}
        for key, saved in monthly.items():
            by_year.setdefault(key[0], []).append(
                {"month": month_str(key), "saved": round(saved, 2) + 0.0}
            )
        by_year.setdefault(today.year, [])
        for year in targets:
            by_year.setdefault(year, [])

        years = [
            {
                "year": year,
                "saved": round(sum(row["saved"] for row in rows), 2) + 0.0,
                "target": targets.get(year),
                "is_current": year == today.year,
                "months": rows,
            }
            for year, rows in sorted(by_year.items())
            if year <= today.year
        ]
        this_year = next(row for row in years if row["is_current"])
        return {
            "current_year": today.year,
            "years": years,
            "pace": self._pace(this_year["saved"], this_year["target"], today),
        }

    def set_yearly_target(
        self, year: int, target_amount: float | None
    ) -> dict[str, Any]:
        """Set (or, with ``None``, clear) how much to save in ``year``.

        Raises
        ------
        ValidationException
            If the target is not positive.
        """
        if target_amount is not None and target_amount <= 0:
            raise ValidationException("A yearly savings target must be positive")
        self.repo.set_yearly_target(year, target_amount)
        return self.get_yearly_savings()

    def _saved_by_month(self, current: tuple[int, int]) -> dict[tuple[int, int], float]:
        """Return income minus spending for every month on record, by month."""
        context = self._build_context()
        months = [
            *context["surplus"],
            *context["direct"],
            *context["utilized"],
            *context["invested"],
        ]
        if not months:
            return {}
        own_income = {g.id for g in self._goals_in_order() if g.contribution_category}

        saved: dict[tuple[int, int], float] = {}
        # Per goal with income of its own: what it has received and spent so
        # far, and how much of that spending its income could not cover.
        received: dict[int, float] = {}
        spent: dict[int, float] = {}
        overspent: dict[int, float] = {}
        for key in iter_months(min(months), current):
            # The surplus took investing out; investing is saving.
            total = context["surplus"].get(key, 0.0) + context["invested"].get(key, 0.0)
            drawn = context["drawn"].get(key, {})
            for goal_id, amount in context["direct"].get(key, {}).items():
                if goal_id in own_income:
                    received[goal_id] = (
                        received.get(goal_id, 0.0) + amount - drawn.get(goal_id, 0.0)
                    )
            for goal_id, amount in context["utilized"].get(key, {}).items():
                if goal_id not in own_income:
                    total -= amount
                    continue
                spent[goal_id] = spent.get(goal_id, 0.0) + amount
            for goal_id in own_income:
                beyond = max(0.0, spent.get(goal_id, 0.0) - received.get(goal_id, 0.0))
                total -= beyond - overspent.get(goal_id, 0.0)
                overspent[goal_id] = beyond
            saved[key] = total
        return saved

    @staticmethod
    def _pace(saved: float, target: float | None, today: date) -> dict[str, Any] | None:
        """Where an even pace toward ``target`` would stand today."""
        if not target:
            return None
        start = date(today.year, 1, 1)
        days_in_year = (date(today.year + 1, 1, 1) - start).days
        elapsed = (today - start).days + 1
        expected = target * elapsed / days_in_year
        months_left = 12 - today.month + 1
        return {
            "expected_by_today": round(expected, 2),
            "ahead_by": round(saved - expected, 2) + 0.0,
            "needed_per_month": round(max(0.0, target - saved) / months_left, 2) + 0.0,
            "months_left": months_left,
        }
