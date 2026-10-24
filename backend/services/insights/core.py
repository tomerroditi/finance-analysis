"""``InsightsService``: runs the insight rules and assembles the strip.

Each card is returned as a structured ``{code, key, severity, data}`` object;
the frontend maps ``code`` to a translated, interpolated message so copy stays
bilingual (en/he) without backend string formatting. What makes a card worth
showing is each rule's business (see ``context``); this module only decides
how the rules' cards share the strip.
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.repositories.insight_dismissals_repository import (
    InsightDismissalsRepository,
)
from backend.services.insights import (
    category_spike,
    large_transaction,
    pace,
    recurring,
)
from backend.services.insights.context import Card, InsightContext

MAX_INSIGHTS = 6
_SEVERITY_RANK = {"warning": 0, "info": 1, "positive": 2}


def assemble(
    *,
    pace_cards: list[Card],
    spikes: list[Card],
    recurring_cards: list[Card],
    large_charges: list[Card],
) -> list[Card]:
    """Combine every rule's cards into the strip.

    One event, one card: a large charge in a category that already spiked is
    the news the spike delivered, so it is dropped. The rest are ordered
    warnings first, then info, then positive — most actionable up top — and
    within a band the biggest sum of money first, then capped.

    Parameters
    ----------
    pace_cards, spikes, recurring_cards, large_charges : list[Card]
        Each rule's undismissed cards.

    Returns
    -------
    list[Card]
        Up to ``MAX_INSIGHTS`` cards in display order.
    """
    spiked = {card["data"]["category"] for card in spikes}
    cards = [
        *pace_cards,
        *spikes,
        *recurring_cards,
        *(c for c in large_charges if c["data"].get("category") not in spiked),
    ]
    cards.sort(
        key=lambda c: (
            _SEVERITY_RANK.get(c["severity"], 1),
            -float(c["data"].get("amount") or 0.0),
        )
    )
    return cards[:MAX_INSIGHTS]


class InsightsService:
    """Build the dashboard's insight strip and record dismissals.

    Parameters
    ----------
    db : Session
        SQLAlchemy session for database operations.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.dismissals = InsightDismissalsRepository(db)

    def get_insights(self) -> list[dict[str, Any]]:
        """Build the prioritized list of insight cards.

        Returns
        -------
        list[dict[str, Any]]
            Up to ``MAX_INSIGHTS`` insight dicts, each with:

            - ``code`` – stable identifier the frontend maps to a message.
            - ``key`` – stable identity of *this* card, for dismissal.
            - ``severity`` – ``positive`` / ``info`` / ``warning``.
            - ``data`` – payload for message interpolation (amounts, labels).
        """
        ctx = InsightContext(self.db)
        return assemble(
            pace_cards=pace.insights(ctx),
            spikes=category_spike.insights(ctx),
            recurring_cards=recurring.insights(ctx),
            large_charges=large_transaction.insights(ctx),
        )

    def dismiss(self, key: str) -> dict[str, str | bool]:
        """Wave one insight card away.

        Parameters
        ----------
        key : str
            The card's ``key``, exactly as ``get_insights`` reported it.

        Returns
        -------
        dict[str, str | bool]
            ``{key, dismissed}``.
        """
        self.dismissals.dismiss(key)
        return {"key": key, "dismissed": True}

    def restore(self, key: str) -> dict[str, str | bool]:
        """Undo a dismissal, letting the card come back.

        Parameters
        ----------
        key : str
            The card's ``key``.

        Returns
        -------
        dict[str, str | bool]
            ``{key, dismissed}``.
        """
        self.dismissals.restore(key)
        return {"key": key, "dismissed": False}
