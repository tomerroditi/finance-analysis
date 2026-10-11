"""SavingsGoal database models.

A savings goal is a **virtual earmark** over money that already sits in the
user's tracked bank and cash accounts — it never adds to net worth. A goal
holds what the user put there (``savings_goal_entries``), plus income its
"saved into" rule claims, less spending paid out of it. Nothing is
distributed automatically.

Individual transactions can also be attached to a goal via
``savings_goal_links`` — either as a *contribution* (income that belongs to
the goal) or as a *utilization* (money spent out of it, which never reduces
the goal's target).
"""

from sqlalchemy import Column, Float, Integer, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin

#: Goal lifecycle states.
GOAL_STATUS_ACTIVE = "active"
GOAL_STATUS_CLOSED = "closed"

#: ``savings_goal_links.link_type`` values.
LINK_CONTRIBUTION = "contribution"
LINK_UTILIZATION = "utilization"

#: ``savings_goal_entries.source`` values.
ENTRY_MANUAL = "manual"
ENTRY_COVER = "cover"
ENTRY_CLOSE = "close"
ENTRY_MIGRATED = "migrated"


class SavingsGoal(Base, TimestampMixin):
    """ORM model for a single savings goal.

    Attributes
    ----------
    name : str
        User-facing goal name (e.g. "Vacation", "Emergency fund").
    target_amount : float
        Amount the user wants to reach (NIS). Fixed — utilizing money out of a
        goal never reduces it.
    priority : int
        List position; lower comes first. It orders "fund all" and the plan
        that covers a free-cash shortfall (lowest priority gives back first).
    monthly_amount : float or None
        How much the user means to put in each month; the card suggests it.
        ``None`` falls back to what the target date needs, if there is one.
    start_month : str or None
        First month (``YYYY-MM``) the goal's rules claim transactions from.
        Defaults to the goal's creation month.
    target_date : str or None
        Optional target date in ``YYYY-MM-DD`` format.
    contribution_category : str or None
        When set, transactions in this category accrue to the goal as
        contributions automatically.
    contribution_tags : str or None
        Semicolon-separated tag names narrowing ``contribution_category``,
        matching the convention used by budget rules.
    utilization_category : str or None
        When set, transactions in this category are spent out of the goal as
        utilizations automatically — the ones on record and every one that
        lands later. This is how a project budget or a yearly envelope is paid
        for out of a goal with one link instead of one transaction at a time.
    utilization_tags : str or None
        Semicolon-separated tag names narrowing ``utilization_category``;
        ``None`` covers every tag in the category.
    status : str
        ``"active"`` or ``"closed"``. Closing hands what the goal still holds
        back to free cash, and its rules stop claiming transactions after the
        month it closed in.
    closed_month : str or None
        Month (``YYYY-MM``) the goal was closed in.
    notes : str or None
        Optional free-text note.
    """

    __tablename__ = Tables.SAVINGS_GOALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    monthly_amount = Column(Float, nullable=True)
    start_month = Column(String, nullable=True)
    target_date = Column(String, nullable=True)
    contribution_category = Column(String, nullable=True)
    contribution_tags = Column(String, nullable=True)
    utilization_category = Column(String, nullable=True)
    utilization_tags = Column(String, nullable=True)
    status = Column(String, nullable=False, default=GOAL_STATUS_ACTIVE)
    closed_month = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SavingsGoal(id={self.id}, name={self.name!r}, "
            f"target={self.target_amount}, priority={self.priority})>"
        )


class SavingsGoalEntry(Base, TimestampMixin):
    """Money the user put into a goal, or took back out of it.

    The only way free cash becomes a goal's money: every entry is a choice the
    user made (or confirmed, for a ``cover`` plan), so a goal's balance never
    moves for a reason they cannot see.

    Attributes
    ----------
    goal_id : int
        Owning ``savings_goals.id``.
    date : str
        ``YYYY-MM-DD`` the money moved.
    amount : float
        Signed: positive puts money into the goal, negative takes it out.
    source : str
        ``"manual"`` (added or taken out by hand), ``"cover"`` (taken out by a
        confirmed free-cash cover plan), ``"close"`` (handed back when the
        goal closed) or ``"migrated"`` (carried over from the old automatic
        ledger).
    note : str or None
        Optional free text.
    """

    __tablename__ = Tables.SAVINGS_GOAL_ENTRIES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, nullable=False, index=True)
    date = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    source = Column(String, nullable=False, default=ENTRY_MANUAL)
    note = Column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SavingsGoalEntry(goal_id={self.goal_id}, {self.date}, "
            f"amount={self.amount}, source={self.source!r})>"
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
            "source_type",
            "source_id",
            "source_table",
            name="uq_savings_goal_link_source",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SavingsGoalLink(goal_id={self.goal_id}, {self.link_type}, "
            f"{self.source_table}#{self.source_id})>"
        )


class YearlySavingsTarget(Base, TimestampMixin):
    """How much the user aims to save in one calendar year.

    One row per year, so a past year keeps the target it was measured
    against.

    Attributes
    ----------
    year : int
        Calendar year.
    target_amount : float
        The amount to save that year.
    """

    __tablename__ = Tables.YEARLY_SAVINGS_TARGETS.value

    year = Column(Integer, primary_key=True, autoincrement=False)
    target_amount = Column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<YearlySavingsTarget(year={self.year}, target={self.target_amount})>"
