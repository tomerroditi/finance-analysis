"""The memoised solve behind the plan page, its card and Calculate.

Solving and advising each search a couple of hundred retirement months, so a
form is solved once per month and its advice added only when asked for.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.fire import projection

FORM = {
    "dateOfBirth": "1990-01-01",
    "base_problem": "retire_at_age",
    "wanted_retire_age": "55",
    "num_expense_fields": "1",
    "expenseSum1": "10000",
    "num_income_fields": "1",
    "incomeSum1": "20000",
}
TODAY = date(2026, 10, 1)


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Count the solves and advice runs behind each call, from an empty cache."""
    projection.clear_cache()
    calls = {"solve": 0, "advise": 0}
    real_solve, real_advise = projection.solve, projection.advise

    def solve(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        calls["solve"] += 1
        return real_solve(*args, **kwargs)

    def advise(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        calls["advise"] += 1
        return real_advise(*args, **kwargs)

    monkeypatch.setattr(projection, "solve", solve)
    monkeypatch.setattr(projection, "advise", advise)
    yield calls
    projection.clear_cache()


class TestProjectionCache:
    """One solve per form and month; advice only on request."""

    def test_same_form_is_solved_once(self, counted: dict[str, int]) -> None:
        """Asking twice for the same form solves it once."""
        first = projection.project(FORM, today=TODAY)
        second = projection.project(dict(FORM), today=TODAY)
        assert second is first
        assert counted == {"solve": 1, "advise": 1}

    def test_advice_is_added_without_solving_again(
        self, counted: dict[str, int]
    ) -> None:
        """The card's answer without advice is reused when the page asks with it."""
        bare = projection.project(FORM, with_advice=False, today=TODAY)
        assert (bare.advised, counted["advise"]) == (False, 0)
        projection.project(FORM, today=TODAY)
        assert counted == {"solve": 1, "advise": 1}

    def test_a_changed_form_is_solved_again(self, counted: dict[str, int]) -> None:
        """Any changed field — here the tracked cash balance — is a new answer."""
        projection.project(FORM, today=TODAY)
        projection.project({**FORM, "balance": "1"}, today=TODAY)
        assert counted["solve"] == 2

    def test_a_new_month_is_solved_again(self, counted: dict[str, int]) -> None:
        """The plan runs from the current month, so a new month is a new answer."""
        projection.project(FORM, today=TODAY)
        projection.project(FORM, today=date(2026, 11, 1))
        assert counted["solve"] == 2
