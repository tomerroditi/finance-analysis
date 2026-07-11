"""Tests for the session-scoped DataFrame cache."""

import pandas as pd
from sqlalchemy import text

from backend.utils.session_cache import session_cache_get, session_cache_set


class TestSessionCache:
    """Behavioral tests for session_cache_get / session_cache_set."""

    def test_get_returns_none_on_miss(self, db_session):
        """A key that was never set returns None."""
        assert session_cache_get(db_session, ("missing",)) is None

    def test_set_then_get_returns_equal_frame(self, db_session):
        """A cached frame round-trips with identical contents."""
        df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        session_cache_set(db_session, ("k",), df)
        out = session_cache_get(db_session, ("k",))
        pd.testing.assert_frame_equal(out, df)

    def test_get_returns_a_copy_not_the_stored_object(self, db_session):
        """Mutating the returned frame must not corrupt the cached copy."""
        df = pd.DataFrame({"a": [1, 2]})
        session_cache_set(db_session, ("k",), df)
        first = session_cache_get(db_session, ("k",))
        first["a"] = 999
        second = session_cache_get(db_session, ("k",))
        assert list(second["a"]) == [1, 2]

    def test_set_stores_a_copy_of_the_input(self, db_session):
        """Mutating the input frame after set must not affect the cache."""
        df = pd.DataFrame({"a": [1, 2]})
        session_cache_set(db_session, ("k",), df)
        df["a"] = 999
        out = session_cache_get(db_session, ("k",))
        assert list(out["a"]) == [1, 2]

    def test_commit_clears_cache(self, db_session):
        """Any commit on the session invalidates every cached entry."""
        session_cache_set(db_session, ("k",), pd.DataFrame({"a": [1]}))
        db_session.commit()
        assert session_cache_get(db_session, ("k",)) is None

    def test_rollback_clears_cache(self, db_session):
        """A rollback with an active transaction invalidates every cached entry. In production a rollback always follows failed DB work (transaction active), so the after_rollback event is guaranteed to fire; this test mirrors that by touching the DB before rolling back."""
        session_cache_set(db_session, ("k",), pd.DataFrame({"a": [1]}))
        db_session.execute(text("SELECT 1"))
        db_session.rollback()
        assert session_cache_get(db_session, ("k",)) is None

    def test_distinct_keys_are_independent(self, db_session):
        """Two keys hold two independent frames."""
        session_cache_set(db_session, ("a",), pd.DataFrame({"x": [1]}))
        session_cache_set(db_session, ("b",), pd.DataFrame({"x": [2]}))
        assert session_cache_get(db_session, ("a",))["x"].iloc[0] == 1
        assert session_cache_get(db_session, ("b",))["x"].iloc[0] == 2
