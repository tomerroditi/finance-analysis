"""
Budget claim ledger.

Decides, once for every expense row, which budget pool owns it and in which
month — the one answer the Monthly, Yearly and Project tabs, the Overview, the
trend and the insights strip all read, so no two of them can disagree about
where a shekel went.

Each row gets:

- ``budget_year`` / ``budget_month`` — its budget month override when it has
  one, else the month of its date. Every pool reads this, yearly included: a
  purchase moved into January belongs to January's year.
- ``claim_kind`` — exactly one of ``project`` / ``yearly`` / ``monthly`` /
  ``other``. A project category is the project's whatever its tag; then a
  yearly rule of the row's budget year; then a monthly rule of its budget
  month; anything no rule claims is ``other`` — whether or not the month has
  any rules, so the pools always add up to everything spent.
- ``claim_rule_id`` — the rule that claimed it. Within a kind the most
  specific rule claims first (see :func:`claim_order`). A project row names
  its most specific per-tag rule, never the all-tags anchor, which is the
  project's total; a row no per-tag rule names carries no id.

The module is pure: it takes the rows, the rules and the override map and
touches no database, so its rules are tested on hand-built frames.
"""

from typing import Any

import numpy as np
import pandas as pd

from backend.constants.budget import (
    ALL_TAGS,
    CATEGORY,
    ID,
    MONTH,
    PERIOD_MONTHLY,
    PERIOD_PROJECT,
    PERIOD_TYPE,
    PERIOD_YEARLY,
    TAGS,
    TOTAL_BUDGET,
    YEAR,
)
from backend.constants.tables import TransactionsTableFields
from backend.services.pending_refunds_service import (
    GROSS_AMOUNT_COLUMN,
    restore_gross_amounts,
)

BUDGET_YEAR = "budget_year"
BUDGET_MONTH = "budget_month"
CLAIM_KIND = "claim_kind"
CLAIM_RULE_ID = "claim_rule_id"
NET_AMOUNT = "net_amount"

KIND_PROJECT = "project"
KIND_YEARLY = "yearly"
KIND_MONTHLY = "monthly"
KIND_OTHER = "other"

#: The kinds that make up a month's monthly pool — what its Total Budget caps.
MONTHLY_POOL = (KIND_MONTHLY, KIND_OTHER)


def is_all_tags(tags: list[str] | str | None) -> bool:
    """Return whether a tag list is the all-tags sentinel (case-insensitive).

    The single comparison point for the sentinel — legacy rows stored
    ``"All Tags"`` in mixed case, so exact matches against ``ALL_TAGS``
    silently miss them. Accepts the raw semicolon string too.
    """
    if isinstance(tags, str):
        tags = tags.split(";")
    if not tags:
        return False
    return [str(t).lower() for t in tags] == [ALL_TAGS.lower()]


def claim_order(rules: pd.DataFrame) -> list[int]:
    """Return positions of ``rules`` in the order they claim transactions.

    The most specific rule claims first: a rule naming fewer tags beats one
    naming more, and all-tags goes last so it covers only what no sibling
    tag rule claimed. Ties keep the rules' own order.
    """

    def priority(position: int) -> tuple[bool, int, int]:
        """Sort key: all-tags last, then fewer tags first, then position."""
        tags = rules.iloc[position][TAGS]
        return is_all_tags(tags), len(tags), position

    return sorted(range(len(rules)), key=priority)


def budget_months(
    expenses: pd.DataFrame, overrides: dict[str, dict[Any, tuple[int, int]]]
) -> tuple[pd.Series, pd.Series]:
    """Return each row's ``(budget_year, budget_month)``: its override, else its date.

    Parameters
    ----------
    expenses : pd.DataFrame
        Rows carrying ``date``, ``source`` and ``unique_id`` (``split_id``
        for split children).
    overrides : dict
        ``{"transaction": {(table, unique_id): (y, m)}, "split": {split_id:
        (y, m)}}`` as :meth:`BudgetMonthOverrideService.get_override_map`
        builds it.

    Returns
    -------
    tuple[pd.Series, pd.Series]
        Integer year and month series aligned to ``expenses``.
    """
    dates = pd.to_datetime(expenses[TransactionsTableFields.DATE.value])
    year = dates.dt.year
    month = dates.dt.month

    tx_map = overrides.get("transaction") or {}
    if tx_map:
        # `unique_id` is a per-table auto-increment, so it only identifies a
        # row alongside its source table.
        keys = pd.Series(
            list(
                zip(
                    expenses[TransactionsTableFields.SOURCE.value],
                    expenses[TransactionsTableFields.UNIQUE_ID.value],
                    strict=True,
                )
            ),
            index=expenses.index,
            dtype=object,
        )
        year = keys.map({k: v[0] for k, v in tx_map.items()}).fillna(year)
        month = keys.map({k: v[1] for k, v in tx_map.items()}).fillna(month)

    split_map = overrides.get("split") or {}
    split_col = TransactionsTableFields.SPLIT_ID.value
    if split_map and split_col in expenses.columns:
        split_ids = expenses[split_col]
        year = split_ids.map({k: v[0] for k, v in split_map.items()}).fillna(year)
        month = split_ids.map({k: v[1] for k, v in split_map.items()}).fillna(month)

    return year.astype(int), month.astype(int)


