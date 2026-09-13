"""Repository for user verdicts on detected recurring charges."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.recurring_decision import RecurringDecision

#: The two verdicts that can be stored. Anything else is *pending*, which is
#: represented by the absence of a row rather than by a value.
DECISIONS = ("confirmed", "dismissed")
PENDING = "pending"


class RecurringDecisionsRepository:
    """Read and write the per-merchant recurring-charge verdicts."""

    def __init__(self, db: Session):
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db

    def get_all(self) -> dict[str, RecurringDecision]:
        """Return every stored verdict keyed by normalized merchant label.

        Returns
        -------
        dict[str, RecurringDecision]
            Mapping of normalized label to its stored decision row.
        """
        rows = self.db.execute(select(RecurringDecision)).scalars().all()
        return {row.normalized: row for row in rows}

    def get(self, normalized: str) -> RecurringDecision | None:
        """Return the stored verdict for one merchant, if any.

        Parameters
        ----------
        normalized : str
            Normalized merchant label.

        Returns
        -------
        RecurringDecision or None
            The stored row, or None when the candidate is still pending.
        """
        return self.db.execute(
            select(RecurringDecision).where(RecurringDecision.normalized == normalized)
        ).scalar_one_or_none()

    def set_decision(
        self,
        normalized: str,
        decision: str,
        label: str | None = None,
        amount: float | None = None,
        cadence: str | None = None,
    ) -> RecurringDecision:
        """Upsert one verdict.

        Parameters
        ----------
        normalized : str
            Normalized merchant label — the key detection groups on.
        decision : str
            ``'confirmed'`` or ``'dismissed'``.
        label : str, optional
            Human-readable description to remember alongside the verdict.
        amount : float, optional
            Median amount at decision time.
        cadence : str, optional
            Cadence at decision time.

        Returns
        -------
        RecurringDecision
            The stored row.
        """
        row = self.get(normalized)
        if row is None:
            row = RecurringDecision(normalized=normalized, decision=decision)
            self.db.add(row)
        row.decision = decision
        # Only overwrite the remembered display fields when the caller has
        # something to offer — a verdict re-made from a stale client must not
        # blank out what the last decision recorded.
        if label is not None:
            row.label = label
        if amount is not None:
            row.decided_amount = amount
        if cadence is not None:
            row.decided_cadence = cadence
        self.db.commit()
        self.db.refresh(row)
        return row

    def clear(self, normalized: str) -> bool:
        """Delete one verdict, returning the candidate to *pending*.

        Parameters
        ----------
        normalized : str
            Normalized merchant label.

        Returns
        -------
        bool
            True when a row was removed, False when there was nothing stored.
        """
        result = self.db.execute(
            delete(RecurringDecision).where(RecurringDecision.normalized == normalized)
        )
        self.db.commit()
        return bool(result.rowcount)
