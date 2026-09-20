"""Tests for the ``YYYY-MM`` formatting helper.

The helper exists to skip a datetime round-trip when the column is already
canonical ``YYYY-MM-DD`` strings (~30x cheaper), so the tests that matter are
the ones proving it falls back correctly whenever it is *not* — a silently
wrong month would corrupt every monthly aggregate on the dashboard.
"""

import pandas as pd

from backend.utils.dataframe_dates import to_month_series


def _reference(dates: pd.Series) -> pd.Series:
    """The datetime round-trip this helper replaces."""
    return pd.to_datetime(dates, errors="coerce").dt.strftime("%Y-%m")


def _same(left: pd.Series, right: pd.Series) -> bool:
    """Compare two month series, treating nulls as equal."""
    return list(left.fillna("<NA>")) == list(right.fillna("<NA>"))


class TestToMonthSeriesFastPath:
    """Canonical strings take the slice, and it must be the right slice."""

    def test_canonical_strings_are_formatted(self):
        """A normalized date column yields its year and month."""
        dates = pd.Series(["2024-01-05", "2024-12-31", "2023-06-15"])

        assert list(to_month_series(dates)) == ["2024-01", "2024-12", "2023-06"]

    def test_matches_the_datetime_round_trip(self):
        """The fast path agrees with the implementation it replaces."""
        dates = pd.Series([f"2024-{m:02d}-{d:02d}" for m in range(1, 13) for d in (1, 28)])

        assert _same(to_month_series(dates), _reference(dates))

    def test_year_boundary_is_not_off_by_one(self):
        """December 31st stays in December, January 1st in January."""
        dates = pd.Series(["2023-12-31", "2024-01-01"])

        assert list(to_month_series(dates)) == ["2023-12", "2024-01"]

    def test_nulls_are_preserved(self):
        """A row the repository could not date stays null, not ``"NaN-Na"``."""
        dates = pd.Series(["2024-03-01", None, "2024-04-02"])

        result = to_month_series(dates)

        assert result.isna().tolist() == [False, True, False]
        assert _same(result, _reference(dates))


class TestToMonthSeriesFallback:
    """Anything not canonical must go through pandas, not a blind slice."""

    def test_datetime_column_falls_back(self):
        """A parsed datetime column has no string to slice."""
        dates = pd.to_datetime(pd.Series(["2024-01-05", "2024-02-06"]))

        assert list(to_month_series(dates)) == ["2024-01", "2024-02"]

    def test_non_canonical_strings_fall_back(self):
        """Slashes would slice to ``"2024/03"`` — the check must catch it."""
        dates = pd.Series(["2024/03/01", "2024/04/01"])

        result = to_month_series(dates)

        assert list(result) == ["2024-03", "2024-04"]
        assert _same(result, _reference(dates))

    def test_one_bad_value_forces_the_whole_column_to_fall_back(self):
        """The validation is all-or-nothing, so a mixed column stays correct."""
        dates = pd.Series(["2024-03-01", "March 4 2024"])

        assert _same(to_month_series(dates), _reference(dates))

    def test_unparseable_value_becomes_null(self):
        """A value neither path can read is null, matching the old behaviour."""
        dates = pd.Series(["2024-03-01", "not a date at all"])

        result = to_month_series(dates)

        assert result.iloc[0] == "2024-03"
        assert pd.isna(result.iloc[1])


class TestToMonthSeriesEdges:
    """Degenerate inputs must not raise."""

    def test_empty_series(self):
        """An empty column yields an empty result."""
        assert len(to_month_series(pd.Series([], dtype=object))) == 0

    def test_all_null_series(self):
        """A column of nothing but nulls stays all null."""
        result = to_month_series(pd.Series([None, None], dtype=object))

        assert result.isna().all()

    def test_index_is_preserved(self):
        """Callers assign the result back onto a filtered frame."""
        dates = pd.Series(["2024-01-05", "2024-02-06"], index=[7, 9])

        assert list(to_month_series(dates).index) == [7, 9]
