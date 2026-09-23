"""
Unit tests for text_utils module.
"""

import pytest

from backend.utils.text_utils import INITIALISMS, to_title_case


class TestToTitleCase:
    """Tests for the to_title_case function."""

    def test_none_input(self):
        """None input should return None."""
        assert to_title_case(None) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("", "", id="empty"),
            pytest.param("   ", "   ", id="whitespace_only"),
            pytest.param("hello world", "Hello World", id="lowercase"),
            pytest.param("HELLO WORLD", "Hello World", id="uppercase"),
            pytest.param("hElLo WoRlD", "Hello World", id="mixed_case"),
            pytest.param("Hello World", "Hello World", id="already_title"),
            pytest.param("atm withdrawal", "ATM Withdrawal", id="initialism_lower"),
            pytest.param("Atm", "ATM", id="initialism_capitalized"),
            pytest.param("ATM", "ATM", id="initialism_upper"),
            pytest.param("chat gpt subscription", "Chat GPT Subscription", id="initialism_mid"),
            pytest.param("usa atm fee", "USA ATM Fee", id="multiple_initialisms"),
            pytest.param("home-improvement", "Home-Improvement", id="hyphenated"),
            pytest.param("chat-gpt", "Chat-GPT", id="hyphenated_initialism"),
            pytest.param("CHAT-GPT", "Chat-GPT", id="hyphenated_initialism_upper"),
            pytest.param("hello  world", "Hello  World", id="multiple_spaces"),
            pytest.param(" hello world ", " Hello World ", id="leading_trailing_spaces"),
            pytest.param("credit card bill", "Credit Card Bill", id="real_category"),
        ],
    )
    def test_casing(self, raw, expected):
        """Words are title-cased per space/hyphen segment, initialisms stay upper,
        and whitespace is preserved exactly."""
        assert to_title_case(raw) == expected

    def test_all_initialisms_recognized(self):
        """All defined initialisms should be recognized."""
        for initialism in INITIALISMS:
            result = to_title_case(initialism.lower())
            assert result == initialism, f"Expected {initialism}, got {result}"
