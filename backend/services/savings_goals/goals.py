"""Goal CRUD, money in and out, and transaction links for the savings-goal service.

Provides ``GoalCrudMixin``: create/update/delete/reorder/close/reopen a goal,
put money into a goal or take it out, fund the month's suggestions, cover a
free-cash shortfall, and attach or detach transactions as income or spending.
Nothing here moves money the user did not ask to move. Mixed into
``SavingsGoalService`` (see ``core.py``).
"""

from datetime import date
from typing import Any

import numpy as np

from backend.constants.budget import ALL_TAGS
from backend.errors import EntityNotFoundException, ValidationException
from backend.models.savings_goal import (
    ENTRY_CLOSE,
    ENTRY_COVER,
    ENTRY_MANUAL,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.repositories.split_transactions_repository import (
    SplitTransactionsRepository,
)
from backend.services.savings_goals.common import ROUNDING_EPSILON, month_key, month_str


class GoalCrudMixin:
    """Goal lifecycle, money movement and link methods for ``SavingsGoalService``."""

    def create(
        self, initial_amount: float = 0.0, **fields: Any
    ) -> list[dict[str, Any]]:
        """Create a new savings goal at the bottom of the list.

        Parameters
        ----------
        initial_amount : float, optional
            Money to put into the goal straight away, recorded as its first
            entry.
        **fields : Any
            Goal columns. ``priority`` defaults to the bottom of the list and
            ``start_month`` to the current month; ``None`` values are dropped.

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
        with self.repo.atomic():
            goal = self.repo.add(**{k: v for k, v in fields.items() if v is not None})
            if initial_amount and initial_amount > 0:
                self.repo.add_entry(
                    goal.id,
                    date.today().isoformat(),
                    float(initial_amount),
                    ENTRY_MANUAL,
                )
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
            If ``start_month`` is not a parseable ``YYYY-MM`` string, or its
            saved-into rule would claim income another goal already claims.
        """
        if "start_month" in fields:
            self._validate_month(fields["start_month"], "start_month")
        goal = self._require(goal_id)
        self._validate_income_claims(goal, fields)
        self.repo.update(goal_id, **fields)
        return self._after_write()

    def delete(self, goal_id: int) -> None:
        """Delete a savings goal with its entries and links.

        What it held goes back to free cash.

        Parameters
        ----------
        goal_id : int
            Goal to delete.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        """
        self.repo.delete(goal_id)
        self._invalidate()

    def reorder(self, ordered_ids: list[int]) -> list[dict[str, Any]]:
        """Set the list order, first id first.

        Order decides nothing about the past: it is the order "fund all"
        funds in and the reverse of the order a cover plan takes money back.

        Parameters
        ----------
        ordered_ids : list[int]
            Goal ids, top of the list first.

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
        """Close a goal, handing what it still holds back to free cash.

        The hand-back is a ``close`` entry, so reopening the goal restores
        exactly that money.

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
        goal = self._require(goal_id)
        today = date.today()
        held = self._state_of(goal).available
        with self.repo.atomic():
            if held > ROUNDING_EPSILON:
                self.repo.add_entry(goal_id, today.isoformat(), -held, ENTRY_CLOSE)
            self.repo.update(
                goal_id,
                status=GOAL_STATUS_CLOSED,
                closed_month=month_str((today.year, today.month)),
            )
        return self._after_write()

    def reopen(self, goal_id: int) -> list[dict[str, Any]]:
        """Reopen a closed goal, giving back what closing it handed to free cash.

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
        self._require(goal_id)
        with self.repo.atomic():
            self.repo.delete_entries(goal_id, ENTRY_CLOSE)
            self.repo.update(goal_id, status=GOAL_STATUS_ACTIVE, closed_month=None)
        return self._after_write()

    # ------------------------------------------------------------------
    # Money in and out
    # ------------------------------------------------------------------

    def add_entry(
        self,
        goal_id: int,
        amount: float,
        entry_date: str | None = None,
        note: str | None = None,
    ) -> list[dict[str, Any]]:
        """Put money into a goal (positive) or take it out (negative).

        Parameters
        ----------
        goal_id : int
            Goal the money moves into or out of.
        amount : float
            Signed amount; never zero.
        entry_date : str or None, optional
            ``YYYY-MM-DD``; defaults to today.
        note : str or None, optional
            Free text kept with the entry.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the goal does not exist.
        ValidationException
            If the amount is zero, the date is not a date, the goal is
            closed, or more is taken out than the goal holds.
        """
        goal = self._require(goal_id)
        if abs(amount) < ROUNDING_EPSILON:
            raise ValidationException("Enter an amount to add or take out")
        if goal.status == GOAL_STATUS_CLOSED:
            raise ValidationException("Reopen the goal to move money into or out of it")
        when = self._validate_date(entry_date)
        if amount < 0:
            held = self._state_of(goal).available
            if -amount > held + ROUNDING_EPSILON:
                raise ValidationException(
                    f"{goal.name!r} holds {held:,.2f}; you cannot take out more"
                )
        self.repo.add_entry(goal_id, when, float(amount), ENTRY_MANUAL, note)
        return self._after_write()

    def delete_entry(self, entry_id: int) -> list[dict[str, Any]]:
        """Undo one entry.

        Parameters
        ----------
        entry_id : int
            Entry to delete.

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        EntityNotFoundException
            If the entry does not exist.
        """
        self.repo.delete_entry(entry_id)
        return self._after_write()

    def fund(self, goal_ids: list[int] | None = None) -> list[dict[str, Any]]:
        """Put this month's suggested amount into goals, top of the list first.

        Never spends more than free cash holds: once it runs out, the goals
        below get nothing rather than driving free cash negative.

        Parameters
        ----------
        goal_ids : list[int] or None, optional
            Goals to fund; ``None`` funds every goal with a suggestion.

        Returns
        -------
        list[dict]
            Every goal, refreshed.
        """
        wanted = set(goal_ids) if goal_ids is not None else None
        free_cash = self._free_cash_now()
        today = date.today().isoformat()
        with self.repo.atomic():
            for goal in self._goals_in_order():
                if wanted is not None and goal.id not in wanted:
                    continue
                amount = min(self._suggestion(goal), max(0.0, free_cash))
                if amount <= ROUNDING_EPSILON:
                    continue
                self.repo.add_entry(goal.id, today, round(amount, 2), ENTRY_MANUAL)
                free_cash -= amount
        return self._after_write()

    def cover_plan(self) -> list[dict[str, Any]]:
        """Return what covering a free-cash shortfall would take from each goal.

        Lowest in the list gives first, and no goal gives more than it holds.

        Returns
        -------
        list[dict]
            ``{"goal_id", "name", "amount"}`` per goal giving money back;
            empty when free cash is not negative.
        """
        shortfall = -self._free_cash_now()
        plan: list[dict[str, Any]] = []
        for goal in reversed(self._goals_in_order()):
            if shortfall <= ROUNDING_EPSILON:
                break
            if goal.status == GOAL_STATUS_CLOSED:
                continue
            take = min(shortfall, self._state_of(goal).available)
            if take <= ROUNDING_EPSILON:
                continue
            plan.append(
                {"goal_id": goal.id, "name": goal.name, "amount": round(take, 2)}
            )
            shortfall -= take
        return plan

    def cover(self) -> list[dict[str, Any]]:
        """Apply :meth:`cover_plan`: take the shortfall back from the goals.

        Returns
        -------
        list[dict]
            Every goal, refreshed.
        """
        today = date.today().isoformat()
        with self.repo.atomic():
            for step in self.cover_plan():
                self.repo.add_entry(
                    step["goal_id"], today, -step["amount"], ENTRY_COVER
                )
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
        """Attach a transaction to a goal as income or as spending.

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
            ``LINK_CONTRIBUTION`` (income) or ``LINK_UTILIZATION`` (spending).

        Returns
        -------
        list[dict]
            Every goal, refreshed.

        Raises
        ------
        ValidationException
            If ``link_type`` is not one of the two accepted values, or a
            contribution is not money coming in.
        EntityNotFoundException
            If the goal does not exist.
        """
        if link_type not in (LINK_CONTRIBUTION, LINK_UTILIZATION):
            raise ValidationException(
                f"link_type must be '{LINK_CONTRIBUTION}' or '{LINK_UTILIZATION}'"
            )
        self._require(goal_id)
        if (
            link_type == LINK_CONTRIBUTION
            and self._link_amount(source_type, source_id, source_table) <= 0
        ):
            raise ValidationException(
                "Only money coming in can be saved into a goal. To set money "
                "aside, add it to the goal instead."
            )
        self.repo.upsert_link(goal_id, source_type, source_id, source_table, link_type)
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
        return self._after_write()

    def set_spending_link(
        self, goal_id: int, category: str | None, tags: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Pay for a category (optionally narrowed to tags) out of a goal.

        Every transaction matching the rule, from the goal's start month on,
        is spent out of the goal — the ones already on record and every one
        that lands later — so a project budget (its category) or a yearly
        envelope (its category and tags) is linked once instead of one
        purchase at a time. An explicit link on a single transaction still
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
        self.repo.set_utilization_rule(goal_id, category, self._join_tags(tags))
        return self._after_write()

    def get_links(self, goal_id: int | None = None) -> list[dict[str, Any]]:
        """Return transaction links, optionally scoped to one goal."""
        links = self.repo.get_links(goal_id)
        if links.empty:
            return []
        links = links.replace({np.nan: None})
        return links.to_dict("records")

    def _link_amount(
        self, source_type: str, source_id: int, source_table: str
    ) -> float:
        """Return the amount of the transaction or split a link points at.

        Raises
        ------
        EntityNotFoundException
            If nothing matches.
        """
        if source_type == "split":
            split = SplitTransactionsRepository(self.db).get_split(source_id)
            if split is None:
                raise EntityNotFoundException(f"Split {source_id} not found")
            return float(split.amount)
        row = self.transactions_service.get_transaction(source_id, source_table)
        return float(row["amount"])

    @staticmethod
    def _join_tags(tags: list[str] | None) -> str | None:
        """Store a tag list the way budget rules do; ``None`` means every tag."""
        cleaned = sorted({t.strip() for t in tags or [] if t and t.strip()})
        if not cleaned or ALL_TAGS in cleaned:
            return None
        return ";".join(cleaned)

    def _after_write(self) -> list[dict[str, Any]]:
        """Return every goal, recomputed after a write."""
        self._invalidate()
        return self.get_all()

    def _require(self, goal_id: int) -> SavingsGoal:
        """Return a goal or raise ``EntityNotFoundException``."""
        goal = self.repo.get(goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        return goal

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
        """Reject a month string that does not parse."""
        if value is not None and month_key(value) is None:
            raise ValidationException(
                f"{field_name} must look like 'YYYY-MM', got {value!r}"
            )

    @staticmethod
    def _validate_date(value: str | None) -> str:
        """Return ``value`` as ``YYYY-MM-DD`` (today when ``None``), or raise."""
        if value is None:
            return date.today().isoformat()
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except ValueError:
            raise ValidationException(
                f"date must look like 'YYYY-MM-DD', got {value!r}"
            ) from None
