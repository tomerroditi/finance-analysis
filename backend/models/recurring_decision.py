"""User decisions on detected recurring charges (subscriptions)."""

from sqlalchemy import Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class RecurringDecision(Base, TimestampMixin):
    """One user verdict on a detected recurring-charge candidate.

    Detection is a heuristic, so a candidate is only a *suggestion* until the
    user rules on it. A row here is that ruling, keyed by the same normalized
    merchant label detection groups on, so the verdict survives new charges
    landing, a re-run of detection, and the amount or cadence drifting.

    Attributes
    ----------
    normalized : str
        Normalized merchant key (``RecurringService.normalize_description``).
        Unique — one verdict per merchant.
    label : str, optional
        Human-readable description as it read when the user decided. Kept for
        display in the dismissed list, where detection may no longer produce
        the candidate at all.
    decision : str
        ``'confirmed'`` (treat as a real recurring charge) or ``'dismissed'``
        (never treat it as one). Absence of a row means *pending*.
    decided_amount : float, optional
        Median charge amount at decision time, for audit.
    decided_cadence : str, optional
        Cadence at decision time, for audit.
    """

    __tablename__ = Tables.RECURRING_DECISIONS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized = Column(String, nullable=False, unique=True, index=True)
    label = Column(String, nullable=True)
    decision = Column(String, nullable=False)
    decided_amount = Column(Float, nullable=True)
    decided_cadence = Column(String, nullable=True)
