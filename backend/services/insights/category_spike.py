"""The ``categorySpike`` card: a category spending well above its own trend."""

import pandas as pd

from backend.services.insights.context import Card, InsightContext

RATIO = 1.4
# The shekel floor is ``max(MIN_DELTA, MIN_SHARE × typical monthly outflow)``.
MIN_DELTA = 200.0
MIN_SHARE = 0.03
BASELINE_MONTHS = 3
MIN_HISTORY = 2
MAX_CARDS = 2


def insights(ctx: InsightContext) -> list[Card]:
    """Flag categories whose current-month spend is well above their trend.

    Only categories that *have* a trend qualify: a project or yearly envelope
    is lumpy by design, and a category seen in fewer than ``MIN_HISTORY`` of
    the baseline months has no normal to deviate from. Spend still inside its
    monthly budget is not a spike either — the budget page already owns that
    conversation.

    Parameters
    ----------
    ctx : InsightContext
        The request's shared inputs.

    Returns
    -------
    list[Card]
        Up to ``MAX_CARDS`` undismissed spikes, biggest overshoot first.
    """
    monthly = ctx.monthly_category_spend
    if len(monthly) < 2:
        return []

    current = next((m for m in monthly if m["month"] == ctx.month), None)
    if current is None:
        return []

    prior = [m for m in monthly if m["month"] < ctx.month][-BASELINE_MONTHS:]
    if len(prior) < MIN_HISTORY:
        return []

    planned = ctx.planned
    floor = max(MIN_DELTA, ctx.spending_baseline * MIN_SHARE)

    ranked: list[tuple[float, Card]] = []
    for category, amount in current["categories"].items():
        if planned.is_long_envelope(category):
            continue
        prior_vals = [m["categories"].get(category, 0.0) for m in prior]
        if sum(1 for v in prior_vals if v > 0) < MIN_HISTORY:
            continue
        # Median, not mean: one unusual month in the baseline should not
        # redefine "usual" — in either direction.
        baseline = float(pd.Series(prior_vals).median())
        if baseline <= 0:
            continue
        delta = amount - baseline
        if amount < baseline * RATIO or delta < floor:
            continue
        if planned.within_monthly_budget(category, amount):
            continue
        ranked.append(
            (
                delta,
                {
                    "code": "categorySpike",
                    "key": f"categorySpike:{category}:{ctx.month}",
                    "severity": "warning",
                    "data": {
                        "category": category,
                        "percent": round((amount / baseline - 1) * 100),
                        "amount": round(amount, 2),
                    },
                },
            )
        )

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ctx.visible([card for _, card in ranked])[:MAX_CARDS]
