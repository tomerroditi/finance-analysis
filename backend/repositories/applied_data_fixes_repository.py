"""Repository for the one-time data repairs already applied."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.applied_data_fix import AppliedDataFix


class AppliedDataFixesRepository:
    """Read and record which one-time data repairs have run."""

    def __init__(self, db: Session) -> None:
        """Initialize the repository.

        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db

    def get_names(self) -> set[str]:
        """Return the names of every applied fix.

        Returns
        -------
        set[str]
            The recorded names. Empty on a database no fix has run on.
        """
        return set(self.db.execute(select(AppliedDataFix.name)).scalars().all())

    def mark_applied(self, name: str) -> None:
        """Record a fix as applied.

        Parameters
        ----------
        name : str
            The fix's registered name.
        """
        self.db.add(AppliedDataFix(name=name))
        self.db.commit()
