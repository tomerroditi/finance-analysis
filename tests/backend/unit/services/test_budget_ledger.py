"""Tests for the budget claim ledger — pure, on hand-built frames."""

import pandas as pd
import pytest

from backend.services.budget.ledger import (
    BUDGET_MONTH,
    BUDGET_YEAR,
    CLAIM_KIND,
    CLAIM_RULE_ID,
    KIND_MONTHLY,
    KIND_OTHER,
    KIND_PROJECT,
    KIND_YEARLY,
    MONTHLY_POOL,
    assign_claims,
    in_budget_month,
    is_all_tags,
    of_kind,
    of_rule,
    spent,
)

NO_OVERRIDES: dict = {"transaction": {}, "split": {}}


def _rows(*rows: tuple) -> pd.DataFrame:
    """Build expense rows from ``(date, category, tag, amount)`` tuples."""
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(date),
                "category": category,
                "tag": tag,
                "amount": amount,
                "source": "credit_card_transactions",
                "unique_id": index + 1,
            }
            for index, (date, category, tag, amount) in enumerate(rows)
        ]
    )


def _rule(
    id_: int,
    period: str,
    category: str,
    tags: list[str],
    year: int | None = None,
    month: int | None = None,
    amount: float = 100.0,
) -> dict:
    """Build one budget rule row."""
    return {
        "id": id_,
        "name": f"rule {id_}",
        "amount": amount,
        "category": category,
        "tags": tags,
        "year": year,
        "month": month,
        "period_type": period,
    }


def _rules(*rules: dict) -> pd.DataFrame:
    """Build a rules frame."""
    return pd.DataFrame(list(rules))


class TestPrecedence:
    """One owner per row: project, then yearly, then monthly, then other."""

    def test_project_category_beats_every_rule(self) -> None:
        """A project category is the project's even where other rules would match."""
        claims = assign_claims(
            _rows(("2026-03-05", "Wedding", "Venue", -500.0)),
            _rules(
                _rule(1, "project", "Wedding", ["all_tags"]),
                _rule(2, "yearly", "Wedding", ["all_tags"], year=2026),
                _rule(3, "monthly", "Wedding", ["all_tags"], 2026, 3),
            ),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_PROJECT]

    def test_yearly_beats_monthly_and_monthly_beats_other(self) -> None:
        """Yearly claims its tag; a monthly rule takes the rest; the remainder is other."""
        claims = assign_claims(
            _rows(
                ("2026-03-05", "Home", "Insurance", -1200.0),
                ("2026-03-06", "Home", "Repairs", -300.0),
                ("2026-03-07", "Fun", "Movies", -50.0),
            ),
            _rules(
                _rule(1, "yearly", "Home", ["Insurance"], year=2026),
                _rule(2, "monthly", "Home", ["all_tags"], 2026, 3),
            ),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_YEARLY, KIND_MONTHLY, KIND_OTHER]
        assert claims[CLAIM_RULE_ID].tolist() == [1, 2, pd.NA]

    def test_unbudgeted_month_is_other(self) -> None:
        """A month with no rules at all still owns its spend, as other."""
        claims = assign_claims(
            _rows(("2026-04-05", "Food", "Groceries", -80.0)),
            _rules(_rule(1, "monthly", "Food", ["all_tags"], 2026, 3)),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_OTHER]

    def test_total_budget_never_claims(self) -> None:
        """The Total Budget row is a cap over the pool, not a claimant."""
        claims = assign_claims(
            _rows(("2026-03-05", "Food", "Groceries", -80.0)),
            _rules(_rule(1, "monthly", "Total Budget", ["all_tags"], 2026, 3)),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_OTHER]


class TestSpecificity:
    """Within a kind the most specific rule claims first."""

    def test_fewer_tags_beat_more_and_all_tags_takes_leftovers(self) -> None:
        """A one-tag rule beats a two-tag rule; all-tags only gets the rest."""
        claims = assign_claims(
            _rows(
                ("2026-03-01", "Food", "Coffee", -10.0),
                ("2026-03-02", "Food", "Lunch", -40.0),
                ("2026-03-03", "Food", "Snacks", -5.0),
            ),
            _rules(
                _rule(1, "monthly", "Food", ["all_tags"], 2026, 3),
                _rule(2, "monthly", "Food", ["Coffee", "Lunch"], 2026, 3),
                _rule(3, "monthly", "Food", ["Coffee"], 2026, 3),
            ),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_RULE_ID].tolist() == [3, 2, 1]

    def test_project_tag_named_by_two_rules_counts_once(self) -> None:
        """A tag two project rules name belongs to the narrower one only."""
        claims = assign_claims(
            _rows(("2026-03-01", "Wedding", "Venue", -900.0)),
            _rules(
                _rule(1, "project", "Wedding", ["all_tags"]),
                _rule(2, "project", "Wedding", ["Venue", "Food"]),
                _rule(3, "project", "Wedding", ["Venue"]),
            ),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_RULE_ID].tolist() == [3]

    def test_project_row_with_no_tag_rule_has_no_rule_id(self) -> None:
        """The anchor is the project's total, never a row's claimant."""
        claims = assign_claims(
            _rows(("2026-03-01", "Wedding", "Flowers", -90.0)),
            _rules(_rule(1, "project", "Wedding", ["all_tags"])),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_PROJECT]
        assert claims[CLAIM_RULE_ID].isna().all()

    def test_legacy_mixed_case_all_tags(self) -> None:
        """``All Tags`` stored in mixed case is still the sentinel."""
        assert is_all_tags(["All_Tags"])
        assert is_all_tags("ALL_TAGS")
        assert not is_all_tags(["Coffee"])
        assert not is_all_tags([])