def assign_claims(
    expenses: pd.DataFrame,
    rules: pd.DataFrame,
    overrides: dict[str, dict[Any, tuple[int, int]]],
) -> pd.DataFrame:
    """Give every expense row its budget month and the one pool that owns it.

    Parameters
    ----------
    expenses : pd.DataFrame
        Expense rows (non-expense categories and split parents already out),
        with ``date``, ``category``, ``tag``, ``source``, ``unique_id`` and
        ``amount``.
    rules : pd.DataFrame
        Every budget rule, ``tags`` parsed into lists.
    overrides : dict
        The budget month override map (see :func:`budget_months`).

    Returns
    -------
    pd.DataFrame
        A copy of ``expenses`` with :data:`BUDGET_YEAR`, :data:`BUDGET_MONTH`,
        :data:`CLAIM_KIND` and :data:`CLAIM_RULE_ID` added.
    """
    claims = expenses.copy()
    if claims.empty:
        for column in (BUDGET_YEAR, BUDGET_MONTH, CLAIM_KIND, CLAIM_RULE_ID):
            claims[column] = pd.Series(dtype=object)
        return claims

    claims[BUDGET_YEAR], claims[BUDGET_MONTH] = budget_months(claims, overrides)
    claims[CLAIM_KIND] = KIND_OTHER
    claims[CLAIM_RULE_ID] = pd.array([pd.NA] * len(claims), dtype="Int64")
    if rules.empty:
        return claims

    category = claims[TransactionsTableFields.CATEGORY.value]
    unclaimed = pd.Series(True, index=claims.index)

    projects = rules.loc[rules[PERIOD_TYPE] == PERIOD_PROJECT]
    for name, project_rules in projects.groupby(CATEGORY, sort=False):
        rows = unclaimed & (category == name)
        claims.loc[rows, CLAIM_KIND] = KIND_PROJECT
        per_tag = project_rules.loc[~project_rules[TAGS].apply(is_all_tags)]
        _claim(claims, rows, per_tag, KIND_PROJECT)
        unclaimed &= ~rows

    yearly = rules.loc[rules[PERIOD_TYPE] == PERIOD_YEARLY]
    for year, year_rules in yearly.groupby(YEAR, sort=False):
        rows = unclaimed & (claims[BUDGET_YEAR] == year)
        unclaimed &= ~_claim(claims, rows, year_rules, KIND_YEARLY)

    monthly = rules.loc[
        (rules[PERIOD_TYPE] == PERIOD_MONTHLY) & (rules[CATEGORY] != TOTAL_BUDGET)
    ]
    for (year, month), month_rules in monthly.groupby([YEAR, MONTH], sort=False):
        rows = (
            unclaimed & (claims[BUDGET_YEAR] == year) & (claims[BUDGET_MONTH] == month)
        )
        unclaimed &= ~_claim(claims, rows, month_rules, KIND_MONTHLY)

    return claims


def _claim(
    claims: pd.DataFrame, candidates: pd.Series, rules: pd.DataFrame, kind: str
) -> pd.Series:
    """Let ``rules`` claim ``candidates`` most-specific first; return what they took."""
    category = claims[TransactionsTableFields.CATEGORY.value]
    tag = claims[TransactionsTableFields.TAG.value]
    remaining = candidates.copy()
    for position in claim_order(rules):
        rule = rules.iloc[position]
        matched = remaining & (category == rule[CATEGORY])
        if not is_all_tags(rule[TAGS]):
            matched &= tag.isin(rule[TAGS])
        if not matched.any():
            continue
        claims.loc[matched, CLAIM_KIND] = kind
        claims.loc[matched, CLAIM_RULE_ID] = int(rule[ID])
        remaining &= ~matched
    return candidates & ~remaining


def in_budget_month(claims: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """Return the rows whose budget month is ``year``/``month``."""
    if claims.empty:
        return claims
    return claims.loc[(claims[BUDGET_YEAR] == year) & (claims[BUDGET_MONTH] == month)]


def of_kind(claims: pd.DataFrame, *kinds: str) -> pd.DataFrame:
    """Return the rows claimed by any of ``kinds``."""
    if claims.empty:
        return claims
    return claims.loc[claims[CLAIM_KIND].isin(kinds)]


def of_rule(claims: pd.DataFrame, rule_id: int) -> pd.DataFrame:
    """Return the rows rule ``rule_id`` claimed."""
    if claims.empty:
        return claims
    return claims.loc[claims[CLAIM_RULE_ID].eq(int(rule_id)).fillna(False)]


def spent(rows: pd.DataFrame) -> float:
    """Return what ``rows`` cost, as a positive expense figure."""
    if rows is None or rows.empty:
        return 0.0
    return float(rows[TransactionsTableFields.AMOUNT.value].sum() * -1)


def transaction_records(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Return ``rows`` as the transaction dicts a view lists: gross amounts, no claim columns.

    A pool totals what its rows *cost*, net of refunds, but the list under it
    shows the real transactions the user can act on (see
    :func:`restore_gross_amounts`). A row a refund reduced also carries
    ``net_amount`` — what it counts for in the pool — so the list can say so:
    without it a refund landing in a later month was netted into the purchase's
    month while nothing listed there explained the smaller total. Every other
    row carries ``net_amount = None``.

    Dates go out as plain ``YYYY-MM-DD``: the ledger parses them for month
    arithmetic, and a timestamp is neither what the other transaction lists
    serve nor something a date input or the edit endpoint accepts.
    """
    listed = rows.drop(columns=[CLAIM_KIND, CLAIM_RULE_ID], errors="ignore")
    amount = TransactionsTableFields.AMOUNT.value
    net = None
    if GROSS_AMOUNT_COLUMN in listed.columns:
        reduced = ~np.isclose(listed[amount], listed[GROSS_AMOUNT_COLUMN])
        net = listed[amount].astype(object).where(reduced, None)
    listed = restore_gross_amounts(listed)
    listed[NET_AMOUNT] = net
    date = TransactionsTableFields.DATE.value
    if date in listed.columns:
        listed[date] = pd.to_datetime(listed[date]).dt.strftime("%Y-%m-%d")
    return listed.to_dict(orient="records")
