"""Investment earmarks for the savings-goal service.

Provides ``InvestmentBackingMixin``: back a goal with an investment holding
the user means to liquidate, release that earmark, and list earmarks and the
headroom left on each open holding. Mixed into ``SavingsGoalService`` (see
``core.py``).
"""

from typing import Any

import pandas as pd

from backend.errors import EntityNotFoundException, ValidationException
from backend.services.investments import InvestmentsService
from backend.services.savings_goals.common import ROUNDING_EPSILON


class InvestmentBackingMixin:
    """Investment-earmark methods for ``SavingsGoalService``."""

    def link_investment(
        self, goal_id: int, investment_id: int, amount: float | None = None
    ) -> list[dict[str, Any]]:
        """Earmark an investment holding against a goal.

        Parameters
        ----------
        goal_id : int
            Goal to back.
        investment_id : int
            Open investment whose value backs it.
        amount : float or None, optional
            How much of the holding to earmark. ``None`` earmarks whatever is
            left of it, which keeps the goal tracking the holding's value
            without the user retyping a number.

        Returns
        -------
        list[dict]
            The refreshed goals.

        Raises
        ------
        EntityNotFoundException
            The goal or the investment does not exist.
        ValidationException
            The investment is closed, the amount is not positive, or the
            earmarks against that holding would exceed what it is worth.
        """
        if not self.repo.get(goal_id):
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        if amount is not None and amount <= 0:
            raise ValidationException("amount must be greater than zero")

        investment = self._require_open_investment(investment_id)
        self._validate_backing_capacity(
            investment_id, investment["balance"], goal_id, amount
        )

        self.repo.upsert_backing(goal_id, investment_id, amount)
        self._backing_cache = None
        return self._after_write()

    def unlink_investment(self, backing_id: int) -> list[dict[str, Any]]:
        """Release an investment earmark.

        Parameters
        ----------
        backing_id : int
            Earmark to remove.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the earmark does not exist.
        """
        try:
            self.repo.delete_backing(backing_id)
        except ValueError as exc:
            raise EntityNotFoundException(
                f"Savings goal investment {backing_id} not found"
            ) from exc
        self._backing_cache = None
        return self._after_write()

    def get_investment_backings(
        self, goal_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Return investment earmarks, each with the holding's live value.

        Parameters
        ----------
        goal_id : int or None, optional
            Restrict to one goal. ``None`` returns every earmark.

        Returns
        -------
        list[dict]
            Rows carrying the investment's ``name``/``type``, the requested
            ``amount`` (``None`` for a whole-holding earmark) and the
            ``value`` actually backing the goal right now.
        """
        backings = self.repo.get_backings(goal_id)
        if backings.empty:
            return []

        investments = {
            record["id"]: record
            for record in InvestmentsService(self.db).get_all_investments(
                include_closed=True
            )
        }
        # Resolve values through the same waterfall the engine uses, so a
        # shrunken holding reports the same split here as it funds with.
        per_goal_totals = self._investment_backing()

        rows = []
        for row in backings.itertuples(index=False):
            investment = investments.get(int(row.investment_id), {})
            rows.append(
                {
                    "id": int(row.id),
                    "goal_id": int(row.goal_id),
                    "investment_id": int(row.investment_id),
                    "investment_name": investment.get("name"),
                    "investment_type": investment.get("type"),
                    "is_closed": bool(investment.get("is_closed")),
                    "amount": None if pd.isna(row.amount) else float(row.amount),
                    "goal_backed_total": round(
                        per_goal_totals.get(int(row.goal_id), 0.0), 2
                    ),
                }
            )
        return rows

    def get_available_investments(self) -> list[dict[str, Any]]:
        """Return open investments with how much of each is still unearmarked.

        Backs the picker: a holding already fully spoken for should not look
        available, and one partly earmarked should show only its headroom.

        Returns
        -------
        list[dict]
            One row per open investment: ``id``, ``name``, ``type``, live
            ``value``, explicitly ``earmarked`` amount, ``available`` headroom
            and ``fully_claimed`` (a goal holds the whole-remainder earmark).
        """
        backings = self.repo.get_backings()
        claimed: dict[int, float] = {}
        whole: set[int] = set()
        if not backings.empty:
            for row in backings.itertuples(index=False):
                investment_id = int(row.investment_id)
                if pd.isna(row.amount):
                    whole.add(investment_id)
                else:
                    claimed[investment_id] = claimed.get(investment_id, 0.0) + float(
                        row.amount
                    )

        investments = InvestmentsService(self.db)
        rows = []
        for record in investments.get_all_investments(include_closed=False):
            investment_id = int(record["id"])
            value = float(investments.calculate_current_balance(investment_id))
            spoken_for = claimed.get(investment_id, 0.0)
            rows.append(
                {
                    "id": investment_id,
                    "name": record.get("name"),
                    "type": record.get("type"),
                    "value": round(value, 2),
                    "earmarked": round(spoken_for, 2),
                    "available": 0.0
                    if investment_id in whole
                    else round(max(0.0, value - spoken_for), 2),
                    "fully_claimed": investment_id in whole,
                }
            )
        return rows

    def _require_open_investment(self, investment_id: int) -> dict[str, Any]:
        """Return an open investment's record plus its live balance.

        Looked up through the full listing rather than ``get_investment``,
        which indexes straight into an empty frame for an unknown id and
        raises ``IndexError`` instead of a domain error.
        """
        investments = InvestmentsService(self.db)
        record = next(
            (
                candidate
                for candidate in investments.get_all_investments(include_closed=True)
                if int(candidate["id"]) == investment_id
            ),
            None,
        )
        if record is None:
            raise EntityNotFoundException(f"Investment {investment_id} not found")
        if record.get("is_closed"):
            raise ValidationException(
                f"Investment {investment_id} is closed and cannot back a goal"
            )
        record["balance"] = float(investments.calculate_current_balance(investment_id))
        return record

    def _validate_backing_capacity(
        self,
        investment_id: int,
        value: float,
        goal_id: int,
        amount: float | None,
    ) -> None:
        """Reject an earmark that would claim more of a holding than it holds.

        A holding can back several goals, but only up to what it is worth —
        otherwise two goals would both count the same bond and progress would
        be fiction. At most one goal may take the "whatever is left" earmark.
        """
        existing = self.repo.get_backings()
        others = (
            existing[
                (existing["investment_id"] == investment_id)
                & (existing["goal_id"] != goal_id)
            ]
            if not existing.empty
            else existing
        )
        if others.empty:
            claimed, has_whole = 0.0, False
        else:
            claimed = float(others["amount"].sum(skipna=True))
            has_whole = bool(others["amount"].isna().any())

        if amount is None:
            if has_whole:
                raise ValidationException(
                    "Another goal already earmarks the remainder of this "
                    "investment; give this one an explicit amount"
                )
            if claimed >= value:
                raise ValidationException(
                    "This investment is already fully earmarked by other goals"
                )
            return

        headroom = value - claimed
        if amount > headroom + ROUNDING_EPSILON:
            raise ValidationException(
                f"Only {round(max(0.0, headroom), 2)} of this investment is "
                f"still unearmarked"
            )
