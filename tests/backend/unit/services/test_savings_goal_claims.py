"""Unit tests for the savings-goal claim rules (``savings_goals.claims``)."""

import pandas as pd

from backend.models.savings_goal import (
    GOAL_STATUS_CLOSED,
    LINK_CONTRIBUTION,
    LINK_UTILIZATION,
    SavingsGoal,
)
from backend.services.savings_goals.claims import (
    claim_span,
    goals_owning_income,
    in_span,
    rule_mask,
    rules_overlap,
)


class TestRuleMask:
    """A rule matches rows the way a budget rule does."""

    def test_no_tags_or_all_tags_match_every_tag(self):
        """Without a tag narrowing, every row of the category matches."""
        df = pd.DataFrame(
            {"category": ["Travel", "Travel", "Food"], "tag": ["a", "b", "a"]}
        )

        assert rule_mask(df, "Travel", None).tolist() == [True, True, False]
        assert rule_mask(df, "Travel", "all_tags").tolist() == [True, True, False]

    def test_tags_narrow_the_category(self):
        """Semicolon-separated tags keep only the rows carrying one of them."""
        df = pd.DataFrame(
            {"category": ["Travel", "Travel", "Travel"], "tag": ["a", "b", "c"]}
        )

        assert rule_mask(df, "Travel", "a; c").tolist() == [True, False, True]


class TestRulesOverlap:
    """Two saved-into rules overlap when one row could match both."""

    def test_different_categories_never_overlap(self):
        """A category mismatch rules out any overlap."""
        assert not rules_overlap(("Gifts", None), ("Salary", None))

    def test_an_untagged_rule_overlaps_any_rule_on_its_category(self):
        """Every tag of the category is claimed by the untagged rule."""
        assert rules_overlap(("Gifts", None), ("Gifts", "Wedding"))

    def test_tagged_rules_overlap_only_on_a_shared_tag(self):
        """Disjoint tag sets on one category can coexist."""
        assert rules_overlap(("Gifts", "a;b"), ("Gifts", "b"))
        assert not rules_overlap(("Gifts", "a"), ("Gifts", "b"))


class TestClaimSpan:
    """A goal claims rows from its start month through the month it closed."""

    def test_an_open_goal_claims_from_its_start_on(self):
        """No closing month means no upper bound."""
        span = claim_span(SavingsGoal(start_month="2026-03", status="active"))

        assert not in_span((2026, 2), span)
        assert in_span((2030, 1), span)

    def test_a_closed_goal_stops_at_its_closing_month(self):
        """The closing month is still claimed, the month after is not."""
        goal = SavingsGoal(
            start_month="2026-01", status=GOAL_STATUS_CLOSED, closed_month="2026-05"
        )
        span = claim_span(goal)

        assert in_span((2026, 5), span)
        assert not in_span((2026, 6), span)


class TestGoalsOwningIncome:
    """A rule or a single claimed income makes a goal own income."""

    def test_a_saved_into_rule_or_an_income_link_owns_income(self):
        """Spending links alone do not."""
        goals = [
            SavingsGoal(id=1, contribution_category="Gifts"),
            SavingsGoal(id=2),
            SavingsGoal(id=3),
        ]
        claimed = [(2, LINK_CONTRIBUTION), (3, LINK_UTILIZATION)]

        assert goals_owning_income(goals, claimed) == {1, 2}
