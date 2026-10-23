"""The recurring cards: review nudge, new subscriptions and price changes."""

from backend.services.insights.context import Card, InsightContext

# A price change must move by ``max(MIN_DELTA, MIN_SHARE × price)`` to be news.
PRICE_CHANGE_MIN_DELTA = 20.0
PRICE_CHANGE_MIN_SHARE = 0.1
MAX_CARDS = 3


def insights(ctx: InsightContext) -> list[Card]:
    """Surface confirmed subscriptions that are new or repriced.

    Also nudges the user when candidates are waiting to be reviewed — a
    detection nobody has ruled on yet is a question, not a finding, so it gets
    one card asking for the ruling rather than one card each.

    A price change has to be worth reading: detection reports any move past
    its own tolerance, but a few shekels on a small subscription is drift, not
    a decision to make.

    Parameters
    ----------
    ctx : InsightContext
        The request's shared inputs.

    Returns
    -------
    list[Card]
        Up to ``MAX_CARDS`` undismissed cards.
    """
    summary = ctx.recurring_summary
    results: list[Card] = []
    if summary["pending_count"]:
        results.append(
            {
                "code": "recurringToReview",
                "key": f"recurringToReview:{ctx.month}",
                "severity": "info",
                "data": {
                    "count": summary["pending_count"],
                    "amount": summary["pending_monthly"],
                },
            }
        )
    for item in summary["items"]:
        if item["confirmation"] != "confirmed":
            continue
        subject = item.get("normalized") or item["label"]
        if item["status"] == "new":
            results.append(
                {
                    "code": "newRecurring",
                    "key": f"newRecurring:{subject}",
                    "severity": "info",
                    "data": {
                        "label": item["label"],
                        "amount": item["amount"],
                        "cadence": item["cadence"],
                    },
                }
            )
        elif item["status"] == "price_changed":
            delta = abs(item["price_change"])
            if delta < max(
                PRICE_CHANGE_MIN_DELTA, abs(item["amount"]) * PRICE_CHANGE_MIN_SHARE
            ):
                continue
            increased = item["price_change"] > 0
            code = "priceIncrease" if increased else "priceDecrease"
            results.append(
                {
                    "code": code,
                    # The price itself is part of the identity: a dismissal
                    # covers this change, not the next one.
                    "key": f"{code}:{subject}:{item['last_amount']}",
                    "severity": "warning" if increased else "info",
                    "data": {
                        "label": item["label"],
                        "delta": delta,
                        "amount": item["last_amount"],
                    },
                }
            )
    return ctx.visible(results)[:MAX_CARDS]
