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
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.services.savings_goals.common import month_key, month_str

#: Fields that decide what the waterfall gave every goal in every month since
#: a goal started: changing one restates that history, not just the months to
#: come.
_ALLOCATION_FIELDS = (
    "contribution_category",
    "contribution_tags",
    "start_month",
    "target_amount",
    "monthly_cap",
    "opening_balance",
    "utilization_category",
    "utilization_tags",
)


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
            If ``start_month`` is not a parseable ``YYYY-MM`` string, or its
            saved-into rule claims income another goal already claims.
        """
        self._validate_income_claims(None, fields)
        fields.setdefault("priority", self.repo.next_priority())
        if not fields.get("start_month"):
            today = date.today()
            fields["start_month"] = month_str((today.year, today.month))
        self._validate_month(fields.get("start_month"), "start_month")
        goal = self.repo.add(**{k: v for k, v in fields.items() if v is not None})
        # It takes its waterfall turn from its start month, so every month
        # since then is restated with it in place.
        return self._restate_for_transfers(goal.start_month)

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
            If ``start_month`` is not a parseable ``YYYY-MM`` string, or its
            saved-into rule would claim income another goal already claims.
        """
        if "start_month" in fields:
            self._validate_month(fields["start_month"], "start_month")
        goal = self.repo.get(goal_id)
        if goal:
            self._validate_income_claims(goal, fields)
        # Every goal takes its turn in the waterfall, so a goal's start, target,
        # cap, opening balance or rules decide what it — and every goal below
        # it — got in each month since it started. A change restates that
        # history from the earlier of the old and new start month (moving the
        # start later must clear the months it no longer covers); left to the
        # months to come, an edit kept last year's allocations as they were.
        old_start = goal.start_month if goal else None
        changed = any(
            name in fields and fields[name] != getattr(goal, name, None)
            for name in _ALLOCATION_FIELDS
        )
        self.repo.update(goal_id, **fields)
        if changed:
            earliest = min(
                (m for m in (old_start, fields.get("start_month")) if m),
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
        start = goal.start_month if goal else None
        self.repo.delete(goal_id)
        # What it took in the waterfall goes back to the goals below it.
        if goal:
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
        self.repo.upsert_link(goal_id, source_type, source_id, source_table, link_type)
        # A link moves money in whatever month the transaction is in, and can
        # move a transaction off another goal: the whole history is restated.
        return self._restate_for_transfers(None)

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
        return self._restate_for_transfers(None)

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
        """
        goal = self.repo.get(goal_id)
        self.repo.set_utilization_rule(goal_id, category, self._join_tags(tags))
        # The rule claims spending in every month since the goal started.
        return self._restate_for_transfers(goal.start_month if goal else None)

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
        """Rebuild history after something that decides a goal's funding changed.

        Every goal takes its turn in the waterfall, and a saved-into rule
        decides what a goal borrowed before its income landed and handed back
        after — in every month they touch. So creating, editing or deleting a
        goal restates history from its start month rather than only the months
        still to come.
        """
        self._context_cache = None
        return self.rebuild(from_month=from_month)["goals"]

    def _validate_income_claims(
        self, goal: SavingsGoal | None, fields: dict[str, Any]
    ) -> None:
        """Refuse income two goals' saved-into rules would both claim.

        One transaction can only feed one goal, so the same income under two
        rules would be counted twice; the second claim is refused rather than
        resolved by a precedence nobody can see.

        Raises
        ------
        ValidationException
            When this goal's claim overlaps another goal's.
        """
        merged = {
            name: getattr(goal, name, None)
            for name in ("contribution_category", "contribution_tags")
        }
        merged.update({k: v for k, v in fields.items() if k in merged})
        claim = (merged["contribution_category"], merged["contribution_tags"])
        if not claim[0]:
            return
        for other in self._goals_in_order():
            if goal is not None and other.id == goal.id:
                continue
            other_claim = (other.contribution_category, other.contribution_tags)
            if self._claims_overlap(claim, other_claim):
                raise ValidationException(
                    f"That income already feeds the goal {other.name!r}"
                )

    def _claims_overlap(
        self, one: tuple[str | None, str | None], other: tuple[str | None, str | None]
    ) -> bool:
        """Whether two category/tag rules can match the same transaction."""
        if not one[0] or one[0] != other[0]:
            return False
        tags, other_tags = self._split_tags(one[1]), self._split_tags(other[1])
        if not tags or not other_tags or ALL_TAGS in tags or ALL_TAGS in other_tags:
            return True
        return bool(set(tags) & set(other_tags))

    @staticmethod
    def _validate_month(value: object, field_name: str) -> None:
        """Reject a month string the engine could not parse."""
        if value is not None and month_key(value) is None:
            raise ValidationException(
                f"{field_name} must look like 'YYYY-MM', got {value!r}"
            )
