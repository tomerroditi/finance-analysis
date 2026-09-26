"""Data access for savings goals: goals, allocations and transaction links."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd
from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.savings_goal import (
    GOAL_STATUS_ACTIVE,
    SavingsGoal,
    SavingsGoalAllocation,
    SavingsGoalLink,
)
from backend.repositories._sql import orm_rows_to_frame

GOAL_COLUMNS = [
    "id",
    "name",
    "target_amount",
    "opening_balance",
    "priority",
    "monthly_cap",
    "start_month",
    "target_date",
    "contribution_category",
    "contribution_tags",
    "kind",
    "status",
    "closed_month",
    "notes",
]

ALLOCATION_COLUMNS = ["id", "goal_id", "year", "month", "amount", "source"]

LINK_COLUMNS = [
    "id",
    "goal_id",
    "source_type",
    "source_id",
    "source_table",
    "link_type",
]


class SavingsGoalRepository:
    """Repository for ``savings_goals`` CRUD operations."""

    def __init__(self, db: Session) -> None:
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self._atomic_depth = 0
        self._atomic_wrote = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """Group every write inside the block into one transaction.

        Each write normally commits on its own. A rebuild is many of them — the
        new priorities, deleting the history it restates, then one upsert per
        (goal, month) — and committed one by one, a request running alongside
        (another tab's reorder, a dashboard read topping up missing months)
        could see the history deleted but not yet rewritten and fill it in
        under the old order. Inside this block writes only flush, and the
        block commits once at the end, so everyone else sees the old ledger or
        the new one and never half of each. Any error rolls the whole block
        back. Blocks nest; only the outermost one commits.

        A block that wrote nothing does not commit at all. Every commit
        discards the cross-request caches (``backend/utils/data_cache.py``),
        and ``ensure_allocations`` opens a block on every read — most of which
        find the ledger already current.

        Yields
        ------
        None
        """
        if self._atomic_depth == 0:
            self._atomic_wrote = False
        self._atomic_depth += 1
        try:
            yield
        except BaseException:
            self._atomic_depth -= 1
            if self._atomic_depth == 0 and self._atomic_wrote:
                self.db.rollback()
            raise
        self._atomic_depth -= 1
        if self._atomic_depth == 0 and self._atomic_wrote:
            self.db.commit()

    def _commit(self) -> None:
        """Commit now, or only flush while an :meth:`atomic` block is open."""
        if self._atomic_depth:
            self._atomic_wrote = True
            self.db.flush()
        else:
            self.db.commit()

    def get_all(self) -> pd.DataFrame:
        """Return all savings goals as a DataFrame (empty with no rows)."""
        records = self.db.execute(select(SavingsGoal)).scalars().all()
        return orm_rows_to_frame(records, GOAL_COLUMNS)

    def get(self, goal_id: int) -> SavingsGoal | None:
        """Return a single goal by id, or None."""
        return self.db.get(SavingsGoal, goal_id)

    def next_priority(self) -> int:
        """Return the priority a newly created goal should take (last place)."""
        priorities = self.db.execute(select(SavingsGoal.priority)).scalars().all()
        return max(priorities) + 1 if priorities else 0

    def add(self, **fields: Any) -> SavingsGoal:
        """Insert a new goal and return the persisted row."""
        goal = SavingsGoal(**fields)
        self.db.add(goal)
        self._commit()
        self.db.refresh(goal)
        return goal

    def update(self, goal_id: int, **fields: Any) -> SavingsGoal:
        """Update an existing goal and return it.

        ``None`` values are applied rather than skipped, so a caller can clear
        an optional field (a target date, a monthly cap). Callers that only
        want to touch supplied fields should pass ``exclude_unset`` data.

        Raises
        ------
        EntityNotFoundException
            If no goal with ``goal_id`` exists.
        """
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        for key, value in fields.items():
            setattr(goal, key, value)
        self._commit()
        self.db.refresh(goal)
        return goal

    def delete(self, goal_id: int) -> None:
        """Delete a goal with its allocations and transaction links.

        Raises
        ------
        EntityNotFoundException
            If no goal with ``goal_id`` exists.
        """
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.db.query(SavingsGoalAllocation).filter(
            SavingsGoalAllocation.goal_id == goal_id
        ).delete()
        self.db.query(SavingsGoalLink).filter(
            SavingsGoalLink.goal_id == goal_id
        ).delete()
        self.db.delete(goal)
        self._commit()

    def set_priorities(self, ordered_ids: list[int]) -> None:
        """Rewrite the waterfall order from a list of goal ids, first funded first."""
        goals = {g.id: g for g in self.db.execute(select(SavingsGoal)).scalars().all()}
        for position, goal_id in enumerate(ordered_ids):
            goal = goals.get(goal_id)
            if goal:
                goal.priority = position
        self._commit()

    def get_allocations(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return allocation rows, optionally scoped to a single goal."""
        stmt = select(SavingsGoalAllocation)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalAllocation.goal_id == goal_id)
        return orm_rows_to_frame(
            self.db.execute(stmt).scalars().all(), ALLOCATION_COLUMNS
        )

    def get_month_allocations(self, year: int, month: int) -> pd.DataFrame:
        """Return every goal's allocation for one calendar month."""
        stmt = select(SavingsGoalAllocation).where(
            SavingsGoalAllocation.year == year, SavingsGoalAllocation.month == month
        )
        return orm_rows_to_frame(
            self.db.execute(stmt).scalars().all(), ALLOCATION_COLUMNS
        )

    def upsert_allocation(
        self, goal_id: int, year: int, month: int, amount: float, source: str
    ) -> SavingsGoalAllocation:
        """Insert or update the single allocation row for a (goal, month).

        A single ``INSERT ... ON CONFLICT DO UPDATE`` rather than
        select-then-insert: the allocation engine runs from read paths
        (``ensure_allocations`` on every budget-month GET), so two parallel
        requests against a fresh database used to race between the SELECT
        and the INSERT and one of them died on the unique constraint.
        """
        stmt = sqlite_insert(SavingsGoalAllocation).values(
            goal_id=goal_id, year=year, month=month, amount=amount, source=source
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["goal_id", "year", "month"],
            set_={
                "amount": stmt.excluded.amount,
                "source": stmt.excluded.source,
                "updated_at": func.now(),
            },
        )
        self.db.execute(stmt)
        self._commit()
        self.db.expire_all()
        return self.db.execute(
            select(SavingsGoalAllocation).where(
                SavingsGoalAllocation.goal_id == goal_id,
                SavingsGoalAllocation.year == year,
                SavingsGoalAllocation.month == month,
            )
        ).scalar_one()

    def delete_allocations(
        self, goal_ids: list[int], from_year: int, from_month: int
    ) -> None:
        """Delete allocations for the given goals at or after a month.

        Used by a rebuild to clear the range it is about to recompute. Goals
        whose history must stay frozen are simply left out of ``goal_ids``.
        """
        if not goal_ids:
            return
        rows = (
            self.db.query(SavingsGoalAllocation)
            .filter(SavingsGoalAllocation.goal_id.in_(goal_ids))
            .all()
        )
        for row in rows:
            if (row.year, row.month) >= (from_year, from_month):
                self.db.delete(row)
        self._commit()

    def get_links(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return transaction links, optionally scoped to a single goal."""
        stmt = select(SavingsGoalLink)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalLink.goal_id == goal_id)
        return orm_rows_to_frame(self.db.execute(stmt).scalars().all(), LINK_COLUMNS)

    def get_link_by_source(
        self, source_type: str, source_id: int, source_table: str
    ) -> SavingsGoalLink | None:
        """Return the link attached to one transaction, or None."""
        return self.db.execute(
            select(SavingsGoalLink).where(
                SavingsGoalLink.source_type == source_type,
                SavingsGoalLink.source_id == source_id,
                SavingsGoalLink.source_table == source_table,
            )
        ).scalar_one_or_none()

    def upsert_link(
        self,
        goal_id: int,
        source_type: str,
        source_id: int,
        source_table: str,
        link_type: str,
    ) -> SavingsGoalLink:
        """Attach a transaction to a goal, replacing any existing attachment.

        A transaction belongs to at most one goal in one role, so re-linking an
        already-linked transaction moves it rather than raising.
        """
        link = self.get_link_by_source(source_type, source_id, source_table)
        if link is None:
            link = SavingsGoalLink(
                goal_id=goal_id,
                source_type=source_type,
                source_id=source_id,
                source_table=source_table,
                link_type=link_type,
            )
            self.db.add(link)
        else:
            link.goal_id = goal_id
            link.link_type = link_type
        self._commit()
        self.db.refresh(link)
        return link

    def delete_link(self, link_id: int) -> None:
        """Delete a transaction link by id; raise ``EntityNotFoundException`` if missing."""
        link = self.db.get(SavingsGoalLink, link_id)
        if not link:
            raise EntityNotFoundException(f"Savings goal link {link_id} not found")
        self.db.delete(link)
        self._commit()

    def set_utilization_rule(
        self, goal_id: int, category: str | None, tags: str | None
    ) -> None:
        """Make ``goal_id`` the goal that pays for ``(category, tags)``.

        Any other goal holding the very same rule lets go of it in the same
        commit: the user just moved that spending to this goal, and two goals
        claiming it would leave the choice to waterfall order instead.

        Parameters
        ----------
        goal_id : int
            Goal that pays for the spending.
        category : str or None
            Category the rule matches; ``None`` clears the goal's rule.
        tags : str or None
            Semicolon-separated tags narrowing ``category``; ``None`` covers
            every tag.

        Raises
        ------
        EntityNotFoundException
            If no goal with ``goal_id`` exists.
        """
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        if category is not None:
            self.db.execute(
                update(SavingsGoal)
                .where(SavingsGoal.utilization_category == category)
                .where(
                    SavingsGoal.utilization_tags.is_(None)
                    if tags is None
                    else SavingsGoal.utilization_tags == tags
                )
                .where(SavingsGoal.id != goal_id)
                .values(utilization_category=None, utilization_tags=None)
            )
        goal.utilization_category = category
        goal.utilization_tags = tags if category is not None else None
        self._commit()

    def active_goals(self) -> list[SavingsGoal]:
        """Return active goals in waterfall order (priority ascending)."""
        return list(
            self.db.execute(
                select(SavingsGoal)
                .where(SavingsGoal.status == GOAL_STATUS_ACTIVE)
                .order_by(SavingsGoal.priority, SavingsGoal.id)
            )
            .scalars()
            .all()
        )
