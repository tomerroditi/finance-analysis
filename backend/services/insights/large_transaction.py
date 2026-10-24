"""The ``largeTransaction`` card: one charge this month nothing explains."""

import pandas as pd

from backend.services.insights.context import Card, InsightContext, row_keys
from backend.services.recurring_service import RecurringService

RATIO = 4.0
# The shekel floor is ``max(MIN_AMOUNT, MIN_SHARE × typical monthly outflow)``.
MIN_AMOUNT = 1000.0
MIN_SHARE = 0.1
HISTORY_MONTHS = 6


def insights(ctx: InsightContext) -> list[Card]:
    """Flag an unusually large single expense in the current month.

    "Unusual" means unusual *for this household and this category*: a charge
    that no month in the trailing window matched, that no project or yearly
    envelope was opened for, and that is not a bill the user already confirmed
    as recurring (rent and insurance are large every time — that is the
    opposite of news).

    Refunds matched to their purchase are netted out first, on the same terms
    as every other spend surface. A charge that came back in full cost nothing
    and is not news either. The netting applies to the trailing history and
    the median too, so the comparison stays like for like.

    Parameters
    ----------
    ctx : InsightContext
        The request's shared inputs.

    Returns
    -------
    list[Card]
        At most one card: the largest undismissed charge that qualifies.
    """
    df = ctx.views.spending(exclude_liabilities=True).expenses
    df = df[df["amount"] < 0].copy()
    if df.empty:
        return []

    df["amount_abs"] = df["amount"].abs()
    median = float(df["amount_abs"].median())
    if median <= 0:
        return []

    df["date_parsed"] = pd.to_datetime(df["date"])
    month_start = ctx.today.replace(day=1)
    next_month = month_start + pd.DateOffset(months=1)
    this_month = df[
        (df["date_parsed"] >= month_start) & (df["date_parsed"] < next_month)
    ]
    if this_month.empty:
        return []

    history = df[
        (df["date_parsed"] < month_start)
        & (df["date_parsed"] >= month_start - pd.DateOffset(months=HISTORY_MONTHS))
    ]
    floor = max(MIN_AMOUNT, ctx.spending_baseline * MIN_SHARE)

    this_month = this_month.assign(_key=row_keys(this_month))
    for _, row in this_month.sort_values("amount_abs", ascending=False).iterrows():
        amount = float(row["amount_abs"])
        if amount < floor or amount < median * RATIO:
            # Sorted high to low — nothing further down can qualify.
            break
        category = row.get("category")
        if row["_key"] in ctx.envelope_rows:
            continue
        if (
            RecurringService.normalize_description(row.get("description"))
            in ctx.confirmed_recurring_keys
        ):
            continue
        peers = history.loc[history["category"] == category, "amount_abs"]
        if not peers.empty and amount <= float(peers.max()):
            continue
        # ``unique_id`` is per-table, so the source table is part of the key —
        # bank #5 and credit-card #5 are different charges.
        key = f"largeTransaction:{row.get('source')}:{row.get('unique_id')}"
        if key in ctx.dismissed:
            continue
        return [
            {
                "code": "largeTransaction",
                "key": key,
                "severity": "info",
                "data": {
                    "label": row.get("description") or category or "",
                    "amount": round(amount, 2),
                    "category": category if isinstance(category, str) else "",
                },
            }
        ]
    return []
