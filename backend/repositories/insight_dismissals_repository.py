"""Repository for the insight cards the user has dismissed."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.insight_dismissal import InsightDismissal


class InsightDismissalsRepository:
    """Read and write the set of dismissed insight keys."""

    def __init__(self, db: Session) -> None:
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db

    def get_keys(self) -> set[str]:
        """Return every dismissed insight key.

        Returns
        -------
        set[str]
            The stored keys. Empty when nothing has been dismissed.
        """
        return set(self.db.execute(select(InsightDismissal.key)).scalars().all())

    def dismiss(self, key: str) -> InsightDismissal:
        """Record one dismissal, or return the existing row unchanged.

        Parameters
        ----------
        key : str
            The insight's stable identity, as ``InsightsService`` minted it.

        Returns
        -------
        InsightDismissal
            The stored row.
        """
        row = self.db.execute(
            select(InsightDismissal).where(InsightDismissal.key == key)
        ).scalar_one_or_none()
        if row is None:
            row = InsightDismissal(key=key)
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row

    def restore(self, key: str) -> bool:
        """Delete one dismissal, letting the card come back.

        Parameters
        ----------
        key : str
            The insight's stable identity.

        Returns
        -------
        bool
            True when a row was removed, False when nothing was stored.
        """
        result = self.db.execute(
            delete(InsightDismissal).where(InsightDismissal.key == key)
        )
        self.db.commit()
        return bool(result.rowcount)
