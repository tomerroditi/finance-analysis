"""Goal CRUD and transaction links for the savings-goal service.

Provides ``GoalCrudMixin``: create/update/delete/reorder/close/reopen a goal,
and attach or detach transactions as contributions or utilizations. Every
write refreshes the allocation ledger before returning the goals. Mixed into
``SavingsGoalService`` (see ``core.py``).
"""

from datetime import date
from typing import Any

import numpy as np

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
)
from backend.services.savings_goals.common import month_key, month_str


class GoalCrudMixin:
    """Goal lifecycle and transaction-link methods for ``SavingsGoalService``."""

    def create(self, **fields: Any) -> list[dict[str, Any]]:
        """Create a new savings goal at the bottom of the waterfall.

        Parameters
        ----------
        **fields : Any
            Goal columns. ``priority`` defaults to the bottom of the waterfall
            and ``start_month`` to the current month; ``None`` values are
            dropped.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        ValidationException
            If ``start_month`` is not a parseable ``YYYY-MM`` string.
        """
        fields.setdefault("priority", self.repo.next_priority())
        if not fields.get("start_month"):
            today = date.today()
            fields["start_month"] = month_str((today.year, today.month))
        self._validate_month(fields.get("start_month"), "start_month")
        self.repo.add(**{k: v for k, v in fields.items() if v is not None})
        return self._after_write()

    def update(self, goal_id: int, **fields: Any) -> list[dict[str, Any]]:
        """Update an existing savings goal.

        Parameters
        ----------
        goal_id : int
            Goal to update.
        **fields : Any
            Columns to change; ``None`` clears a column.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        ValidationException
            If ``start_month`` is not a parseable ``YYYY-MM`` string.
        """
        if "start_month" in fields:
            self._validate_month(fields["start_month"], "start_month")
        try:
            self.repo.update(goal_id, **fields)
        except ValueError as exc:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found") from exc
        return self._after_write()

    def delete(self, goal_id: int) -> None:
        """Delete a savings goal and everything attached to it.

        Parameters
        ----------
        goal_id : int
            Goal to delete.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        """
        try:
            self.repo.delete(goal_id)
        except ValueError as exc:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found") from exc

    def reorder(self, ordered_ids: list[int]) -> list[dict[str, Any]]:
        """Set the waterfall order; the first id is funded first.

        New priorities take effect from the next allocation run forward.
        Already-written months keep their amounts until an explicit
        :meth:`rebuild` restates them.

        Parameters
        ----------
        ordered_ids : list[int]
            Goal ids, highest priority first.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If any id is not a known goal.
        """
        all_goals = self.repo.get_all()
        known = set(all_goals["id"]) if not all_goals.empty else set()
        unknown = [gid for gid in ordered_ids if gid not in known]
        if unknown:
            raise EntityNotFoundException(f"Unknown savings goal ids: {unknown}")
        self.repo.set_priorities(ordered_ids)
        return self._after_write()

    def close(self, goal_id: int) -> list[dict[str, Any]]:
        """Close a goal by hand, freezing its allocation history.

        Parameters
        ----------
        goal_id : int
            Goal to close.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        """
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        today = date.today()
        self.repo.update(
            goal_id,
            status=GOAL_STATUS_CLOSED,
            closed_month=month_str((today.year, today.month)),
        )
        return self._after_write()

    def reopen(self, goal_id: int) -> list[dict[str, Any]]:
        """Reopen a closed goal so it absorbs surplus again.

        Parameters
        ----------
        goal_id : int
            Goal to reopen.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        """
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.repo.update(goal_id, status=GOAL_STATUS_ACTIVE, closed_month=None)
        return self._after_write()

    # ------------------------------------------------------------------
    # Transaction links
    # ------------------------------------------------------------------

    def link_transaction(
        self,
        goal_id: int,
        source_type: str,
        source_id: int,
        source_table: str,
        link_type: str,
    ) -> list[dict[str, Any]]:
        """Attach a transaction to a goal as a contribution or a utilization.

        Parameters
        ----------
        goal_id : int
            Goal the transaction belongs to.
        source_type : str
            ``"transaction"`` or ``"split"``.
        source_id : int
            ``unique_id`` of the transaction, or the split's id.
        source_table : str
            Table the transaction lives in (ignored for splits, whose ids are
            global).
        link_type : str
            ``LINK_CONTRIBUTION`` or ``LINK_UTILIZATION``.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        ValidationException
            If ``link_type`` is not one of the two accepted values.
        EntityNotFoundException
            If the goal does not exist.
        """
        if link_type not in (LINK_CONTRIBUTION, LINK_UTILIZATION):
            raise ValidationException(
                f"link_type must be '{LINK_CONTRIBUTION}' or '{LINK_UTILIZATION}'"
            )
        if not self.repo.get(goal_id):
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.repo.upsert_link(goal_id, source_type, source_id, source_table, link_type)
        # Links feed the context, so anything cached before this write is stale.
        self._context_cache = None
        return self._after_write()

    def unlink_transaction(self, link_id: int) -> list[dict[str, Any]]:
        """Detach a transaction from its goal.

        Parameters
        ----------
        link_id : int
            Link to remove.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the link does not exist.
        """
        try:
            self.repo.delete_link(link_id)
        except ValueError as exc:
            raise EntityNotFoundException(
                f"Savings goal link {link_id} not found"
            ) from exc
        self._context_cache = None
        return self._after_write()

    def get_links(self, goal_id: int | None = None) -> list[dict[str, Any]]:
        """Return transaction links, optionally scoped to one goal."""
        links = self.repo.get_links(goal_id)
        if links.empty:
            return []
        links = links.replace({np.nan: None})
        return links.to_dict("records")

    @staticmethod
    def _validate_month(value: object, field_name: str) -> None:
        """Reject a month string the engine could not parse."""
        if value is not None and month_key(value) is None:
            raise ValidationException(
                f"{field_name} must look like 'YYYY-MM', got {value!r}"
            )
