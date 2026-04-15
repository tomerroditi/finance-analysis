"""
Unit tests for text_utils module.
"""


from backend.utils.text_utils import INITIALISMS, to_title_case


class TestToTitleCase:
    """Tests for the to_title_case function."""

    def test_none_input(self):
        """None input should return None."""
        assert to_title_case(None) is None

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert to_title_case("") == ""

    def test_whitespace_only(self):
        """Whitespace-only string should be preserved."""
        assert to_title_case("   ") == "   "

    def test_basic_lowercase(self):
        """Lowercase words should be title-cased."""
        assert to_title_case("hello world") == "Hello World"

    def test_all_uppercase(self):
        """Uppercase words should be title-cased (unless initialism)."""
        assert to_title_case("HELLO WORLD") == "Hello World"

    def test_mixed_case(self):
        """Mixed case should be normalized to title case."""
        assert to_title_case("hElLo WoRlD") == "Hello World"

    def test_already_title_case(self):
        """Already title-cased strings should remain unchanged."""
        assert to_title_case("Hello World") == "Hello World"

    def test_single_word(self):
        """Single word should be capitalized."""
        assert to_title_case("groceries") == "Groceries"

    def test_preserves_atm_initialism(self):
        """ATM initialism should be preserved in uppercase."""
        assert to_title_case("atm withdrawal") == "ATM Withdrawal"
        assert to_title_case("Atm") == "ATM"
        assert to_title_case("ATM") == "ATM"

    def test_preserves_dj_initialism(self):
        """DJ initialism should be preserved."""
        assert to_title_case("dj music") == "DJ Music"
        assert to_title_case("Dj") == "DJ"

    def test_preserves_gpt_initialism(self):
        """GPT initialism should be preserved."""
        assert to_title_case("chat gpt subscription") == "Chat GPT Subscription"

    def test_preserves_btb_initialism(self):
        """BTB initialism should be preserved."""
        assert to_title_case("btb investment") == "BTB Investment"

    def test_hyphenated_word_basic(self):
        """Hyphenated words should be title-cased per segment."""
        assert to_title_case("first-degree") == "First-Degree"
        assert to_title_case("home-improvement") == "Home-Improvement"

    def test_hyphenated_word_with_initialism(self):
        """Hyphenated words with initialisms should handle both."""
        assert to_title_case("chat-gpt") == "Chat-GPT"
        assert to_title_case("Chat-Gpt") == "Chat-GPT"
        assert to_title_case("CHAT-GPT") == "Chat-GPT"

    def test_multiple_initialisms(self):
        """Multiple initialisms in one string should all be preserved."""
        assert to_title_case("usa atm fee") == "USA ATM Fee"

    def test_preserves_multiple_spaces(self):
        """Multiple consecutive spaces should be preserved."""
        assert to_title_case("hello  world") == "Hello  World"

    def test_leading_trailing_spaces(self):
        """Leading and trailing spaces should be preserved."""
        assert to_title_case(" hello world ") == " Hello World "

    def test_real_world_categories(self):
        """Test with real category/tag names from the application."""
        assert to_title_case("bank commisions") == "Bank Commisions"
        assert to_title_case("credit card bill") == "Credit Card Bill"
        assert to_title_case("internal transactions") == "Internal Transactions"
        assert to_title_case("other income") == "Other Income"

    def test_real_world_tags_with_issues(self):
        """Test tags that currently have casing issues."""
        assert to_title_case("weddings") == "Weddings"
        assert to_title_case("other") == "Other"
        assert to_title_case("jewelries") == "Jewelries"
        assert to_title_case("tabaco") == "Tabaco"

    def test_all_initialisms_recognized(self):
        """All defined initialisms should be recognized."""
        for initialism in INITIALISMS:
            result = to_title_case(initialism.lower())
            assert result == initialism, f"Expected {initialism}, got {result}"
