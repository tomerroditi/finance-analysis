"""
Interest rates repository with SQLAlchemy ORM.
"""

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.interest_rate import InterestRate


class InterestRatesRepository:
    """
    Repository for interest rate series points.
    """

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def get_series(self, series: str) -> pd.DataFrame:
        """Get all points of a rate series ordered by date ascending.

        Parameters
        ----------
        series : str
            Series identifier (e.g. ``boi_rate``).

        Returns
        -------
        pd.DataFrame
            Columns ``series``, ``date``, ``value``, ``source`` —
            empty (column-less) DataFrame when the series has no points.
        """
        stmt = (
            select(InterestRate)
            .where(InterestRate.series == series)
            .order_by(InterestRate.date)
        )
        records = self.db.execute(stmt).scalars().all()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame([r.__dict__ for r in records])
        return df.drop(columns=["_sa_instance_state"], errors="ignore")

    def count_series(self, series: str) -> int:
        """Count the points stored for a series.

        Parameters
        ----------
        series : str
            Series identifier.

        Returns
        -------
        int
            Number of stored points.
        """
        stmt = select(func.count(InterestRate.id)).where(
            InterestRate.series == series
        )
        return int(self.db.execute(stmt).scalar_one())

    def upsert_points(
        self, series: str, points: list[dict], source: str = "seed"
    ) -> int:
        """Insert rate points, updating the value of existing dates.

        Parameters
        ----------
        series : str
            Series identifier.
        points : list[dict]
            Dicts with ``date`` (YYYY-MM-DD) and ``value`` keys.
        source : str
            Provenance stamp for newly inserted points.

        Returns
        -------
        int
            Number of points inserted or updated.
        """
        changed = 0
        for point in points:
            stmt = select(InterestRate).where(
                InterestRate.series == series, InterestRate.date == point["date"]
            )
            existing = self.db.execute(stmt).scalar_one_or_none()
            if existing is None:
                self.db.add(
                    InterestRate(
                        series=series,
                        date=point["date"],
                        value=float(point["value"]),
                        source=source,
                    )
                )
                changed += 1
            elif existing.value != float(point["value"]):
                existing.value = float(point["value"])
                existing.source = source
                changed += 1
        if changed:
            self.db.commit()
        return changed
