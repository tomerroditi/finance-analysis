"""Data access for savings goals: allocations, transaction links, investment earmarks."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.savings_goal import (
    GOAL_STATUS_ACTIVE,
    SavingsGoal,
    SavingsGoalAllocation,
    SavingsGoalInvestment,
    SavingsGoalLink,
)

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
    "status",
    "closed_month",
    "notes",
]

ALLOCATION_COLUMNS = ["id", "goal_id", "year", "month", "amount", "source"]

LINK_COLUMNS = ["id", "goal_id", "source_type", "source_id", "source_table", "link_type"]

BACKING_COLUMNS = ["id", "goal_id", "investment_id", "amount"]


def _to_frame(records: list, columns: list[str]) -> pd.DataFrame:
    """Build a DataFrame from ORM rows, preserving column order when empty."""
    if not records:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame([r.__dict__ for r in records])
    return df.drop(columns=["_sa_instance_state"], errors="ignore")


class SavingsGoalRepository:
    """Repository for ``savings_goals`` CRUD operations."""

    def __init__(self, db: Session):
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Return all savings goals as a DataFrame (empty with no rows)."""
        records = self.db.execute(select(SavingsGoal)).scalars().all()
        return _to_frame(records, GOAL_COLUMNS)

    def get(self, goal_id: int) -> SavingsGoal | None:
        """Return a single goal by id, or None."""
        return self.db.get(SavingsGoal, goal_id)

    def next_priority(self) -> int:
        """Return the priority a newly created goal should take (last place)."""
        priorities = self.db.execute(select(SavingsGoal.priority)).scalars().all()
        return max(priorities) + 1 if priorities else 0

    def add(self, **fields) -> SavingsGoal:
        """Insert a new goal and return the persisted row."""
        goal = SavingsGoal(**fields)
        self.db.add(goal)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def update(self, goal_id: int, **fields) -> SavingsGoal:
        """Update an existing goal and return it.

        ``None`` values are applied rather than skipped, so a caller can clear
        an optional field (a target date, a monthly cap). Callers that only
        want to touch supplied fields should pass ``exclude_unset`` data.
        """
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise ValueError(f"No savings goal with id {goal_id}")
        for key, value in fields.items():
            setattr(goal, key, value)
        self.db.commit()
        self.db.refresh(goal)
        return goal

    def delete(self, goal_id: int) -> None:
        """Delete a goal along with its allocations and transaction links."""
        goal = self.db.get(SavingsGoal, goal_id)
        if not goal:
            raise ValueError(f"No savings goal with id {goal_id}")
        self.db.query(SavingsGoalAllocation).filter(
            SavingsGoalAllocation.goal_id == goal_id
        ).delete()
        self.db.query(SavingsGoalLink).filter(
            SavingsGoalLink.goal_id == goal_id
        ).delete()
        self.db.delete(goal)
        self.db.commit()

    def set_priorities(self, ordered_ids: list[int]) -> None:
        """Rewrite the waterfall order from a list of goal ids, first funded first."""
        goals = {g.id: g for g in self.db.execute(select(SavingsGoal)).scalars().all()}
        for position, goal_id in enumerate(ordered_ids):
            goal = goals.get(goal_id)
            if goal:
                goal.priority = position
        self.db.commit()

    # ------------------------------------------------------------------
    # Allocations
    # ------------------------------------------------------------------

    def get_allocations(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return allocation rows, optionally scoped to a single goal."""
        stmt = select(SavingsGoalAllocation)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalAllocation.goal_id == goal_id)
        return _to_frame(self.db.execute(stmt).scalars().all(), ALLOCATION_COLUMNS)

    def get_month_allocations(self, year: int, month: int) -> pd.DataFrame:
        """Return every goal's allocation for one calendar month."""
        stmt = select(SavingsGoalAllocation).where(
            SavingsGoalAllocation.year == year, SavingsGoalAllocation.month == month
        )
        return _to_frame(self.db.execute(stmt).scalars().all(), ALLOCATION_COLUMNS)

    def upsert_allocation(
        self, goal_id: int, year: int, month: int, amount: float, source: str
    ) -> SavingsGoalAllocation:
        """Insert or update the single allocation row for a (goal, month)."""
        row = self.db.execute(
            select(SavingsGoalAllocation).where(
                SavingsGoalAllocation.goal_id == goal_id,
                SavingsGoalAllocation.year == year,
                SavingsGoalAllocation.month == month,
            )
        ).scalar_one_or_none()
        if row is None:
            row = SavingsGoalAllocation(
                goal_id=goal_id, year=year, month=month, amount=amount, source=source
            )
            self.db.add(row)
        else:
            row.amount = amount
            row.source = source
        self.db.commit()
        self.db.refresh(row)
        return row

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
        self.db.commit()

    # ------------------------------------------------------------------
    # Transaction links
    # ------------------------------------------------------------------

    def get_links(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return transaction links, optionally scoped to a single goal."""
        stmt = select(SavingsGoalLink)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalLink.goal_id == goal_id)
        return _to_frame(self.db.execute(stmt).scalars().all(), LINK_COLUMNS)

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
        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_link(self, link_id: int) -> None:
        """Delete a transaction link by id."""
        link = self.db.get(SavingsGoalLink, link_id)
        if not link:
            raise ValueError(f"No savings goal link with id {link_id}")
        self.db.delete(link)
        self.db.commit()

    # ------------------------------------------------------------------
    # Investment earmarks
    # ------------------------------------------------------------------

    def get_backings(self, goal_id: int | None = None) -> pd.DataFrame:
        """Return investment earmarks, optionally scoped to a single goal.

        Ordered by id so that when a holding loses value, the earlier earmark
        keeps its claim and the later one absorbs the shortfall.
        """
        stmt = select(SavingsGoalInvestment).order_by(SavingsGoalInvestment.id)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalInvestment.goal_id == goal_id)
        return _to_frame(self.db.execute(stmt).scalars().all(), BACKING_COLUMNS)

    def get_backing(
        self, goal_id: int, investment_id: int
    ) -> SavingsGoalInvestment | None:
        """Return one goal's earmark against one investment, or None."""
        return self.db.execute(
            select(SavingsGoalInvestment).where(
                SavingsGoalInvestment.goal_id == goal_id,
                SavingsGoalInvestment.investment_id == investment_id,
            )
        ).scalar_one_or_none()

    def upsert_backing(
        self, goal_id: int, investment_id: int, amount: float | None
    ) -> SavingsGoalInvestment:
        """Earmark an investment for a goal, replacing any existing earmark."""
        backing = self.get_backing(goal_id, investment_id)
        if backing is None:
            backing = SavingsGoalInvestment(
                goal_id=goal_id, investment_id=investment_id, amount=amount
            )
            self.db.add(backing)
        else:
            backing.amount = amount
        self.db.commit()
        self.db.refresh(backing)
        return backing

    def delete_backing(self, backing_id: int) -> None:
        """Delete an investment earmark by id."""
        backing = self.db.get(SavingsGoalInvestment, backing_id)
        if not backing:
            raise ValueError(f"No savings goal investment with id {backing_id}")
        self.db.delete(backing)
        self.db.commit()

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
