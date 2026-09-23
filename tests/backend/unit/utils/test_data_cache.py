"""Tests for the process-wide, write-versioned derived-read cache."""

import threading
import time

import pytest
from sqlalchemy import Column, Integer, create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.models.base import Base
from backend.utils import data_cache


class _CacheProbe(Base):
    """Throwaway table so a test session has something to write."""

    __tablename__ = "data_cache_probe"
    id = Column(Integer, primary_key=True, autoincrement=True)
    value = Column(Integer)


@pytest.fixture
def file_session(tmp_path):
    """A session backed by a real file, which is what the cache versions on.

    In-memory databases are deliberately never cached (see ``_db_path``), so
    the cache's own tests need a file on disk.
    """
    db_path = tmp_path / "cache.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _CacheProbe.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    data_cache.clear()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        data_cache.clear()


@pytest.fixture
def second_file_session(tmp_path):
    """A session on a *different* file, to prove entries are not shared."""
    db_path = tmp_path / "other.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _CacheProbe.__table__.create(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _Counter:
    """Callable that records how many times it was invoked."""

    def __init__(self, value="computed"):
        self.calls = 0
        self.value = value

    def __call__(self):
        self.calls += 1
        return self.value


class TestCachedHitsAndMisses:
    """The basic reuse contract."""

    def test_first_call_computes(self, file_session):
        """A cold key runs the compute callable and returns its value."""
        compute = _Counter()
        assert data_cache.cached(file_session, ("k",), compute) == "computed"
        assert compute.calls == 1

    def test_second_call_reuses_without_computing(self, file_session):
        """A warm key returns the stored value without recomputing."""
        compute = _Counter()
        data_cache.cached(file_session, ("k",), compute)
        assert data_cache.cached(file_session, ("k",), compute) == "computed"
        assert compute.calls == 1

    def test_distinct_keys_are_independent(self, file_session):
        """Two keys hold two values."""
        data_cache.cached(file_session, ("a",), lambda: "first")
        assert data_cache.cached(file_session, ("b",), lambda: "second") == "second"
        assert data_cache.cached(file_session, ("a",), lambda: "ignored") == "first"

    def test_cached_none_is_a_hit_not_a_miss(self, file_session):
        """A legitimately cached ``None`` must not be mistaken for absence."""
        compute = _Counter(value=None)
        data_cache.cached(file_session, ("k",), compute)
        assert data_cache.cached(file_session, ("k",), compute) is None
        assert compute.calls == 1

    def test_clear_drops_every_entry(self, file_session):
        """``clear()`` forces the next lookup to recompute."""
        compute = _Counter()
        data_cache.cached(file_session, ("k",), compute)
        data_cache.clear()
        data_cache.cached(file_session, ("k",), compute)
        assert compute.calls == 2


class TestInvalidation:
    """What must make a cached answer stop being served."""

    def test_commit_invalidates(self, file_session):
        """A committed write anywhere in the process invalidates the cache."""
        compute = _Counter()
        data_cache.cached(file_session, ("k",), compute)

        file_session.add(_CacheProbe(value=1))
        file_session.commit()

        data_cache.cached(file_session, ("k",), compute)
        assert compute.calls == 2

    def test_rollback_invalidates(self, file_session):
        """A rollback discards in-flight state, so cached reads go too."""
        compute = _Counter()
        data_cache.cached(file_session, ("k",), compute)

        file_session.execute(text("SELECT 1"))
        file_session.rollback()

        data_cache.cached(file_session, ("k",), compute)
        assert compute.calls == 2

    def test_out_of_process_write_invalidates(self, file_session, tmp_path):
        """A foreign connection's commit is caught by the file fingerprint.

        This is the case the in-process write counter cannot see: a second
        dev server, or a restore that swaps the file.
        """
        compute = _Counter()
        data_cache.cached(file_session, ("k",), compute)

        foreign = create_engine(f"sqlite:///{tmp_path / 'cache.db'}")
        with foreign.begin() as conn:
            conn.execute(text("INSERT INTO data_cache_probe (value) VALUES (7)"))
        foreign.dispose()

        data_cache.cached(file_session, ("k",), compute)
        assert compute.calls == 2

    def test_value_built_during_a_write_is_not_stored(self, file_session):
        """A compute that straddles a commit must not publish a stale answer."""

        def compute_then_write():
            file_session.add(_CacheProbe(value=2))
            file_session.commit()
            return "built-across-a-write"

        first = data_cache.cached(file_session, ("k",), compute_then_write)
        assert first == "built-across-a-write"

        # Nothing was cached, so the next lookup computes again.
        follow_up = _Counter(value="fresh")
        assert data_cache.cached(file_session, ("k",), follow_up) == "fresh"
        assert follow_up.calls == 1


class TestIsolation:
    """Entries must never leak across databases or uncommitted views."""

    def test_two_databases_do_not_share_entries(
        self, file_session, second_file_session
    ):
        """Demo and real mode run on one process but must not see each other."""
        data_cache.cached(file_session, ("k",), lambda: "first-db")
        assert (
            data_cache.cached(second_file_session, ("k",), lambda: "second-db")
            == "second-db"
        )
        assert data_cache.cached(file_session, ("k",), lambda: "ignored") == "first-db"

    def test_in_memory_session_is_never_cached(self):
        """An in-memory database has no file identity, so it is not cached."""
        engine = create_engine("sqlite:///:memory:")
        _CacheProbe.__table__.create(engine)
        session = sessionmaker(bind=engine)()
        try:
            compute = _Counter()
            data_cache.cached(session, ("k",), compute)
            data_cache.cached(session, ("k",), compute)
            assert compute.calls == 2
        finally:
            session.close()
            engine.dispose()

    def test_session_with_pending_writes_bypasses_the_cache(self, file_session):
        """An uncommitted view is private and must not be published."""
        data_cache.cached(file_session, ("k",), lambda: "committed-view")

        file_session.add(_CacheProbe(value=3))
        assert (
            data_cache.cached(file_session, ("k",), lambda: "pending-view")
            == "pending-view"
        )
        file_session.rollback()


class TestSingleFlight:
    """Concurrent misses on one key must collapse into one computation."""

    def test_concurrent_misses_compute_once(self, tmp_path):
        """The dashboard's ~25 simultaneous cold requests share one result."""
        db_path = tmp_path / "flight.db"
        engine = create_engine(f"sqlite:///{db_path}")
        _CacheProbe.__table__.create(engine)
        factory = sessionmaker(bind=engine)
        data_cache.clear()

        calls = []
        lock = threading.Lock()

        def slow_compute():
            with lock:
                calls.append(1)
            time.sleep(0.2)
            return "once"

        results = []
        start = threading.Barrier(8)

        def worker():
            start.wait()
            session = factory()
            try:
                results.append(data_cache.cached(session, ("k",), slow_compute))
            finally:
                session.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        engine.dispose()
        data_cache.clear()

        assert len(calls) == 1
        assert results == ["once"] * 8
