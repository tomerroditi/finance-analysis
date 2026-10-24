"""Which transactions a savings goal claims, and what that makes the goal.

Pure functions over goals and analysis rows — no database access — shared by
the transaction scan (``inputs``), the ledger, the yearly figure and goal
validation, so the facts they all depend on are decided in one place:

- a **rule** (a category, optionally narrowed to tags) matches a row the way
  budget rules do: no tags, or ``all_tags``, means every tag;
- a goal's rules and links claim rows only inside its **claim span**, from
  its start month through the month it closed in;
- a goal **owns income** when it has a saved-into rule or any income it
  claims — such a goal may spend ahead of that income, and that income is
  the goal's money rather than the year's savings.
"""

from collections.abc import Iterable

import pandas as pd

from backend.constants.budget import ALL_TAGS
from backend.constants.tables import TransactionsTableFields
from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    SavingsGoal,
)
from backend.services.budget.ledger import is_all_tags
from backend.services.savings_goals.common import month_key

#: ``(first month, last month)`` a goal claims rows in; ``None`` is open-ended.
ClaimSpan = tuple[tuple[int, int] | None, tuple[int, int] | None]


def split_tags(tags: str | None) -> list[str]:
    """Split the semicolon-separated tag string budgets also use."""
    if not tags:
        return []
    return [t.strip() for t in str(tags).split(";") if t.strip()]


def rule_mask(df: pd.DataFrame, category: str, tags: str | None) -> pd.Series:
    """Return which rows of ``df`` a category/tag rule matches."""
    matches = df[TransactionsTableFields.CATEGORY.value] == category
    tag_list = split_tags(tags)
    tag_col = TransactionsTableFields.TAG.value
    if tag_list and not is_all_tags(tag_list) and tag_col in df.columns:
        matches &= df[tag_col].isin(tag_list)
    return matches


def rules_overlap(
    one: tuple[str | None, str | None], other: tuple[str | None, str | None]
) -> bool:
    """Whether two ``(category, tags)`` rules can match the same transaction."""
    if not one[0] or one[0] != other[0]:
        return False
    tags, other_tags = split_tags(one[1]), split_tags(other[1])
    if not tags or not other_tags or ALL_TAGS in tags or ALL_TAGS in other_tags:
        return True
    return bool(set(tags) & set(other_tags))


def claim_span(goal: SavingsGoal) -> ClaimSpan:
    """Return the first and last month a goal's rules and links claim rows in."""
    last = month_key(goal.closed_month) if goal.status == GOAL_STATUS_CLOSED else None
    return month_key(goal.start_month), last


def in_span(month: tuple[int, int], span: ClaimSpan) -> bool:
    """Whether ``month`` falls inside a goal's claim span."""
    first, last = span
    return (first is None or month >= first) and (last is None or month <= last)


def goals_owning_income(
    goals: Iterable[SavingsGoal], claimed: Iterable[tuple[int, str]]
) -> set[int]:
    """Return the ids of the goals with income of their own.

    Parameters
    ----------
    goals : iterable of SavingsGoal
        Every goal.
    claimed : iterable of tuple
        ``(goal_id, link_type)`` for every row a goal claims.

    Returns
    -------
    set[int]
        Goals with a saved-into rule, plus goals that claim any income.
    """
    owners = {g.id for g in goals if g.contribution_category}
    owners.update(gid for gid, kind in claimed if kind == LINK_CONTRIBUTION)
    return owners
