"""Insight cards the user has waved away."""

from sqlalchemy import Column, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class InsightDismissal(Base, TimestampMixin):
    """One insight card the user dismissed from the dashboard strip.

    The card is identified by the stable ``key`` ``InsightsService`` mints for
    it, which encodes what the card is *about* rather than its wording: a
    month for the ones that describe the running month, a transaction for a
    large charge, a merchant and price for a repriced subscription. So a
    dismissal is forgotten exactly when the thing it silenced changes — next
    month's spike in the same category is a new key and shows up again, while
    the one the user waved away stays gone.

    Attributes
    ----------
    key : str
        The insight's stable identity (``InsightsService`` ``key`` field).
        Unique — one dismissal per card.
    """

    __tablename__ = Tables.INSIGHT_DISMISSALS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True, index=True)
