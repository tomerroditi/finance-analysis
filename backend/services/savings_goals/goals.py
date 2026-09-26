"""Goal CRUD and transaction links for the savings-goal service.

Provides ``GoalCrudMixin``: create/update/delete/reorder/close/reopen a goal,
and attach or detach transactions as contributions or utilizations. Every
write refreshes the allocation ledger before returning the goals. Mixed into
``SavingsGoalService`` (see ``core.py``).
"""

from datetime import date
from typing import Any

import numpy as np

from backend.constants.budget import ALL_TAGS
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    GOAL_KIND_INVESTMENT,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.services.savings_goals.common import (
    is_investment_goal,
    month_key,
    month_str,
)

#: What an investment goal cannot carry: it is filled by transfers alone, so
#: surplus caps, an opening earmark of cash and paying for spending out of it
#: have nothing to act on.
_CASH_ONLY_FIELDS = ("monthly_cap", "utilization_category", "utilization_tags")

#: The fields that decide which transfers an investment goal owns.
_TRANSFER_SCOPE_FIELDS = ("contribution_category", "contribution_tags", "start_month")


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
            If ``start_month`` is not a parseable ``YYYY-MM`` string, or an
            investment goal names no transfers or carries a cash-only field.
        """
        if fields.get("kind") == GOAL_KIND_INVESTMENT:
            self._validate_investment_fields(fields)
        fields.setdefault("priority", self.repo.next_priority())
        if not fields.get("start_month"):
            today = date.today()
            fields["start_month"] = month_str((today.year, today.month))
        self._validate_month(fields.get("start_month"), "start_month")
        goal = self.repo.add(**{k: v for k, v in fields.items() if v is not None})
        if self._owns_transfers(goal):
            return self._restate_for_transfers(goal.start_month)
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
            If ``start_month`` is not a parseable ``YYYY-MM`` string, or the
            change would leave an investment goal without transfers or with a
            cash-only field.
        """
        if "start_month" in fields:
            self._validate_month(fields["start_month"], "start_month")
        goal = self.repo.get(goal_id)
        if goal and is_investment_goal(goal):
            current = {
                "contribution_category": goal.contribution_category,
                "opening_balance": goal.opening_balance,
            }
            self._validate_investment_fields({**current, **fields})
        # Adding, dropping or narrowing a goal's own income rule decides, in
        # every month since it started, what it borrowed and handed back — so
        # it restates that history rather than only the months to come.
        was_owner = bool(goal and self._owns_transfers(goal))
        rescoped = any(
            name in fields and fields[name] != getattr(goal, name, None)
            for name in _TRANSFER_SCOPE_FIELDS
        )
        self.repo.update(goal_id, **fields)
        goal = self.repo.get(goal_id)
        if rescoped and (was_owner or self._owns_transfers(goal)):
            earliest = min(
                (m for m in (goal.start_month, fields.get("start_month")) if m),
                default=None,
            )
            return self._restate_for_transfers(earliest)
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
        goal = self.repo.get(goal_id)
        start = goal.start_month if goal and self._owns_transfers(goal) else None
        self.repo.delete(goal_id)
        if start:
            self._restate_for_transfers(start)

    def reorder(self, ordered_ids: list[int]) -> list[dict[str, Any]]:
        """Set the waterfall order and restate history under it.

        The first id is funded first. The whole ledger is rebuilt in the same
        call: an order that only applied forward left every past month
        allocated under the old one, so the list and its numbers disagreed
        until the user found a separate "redistribute" action. Closed goals
        keep their frozen allocations, as they do in any rebuild.

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
        return self.rebuild(order=ordered_ids)["goals"]

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
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self._reject_investment_goal(goal, "take single transactions")
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
        self.repo.delete_link(link_id)
        self._context_cache = None
        return self._after_write()

    def set_spending_link(
        self, goal_id: int, category: str | None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Pay for a category (optionally narrowed to tags) out of a goal.

        Every transaction matching the rule, from the goal's start month on,
        is spent out of the goal as a utilization — the ones already on record
        and every one that lands later — so a project budget (its category) or
        a yearly envelope (its category and tags) is linked once instead of
        one purchase at a time. An explicit link on a single transaction still
        wins over it.

        Parameters
        ----------
        goal_id : int
            Goal that pays for the spending.
        category : str or None
            Category to match, or ``None`` to clear the goal's rule.
        tags : list[str] or None, optional
            Tags narrowing ``category``. Empty, ``None`` or ``["all_tags"]``
            covers every tag.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        ValidationException
            If the goal is an investment goal, which nothing is spent out of.
        """
        goal = self.repo.get(goal_id)
        if goal and category is not None:
            self._reject_investment_goal(goal, "pay for spending")
        self.repo.set_utilization_rule(goal_id, category, self._join_tags(tags))
        self._context_cache = None
        return self._after_write()

    @staticmethod
    def _join_tags(tags: list[str] | None) -> str | None:
        """Store a tag list the way budget rules do; ``None`` means every tag."""
        cleaned = sorted({t.strip() for t in tags or [] if t and t.strip()})
        if not cleaned or ALL_TAGS in cleaned:
            return None
        return ";".join(cleaned)

    def get_links(self, goal_id: int | None = None) -> list[dict[str, Any]]:
        """Return transaction links, optionally scoped to one goal."""
        links = self.repo.get_links(goal_id)
        if links.empty:
            return []
        links = links.replace({np.nan: None})
        return links.to_dict("records")

    def _restate_for_transfers(self, from_month: str | None) -> list[dict[str, Any]]:
        """Rebuild history after the income a goal owns changed.

        Which transfers an investment goal owns decides whether each one is
        progress or a deficit that claws back the cash goals, and a saved-into
        rule decides what a goal borrowed before its income landed and handed
        back after — in every month they touch. So creating, rescoping or
        deleting either restates history from the goal's start month rather
        than only the months still to come. Without this, a goal created today
        over last year's transfers would keep every clawback they once caused.
        """
        self._context_cache = None
        return self.rebuild(from_month=from_month)["goals"]

    @staticmethod
    def _owns_transfers(goal: SavingsGoal) -> bool:
        """Whether the goal has income of its own: an investment or a saved-into rule."""
        return is_investment_goal(goal) or bool(goal.contribution_category)

    @staticmethod
    def _validate_investment_fields(fields: dict[str, Any]) -> None:
        """Reject an investment goal that names no transfers or holds cash fields.

        Raises
        ------
        ValidationException
            When ``contribution_category`` is empty, ``opening_balance`` is
            non-zero, or any cash-only field is set.
        """
        if not fields.get("contribution_category"):
            raise ValidationException(
                "An investment goal needs the category its transfers are tagged with"
            )
        if fields.get("opening_balance"):
            raise ValidationException(
                "An investment goal counts transfers only; it takes no opening balance"
            )
        set_fields = [name for name in _CASH_ONLY_FIELDS if fields.get(name)]
        if set_fields:
            raise ValidationException(
                f"An investment goal cannot set {', '.join(set_fields)}"
            )

    @staticmethod
    def _reject_investment_goal(goal: SavingsGoal, action: str) -> None:
        """Refuse an action that only applies to a cash goal.

        Raises
        ------
        ValidationException
            When ``goal`` is an investment goal.
        """
        if is_investment_goal(goal):
            raise ValidationException(f"An investment goal cannot {action}")

    @staticmethod
    def _validate_month(value: object, field_name: str) -> None:
        """Reject a month string the engine could not parse."""
        if value is not None and month_key(value) is None:
            raise ValidationException(
                f"{field_name} must look like 'YYYY-MM', got {value!r}"
            )
