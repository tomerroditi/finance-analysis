"""SavingsGoal database models.

A savings goal is a **virtual earmark** over money that already sits in the
user's tracked accounts — it never adds to net worth. Progress is derived, not
typed: each closed month's realized surplus is distributed across goals by
priority (see ``backend.services.savings_goal_service``), and the resulting
per-month amounts are persisted in ``savings_goal_allocations`` so history stays
stable when priorities later change.

Individual transactions can also be attached to a goal via
``savings_goal_links`` — either as a *contribution* (money put aside for the
goal, which consumes that month's surplus before the waterfall runs) or as a
*utilization* (money actually spent out of the goal, which never reduces the
goal's target).
"""

from sqlalchemy import Column, Integer, Float, String, UniqueConstraint

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables

#: Goal lifecycle states.
GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_CLOSED = "closed"

#: ``savings_goal_links.link_type`` values.
LINK_CONTRIBUTION = "contribution"
LINK_UTILIZATION = "utilization"

#: ``savings_goal_allocations.source`` values.
ALLOCATION_AUTO = "auto"
ALLOCATION_MANUAL = "manual"


class SavingsGoal(Base, TimestampMixin):
    """ORM model for a single savings goal.

    Attributes
    ----------
    name : str
        User-facing goal name (e.g. "Vacation", "Emergency fund").
    target_amount : float
        Amount the user wants to reach (NIS). Fixed — utilizing money out of a
        goal never reduces it.
    opening_balance : float
        Money already set aside for this goal before tracking began. Counts
        toward ``funded`` without consuming any month's surplus.
    priority : int
        Waterfall position; lower runs first. Surplus fills priority 1 before
        anything below it.
    monthly_cap : float or None
        Optional ceiling on how much surplus this goal may absorb in a single
        month. ``None`` means uncapped, so the goal can fill in one month.
    start_month : str or None
        First month (``YYYY-MM``) this goal participates in allocation.
        Defaults to the goal's creation month so a new goal never claims
        surpluses that predate it.
    target_date : str or None
        Optional target date in ``YYYY-MM-DD`` format.
    contribution_category : str or None
        When set, transactions in this category accrue to the goal as
        contributions automatically.
    contribution_tags : str or None
        Semicolon-separated tag names narrowing ``contribution_category``,
        matching the convention used by budget rules.
    status : str
        ``"active"`` or ``"closed"``. A closed goal stops absorbing surplus and
        its existing allocations become immutable.
    closed_month : str or None
        Month (``YYYY-MM``) the goal was closed in.
    notes : str or None
        Optional free-text note.
    """

    __tablename__ = Tables.SAVINGS_GOALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    opening_balance = Column(Float, nullable=False, default=0.0)
    priority = Column(Integer, nullable=False, default=0)
    monthly_cap = Column(Float, nullable=True)
    start_month = Column(String, nullable=True)
    target_date = Column(String, nullable=True)
    contribution_category = Column(String, nullable=True)
    contribution_tags = Column(String, nullable=True)
    status = Column(String, nullable=False, default=GOAL_STATUS_ACTIVE)
    closed_month = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    def __repr__(self):
        return (
            f"<SavingsGoal(id={self.id}, name={self.name!r}, "
            f"target={self.target_amount}, priority={self.priority})>"
        )


class SavingsGoalAllocation(Base, TimestampMixin):
    """One month's surplus allocation to one goal.

    Rows are written by the allocation engine, one per (goal, month). Past
    months are left untouched on subsequent runs — only an explicit rebuild
    rewrites them — so a priority change never silently restates history.

    Attributes
    ----------
    goal_id : int
        Owning ``savings_goals.id``.
    year, month : int
        Calendar month this allocation belongs to.
    amount : float
        Money directed into the goal that month (never negative).
    source : str
        ``"auto"`` for engine-computed rows, ``"manual"`` for user overrides.
    """

    __tablename__ = Tables.SAVINGS_GOAL_ALLOCATIONS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    source = Column(String, nullable=False, default=ALLOCATION_AUTO)

    # One allocation row per goal per month — the engine upserts.
    __table_args__ = (
        UniqueConstraint(
            "goal_id", "year", "month", name="uq_savings_goal_allocation_month"
        ),
    )

    def __repr__(self):
        return (
            f"<SavingsGoalAllocation(goal_id={self.goal_id}, "
            f"{self.year}-{self.month:02d}, amount={self.amount})>"
        )


class SavingsGoalLink(Base, TimestampMixin):
    """A transaction (or split) attached to a savings goal.

    Mirrors the ``(source_type, source_id, source_table)`` addressing used by
    pending refunds — ``unique_id`` is per-table, so the table must travel with
    the id (see ``.claude/rules/backend_repositories.md``).

    Attributes
    ----------
    goal_id : int
        Owning ``savings_goals.id``.
    source_type : str
        ``"transaction"`` or ``"split"``.
    source_id : int
        ``unique_id`` for transactions, ``id`` for splits.
    source_table : str
        Table the source lives in (e.g. ``"bank_transactions"``).
    link_type : str
        ``"contribution"`` (money into the goal) or ``"utilization"``
        (money spent out of it).
    """

    __tablename__ = Tables.SAVINGS_GOAL_LINKS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, nullable=False, index=True)
    source_type = Column(String, nullable=False)
    source_id = Column(Integer, nullable=False)
    source_table = Column(String, nullable=False)
    link_type = Column(String, nullable=False)

    # A transaction belongs to at most one goal, in one role.
    __table_args__ = (
        UniqueConstraint(
            "source_type", "source_id", "source_table",
            name="uq_savings_goal_link_source",
        ),
    )

    def __repr__(self):
        return (
            f"<SavingsGoalLink(goal_id={self.goal_id}, {self.link_type}, "
            f"{self.source_table}#{self.source_id})>"
        )
