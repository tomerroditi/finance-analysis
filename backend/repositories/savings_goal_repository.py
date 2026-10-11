"""Data access for savings goals: goals, entries, transaction links and yearly targets."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.savings_goal import (
    SavingsGoal,
    SavingsGoalEntry,
    SavingsGoalLink,
    YearlySavingsTarget,
)
from backend.repositories._sql import orm_rows_to_frame

GOAL_COLUMNS = [
    "id",
    "name",
    "target_amount",
    "priority",
    "monthly_amount",
    "start_month",
    "target_date",
    "contribution_category",
    "contribution_tags",
    "utilization_category",
    "utilization_tags",
    "status",
    "closed_month",
    "notes",
]

ENTRY_COLUMNS = ["id", "goal_id", "date", "amount", "source", "note"]

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

        Each write normally commits on its own. Funding every goal, or
        covering a shortfall out of several, is one entry per goal — committed
        one by one, a failure halfway would leave half the plan applied.
        Inside this block writes only flush, and the block commits once at the
        end. Any error rolls the whole block back. Blocks nest; only the
        outermost one commits, and a block that wrote nothing does not commit
        at all (every commit discards the cross-request caches,
        ``backend/utils/data_cache.py``).

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
        """Delete a goal with its entries and transaction links.

        Raises
        ------
        EntityNotFoundException
            If no goal with ``goal_id`` exists.
        """
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise EntityNotFoundException(f"Savings goal {goal_id} not found")
        self.db.query(SavingsGoalEntry).filter(
            SavingsGoalEntry.goal_id == goal_id
        ).delete()
        self.db.query(SavingsGoalLink).filter(
            SavingsGoalLink.goal_id == goal_id
        ).delete()
        self.db.delete(goal)
        self._commit()

    def set_priorities(self, ordered_ids: list[int]) -> None:
        """Rewrite the list order from a list of goal ids, first one first."""
        goals = {g.id: g for g in self.db.execute(select(SavingsGoal)).scalars().all()}
        for position, goal_id in enumerate(ordered_ids):
            goal = goals.get(goal_id)
            if goal:
                goal.priority = position
        self._commit()

    def get_entries(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return entries, optionally scoped to one goal, oldest first."""
        stmt = select(SavingsGoalEntry).order_by(
            SavingsGoalEntry.date, SavingsGoalEntry.id
        )
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalEntry.goal_id == goal_id)
        return orm_rows_to_frame(self.db.execute(stmt).scalars().all(), ENTRY_COLUMNS)

    def get_entry(self, entry_id: int) -> SavingsGoalEntry | None:
        """Return a single entry by id, or None."""
        return self.db.get(SavingsGoalEntry, entry_id)

    def add_entry(
        self,
        goal_id: int,
        entry_date: str,
        amount: float,
        source: str,
        note: str | None = None,
    ) -> SavingsGoalEntry:
        """Record money put into (positive) or taken out of (negative) a goal."""
        entry = SavingsGoalEntry(
            goal_id=goal_id, date=entry_date, amount=amount, source=source, note=note
        )
        self.db.add(entry)
        self._commit()
        return entry

    def delete_entry(self, entry_id: int) -> None:
        """Delete one entry.

        Raises
        ------
        EntityNotFoundException
            If no entry with ``entry_id`` exists.
        """
        entry = self.db.get(SavingsGoalEntry, entry_id)
        if not entry:
            raise EntityNotFoundException(f"Savings goal entry {entry_id} not found")
        self.db.delete(entry)
        self._commit()

    def delete_entries(self, goal_id: int, source: str) -> None:
        """Delete every entry of one ``source`` on a goal."""
        self.db.query(SavingsGoalEntry).filter(
            SavingsGoalEntry.goal_id == goal_id, SavingsGoalEntry.source == source
        ).delete()
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

    def delete_links_for_goal(self, goal_id: int) -> None:
        """Delete every transaction link a goal has."""
        self.db.query(SavingsGoalLink).filter(
            SavingsGoalLink.goal_id == goal_id
        ).delete()
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

    def get_yearly_targets(self) -> dict[int, float]:
        """Return every year's savings target as ``{year: target_amount}``."""
        rows = self.db.execute(select(YearlySavingsTarget)).scalars().all()
        return {int(row.year): float(row.target_amount) for row in rows}

    def set_yearly_target(self, year: int, target_amount: float | None) -> None:
        """Set a year's savings target; ``None`` clears it."""
        row = self.db.get(YearlySavingsTarget, year)
        if target_amount is None:
            if row is not None:
                self.db.delete(row)
        elif row is None:
            self.db.add(YearlySavingsTarget(year=year, target_amount=target_amount))
        else:
            row.target_amount = target_amount
        self._commit()
