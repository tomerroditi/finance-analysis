"""Tests for provider policy-ID normalization and match keys.

The real-world case these guard is HaPhoenix reformatting the parenthesised
internal ID it appends to Keren Hishtalmut policy numbers
(``"007-916-407357 (8296857)"`` -> ``"007-916-407357 (08296857)"``) in
September 2026, which forked a duplicate insurance account, investment and
deposit history for every affected policy.
"""

import pytest

from backend.utils.policy_ids import normalize_policy_id, policy_id_key


class TestNormalizePolicyId:
    """Tests for ``normalize_policy_id``."""

    def test_strips_parenthesised_internal_id(self):
        """Verify the volatile parenthesised suffix is dropped."""
        assert normalize_policy_id("007-916-407357 (8296857)") == "007-916-407357"

    def test_preserves_leading_zeros_of_the_policy_number(self):
        """Verify the displayed policy number keeps the provider's leading zeros."""
        assert normalize_policy_id("007-925-053655 (09527977)").startswith("007-")

    def test_plain_numeric_policy_id_is_unchanged(self):
        """Verify a pension-style bare numeric ID passes through untouched."""
        assert normalize_policy_id("1215029099") == "1215029099"

    def test_trims_surrounding_whitespace(self):
        """Verify padding around the value is removed."""
        assert normalize_policy_id("  1215029099  ") == "1215029099"

    def test_value_that_is_only_a_suffix_is_kept(self):
        """Verify stripping never empties out an otherwise-valid ID."""
        assert normalize_policy_id("(9370165)") == "(9370165)"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_input_returns_empty_string(self, empty):
        """Verify missing values normalize to an empty string, not ``None``."""
        assert normalize_policy_id(empty) == ""


class TestPolicyIdKey:
    """Tests for ``policy_id_key``."""

    def test_both_haphenix_suffix_formats_share_a_key(self):
        """Verify the September 2026 reformat maps onto one key."""
        assert policy_id_key("007-916-407357 (8296857)") == policy_id_key(
            "007-916-407357 (08296857)"
        )

    def test_leading_zeros_in_the_policy_number_are_insignificant(self):
        """Verify a future restyle of the policy number itself still matches."""
        assert policy_id_key("007-916-407357") == policy_id_key("7-916-407357")

    def test_distinct_policies_do_not_collide(self):
        """Verify normalization does not merge genuinely different policies."""
        keys = {
            policy_id_key(p)
            for p in (
                "007-916-407357 (8296857)",
                "007-925-053655 (9527977)",
                "007-926-322907 (9370165)",
                "1215029099",
                "7187793018",
            )
        }
        assert len(keys) == 5

    def test_all_zero_digit_run_survives(self):
        """Verify a segment of only zeros collapses to ``0`` rather than vanishing."""
        assert policy_id_key("000-12") == "0-12"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_empty_input_returns_empty_key(self, empty):
        """Verify missing values produce a falsy key callers can reject."""
        assert policy_id_key(empty) == ""