class TestBudgetMonth:
    """One budget month per row, and every pool reads it."""

    def test_override_moves_row_and_its_yearly_claim(self) -> None:
        """A December purchase moved into January is January's — yearly year included."""
        rows = _rows(("2025-12-30", "Home", "Insurance", -1200.0))
        overrides = {
            "transaction": {("credit_card_transactions", 1): (2026, 1)},
            "split": {},
        }
        claims = assign_claims(
            rows,
            _rules(
                _rule(1, "yearly", "Home", ["Insurance"], year=2025),
                _rule(2, "yearly", "Home", ["Insurance"], year=2026),
            ),
            overrides,
        )
        assert (claims[BUDGET_YEAR].iloc[0], claims[BUDGET_MONTH].iloc[0]) == (2026, 1)
        assert claims[CLAIM_RULE_ID].tolist() == [2]

    def test_split_override_wins_over_transaction_override(self) -> None:
        """A split's own override beats its parent transaction's."""
        rows = _rows(("2026-03-01", "Food", "Lunch", -40.0))
        rows["split_id"] = [7]
        overrides = {
            "transaction": {("credit_card_transactions", 1): (2026, 4)},
            "split": {7: (2026, 5)},
        }
        claims = assign_claims(rows, _rules(), overrides)
        assert claims[BUDGET_MONTH].tolist() == [5]

    def test_yearly_rule_never_claims_another_year(self) -> None:
        """A 2026 envelope leaves 2025 spend alone."""
        claims = assign_claims(
            _rows(("2025-06-01", "Home", "Insurance", -1200.0)),
            _rules(_rule(1, "yearly", "Home", ["Insurance"], year=2026)),
            NO_OVERRIDES,
        )
        assert claims[CLAIM_KIND].tolist() == [KIND_OTHER]


class TestInvariants:
    """The pools are disjoint and add up to everything spent."""

    @pytest.fixture
    def claims(self) -> pd.DataFrame:
        """A month touching every pool, plus a neighbouring month."""
        return assign_claims(
            _rows(
                ("2026-03-01", "Wedding", "Venue", -900.0),
                ("2026-03-02", "Home", "Insurance", -1200.0),
                ("2026-03-03", "Food", "Coffee", -10.0),
                ("2026-03-04", "Food", "Lunch", -40.0),
                ("2026-03-05", "Fun", "Movies", -50.0),
                ("2026-03-06", "Food", "Coffee", 4.0),
                ("2026-04-01", "Food", "Coffee", -12.0),
            ),
            _rules(
                _rule(1, "project", "Wedding", ["all_tags"]),
                _rule(2, "yearly", "Home", ["all_tags"], year=2026),
                _rule(3, "monthly", "Food", ["Coffee"], 2026, 3),
                _rule(4, "monthly", "Food", ["all_tags"], 2026, 3),
                _rule(5, "monthly", "Total Budget", ["all_tags"], 2026, 3),
            ),
            NO_OVERRIDES,
        )

    def test_pools_sum_to_the_month(self, claims: pd.DataFrame) -> None:
        """Monthly pool + yearly + project == every row of the budget month."""
        month = in_budget_month(claims, 2026, 3)
        pools = (
            spent(of_kind(month, *MONTHLY_POOL))
            + spent(of_kind(month, KIND_YEARLY))
            + spent(of_kind(month, KIND_PROJECT))
        )
        assert pools == pytest.approx(spent(month))
        assert spent(month) == pytest.approx(2196.0)

    def test_every_row_has_exactly_one_kind(self, claims: pd.DataFrame) -> None:
        """No row is unclaimed and none is claimed twice."""
        kinds = [KIND_PROJECT, KIND_YEARLY, KIND_MONTHLY, KIND_OTHER]
        assert sum(len(of_kind(claims, kind)) for kind in kinds) == len(claims)

    def test_rule_rows_partition_the_monthly_kind(self, claims: pd.DataFrame) -> None:
        """Each monthly row belongs to one rule, and refunds net inside it."""
        assert spent(of_rule(claims, 3)) == pytest.approx(6.0)
        assert spent(of_rule(claims, 4)) == pytest.approx(40.0)
        assert of_rule(claims, 5).empty

    def test_empty_frame_keeps_its_columns(self) -> None:
        """An empty input still carries the claim columns."""
        claims = assign_claims(_rows(), _rules(), NO_OVERRIDES)
        assert claims.empty
        assert {BUDGET_YEAR, BUDGET_MONTH, CLAIM_KIND, CLAIM_RULE_ID} <= set(
            claims.columns
        )
