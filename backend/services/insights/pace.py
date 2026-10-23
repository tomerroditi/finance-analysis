"""The month-pace card: ``overspendPace`` / ``onTrack``."""

from backend.services.insights.context import Card, InsightContext

# A gap smaller than this share of expected income is inside the forecast's
# own error bars.
MIN_SHARE = 0.05


def insights(ctx: InsightContext) -> list[Card]:
    """Flag whether the month is on pace to over- or under-spend.

    A gap smaller than ``MIN_SHARE`` of expected income is noise in the
    projection, and a gap a running project accounts for is the user's own
    plan playing out — neither is worth a warning.

    Parameters
    ----------
    ctx : InsightContext
        The request's shared inputs.

    Returns
    -------
    list[Card]
        At most one card, not yet dismissed.
    """
    forecast = ctx.forecast
    income = forecast["expected_income"]
    expenses = forecast["expected_expenses"]
    if income <= 0:
        return []

    floor = income * MIN_SHARE
    if expenses > income:
        gap = expenses - income
        if gap < floor or gap <= ctx.project_spend_this_month:
            return []
        return ctx.visible(
            [
                {
                    "code": "overspendPace",
                    "key": f"overspendPace:{ctx.month}",
                    "severity": "warning",
                    "data": {"amount": round(gap, 2)},
                }
            ]
        )
    if forecast["projected_net"] >= floor:
        return ctx.visible(
            [
                {
                    "code": "onTrack",
                    "key": f"onTrack:{ctx.month}",
                    "severity": "positive",
                    "data": {"amount": forecast["projected_net"]},
                }
            ]
        )
    return []
