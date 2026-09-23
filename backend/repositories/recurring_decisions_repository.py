"""Repository for user verdicts on detected recurring charges."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.recurring_decision import RecurringDecision

#: The two verdicts that can be stored. Anything else is *pending*, which is
#: represented by the absence of a row rather than by a value.
DECISIONS = ("confirmed", "dismissed")
PENDING = "pending"


class RecurringDecisionsRepository:
    """Read and write the per-merchant recurring-charge verdicts."""

    def __init__(self, db: Session) -> None:
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

    def apply(self, entries: list[dict[str, Any]]) -> None:
        """Apply a batch of verdicts in a single transaction.

        One commit for the whole batch, which is what the caller needs: every
        commit invalidates the process-wide derived-read cache, so a batch
        written a row at a time made the recurring detection re-run once per
        entry and "confirm all" took seconds.

        Parameters
        ----------
        entries : list[dict[str, Any]]
            Each entry ``{"normalized": str, "decision": str}`` plus the
            optional display fields ``label``, ``amount`` and ``cadence``.
            A decision of ``'pending'`` deletes the stored verdict.
        """
        rows = self.get_all()
        for entry in entries:
            normalized = entry["normalized"]
            decision = entry["decision"]

            if decision == PENDING:
                row = rows.pop(normalized, None)
                if row is not None:
                    self.db.delete(row)
                continue

            row = rows.get(normalized)
            if row is None:
                row = RecurringDecision(normalized=normalized, decision=decision)
                self.db.add(row)
                rows[normalized] = row
            row.decision = decision
            # Only overwrite the remembered display fields when the caller
            # has something to offer — a verdict re-made from a stale client
            # must not blank out what the last decision recorded.
            if entry.get("label") is not None:
                row.label = entry["label"]
            if entry.get("amount") is not None:
                row.decided_amount = entry["amount"]
            if entry.get("cadence") is not None:
                row.decided_cadence = entry["cadence"]
        self.db.commit()
