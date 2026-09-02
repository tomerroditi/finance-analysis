"""
Interest rates repository with SQLAlchemy ORM.
"""

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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
        # One atomic INSERT .. ON CONFLICT DO UPDATE per point, rather than
        # SELECT-then-INSERT. The read-then-write version raced: seeding is
        # lazy (RatesService.ensure_seeded is check-then-act), so two
        # concurrent cold requests — the Liabilities page fetches
        # /rates/current and /rates/history at once — both saw an empty
        # series and both inserted the same points. The loser hit
        # `UNIQUE constraint failed: interest_rates.series, date` and the
        # request 500'd on a fresh install. Conflict resolution belongs in
        # the write itself, where it is atomic.
        changed = 0
        for point in points:
            stmt = sqlite_insert(InterestRate).values(
                series=series,
                date=point["date"],
                value=float(point["value"]),
                source=source,
            )
            # DO UPDATE only when the value actually moved, so the return
            # count keeps meaning "points inserted or changed".
            stmt = stmt.on_conflict_do_update(
                index_elements=["series", "date"],
                set_={
                    "value": stmt.excluded.value,
                    "source": stmt.excluded.source,
                    "updated_at": func.now(),
                },
                where=InterestRate.value.is_distinct_from(stmt.excluded.value),
            )
            changed += self.db.execute(stmt).rowcount
        if changed:
            self.db.commit()
        return changed
