"""Unit tests for InterestRatesRepository — point upserts and concurrency."""

import threading

from sqlalchemy.orm import sessionmaker

from backend.constants.loans import BOI_RATE_SERIES
from backend.database import create_db_engine
from backend.models.base import Base
from backend.models.interest_rate import InterestRate
from backend.repositories.interest_rates_repository import InterestRatesRepository

POINTS = [
    {"date": "2024-01-01", "value": 4.5},
    {"date": "2024-06-01", "value": 4.25},
    {"date": "2024-12-01", "value": 4.0},
]


class TestUpsertPoints:
    """Tests for insert/update semantics of upsert_points."""

    def test_new_points_are_inserted_and_counted(self, db_session):
        """Every new point is stored and included in the changed count."""
        repo = InterestRatesRepository(db_session)
        assert repo.upsert_points(BOI_RATE_SERIES, POINTS) == len(POINTS)
        assert repo.count_series(BOI_RATE_SERIES) == len(POINTS)

    def test_repeating_identical_points_changes_nothing(self, db_session):
        """Re-upserting unchanged points is a no-op, not a duplicate insert."""
        repo = InterestRatesRepository(db_session)
        repo.upsert_points(BOI_RATE_SERIES, POINTS)

        assert repo.upsert_points(BOI_RATE_SERIES, POINTS) == 0
        assert repo.count_series(BOI_RATE_SERIES) == len(POINTS)

    def test_changed_value_updates_in_place(self, db_session):
        """A new value for an existing date updates the row and its source."""
        repo = InterestRatesRepository(db_session)
        repo.upsert_points(BOI_RATE_SERIES, POINTS, source="seed")

        changed = repo.upsert_points(
            BOI_RATE_SERIES, [{"date": "2024-06-01", "value": 5.0}], source="fetched"
        )

        assert changed == 1
        assert repo.count_series(BOI_RATE_SERIES) == len(POINTS)
        row = (
            db_session.query(InterestRate)
            .filter_by(series=BOI_RATE_SERIES, date="2024-06-01")
            .one()
        )
        assert row.value == 5.0
        assert row.source == "fetched"


class TestUpsertPointsConcurrency:
    """Tests for concurrent writers hitting the same series/date rows."""

    def test_concurrent_upserts_of_the_same_points_do_not_raise(self, tmp_path):
        """Simultaneous seeding of identical points must not violate the
        unique constraint.

        Regression: seeding is lazy and check-then-act
        (``RatesService.ensure_seeded``), and upsert_points used to
        SELECT-then-INSERT. On a fresh install the Liabilities page fetches
        /rates/current and /rates/history at once; both saw an empty series
        and both inserted the same points, so the loser died on
        ``UNIQUE constraint failed: interest_rates.series, date`` and the
        request 500'd. Schemathesis caught it by fuzzing with 2 workers.
        """
        engine = create_db_engine(str(tmp_path / "rates.db"))
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        workers = 4
        errors: list[Exception] = []
        # The barrier forces the writers to overlap; without it they would
        # serialize and the original race would never be exercised.
        barrier = threading.Barrier(workers)

        def seed() -> None:
            db = Session()
            try:
                barrier.wait()
                InterestRatesRepository(db).upsert_points(BOI_RATE_SERIES, POINTS)
            except Exception as exc:  # noqa: BLE001 - reported via assertion
                errors.append(exc)
            finally:
                db.close()

        threads = [threading.Thread(target=seed) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []

        db = Session()
        try:
            assert InterestRatesRepository(db).count_series(BOI_RATE_SERIES) == len(
                POINTS
            )
        finally:
            db.close()
            engine.dispose()
