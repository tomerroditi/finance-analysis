"""Tests for the log-value scrubber.

Guards CWE-117 (log injection). Values that reach a log line here include
user-chosen account names and, more importantly, provider response text —
genuinely external input. A newline in either forges what looks like a
separate, legitimate log entry, which matters because these logs are what
someone pastes into a bug report.
"""

import pytest

from backend.utils.log_sanitize import scrub


class TestScrubNeutralisesLineBreaks:
    """Line and record separators must not survive into a log line."""

    @pytest.mark.parametrize(
        "raw",
        [
            "ok\nFAKE 2026-01-01 ERROR forged entry",
            "ok\rFAKE",
            "ok\r\nFAKE",
            "ok\x0bFAKE",
            "ok\x0cFAKE",
            "ok FAKE",
            "ok FAKE",
            "ok\x85FAKE",
        ],
    )
    def test_break_characters_are_replaced(self, raw):
        """Verify no character that starts a new log line survives."""
        out = scrub(raw)
        for ch in "\n\r\x0b\x0c\x85  ":
            assert ch not in out

    def test_crlf_collapses_to_one_marker(self):
        """Verify a CRLF pair does not become two markers."""
        assert scrub("a\r\nb") == "a\\nb"

    def test_visible_marker_is_used(self):
        """Verify removal is visible, so truncation cannot be silent."""
        assert scrub("a\nb") == "a\\nb"


class TestScrubStripsControlCharacters:
    """Terminal control sequences must not reach a log."""

    def test_ansi_escape_is_removed(self):
        """Verify an ESC byte cannot inject terminal colour codes."""
        assert "\x1b" not in scrub("\x1b[31mred")

    def test_null_byte_is_removed(self):
        """Verify a NUL byte is stripped rather than truncating the line."""
        assert "\x00" not in scrub("a\x00b")

    def test_tab_is_preserved(self):
        """Verify tabs survive — they are legitimate log content."""
        assert scrub("a\tb") == "a\tb"


class TestScrubPreservesOrdinaryValues:
    """The common path must not damage legitimate data."""

    def test_plain_text_is_unchanged(self):
        """Verify an ordinary account name passes through untouched."""
        assert scrub("Main Account") == "Main Account"

    def test_hebrew_is_unchanged(self):
        """Verify non-ASCII text is not mangled — provider text is Hebrew."""
        assert scrub("חשבון עיקרי") == "חשבון עיקרי"

    def test_non_string_is_coerced(self):
        """Verify non-string values are rendered rather than raising."""
        assert scrub(42) == "42"
        assert scrub(None) == "None"

    def test_object_with_hostile_repr_is_scrubbed(self):
        """Verify coercion happens before scrubbing, not after."""

        class Hostile:
            def __str__(self):
                return "a\nFAKE"

        assert "\n" not in scrub(Hostile())


class TestScrubCapsLength:
    """A single value must not be able to flood the log."""

    def test_long_value_is_truncated_with_a_marker(self):
        """Verify an oversized value is cut and the cut is visible."""
        out = scrub("x" * 5000)
        assert len(out) < 5000
        assert out.endswith("…[truncated]")

    def test_value_at_the_limit_is_untouched(self):
        """Verify the cap does not fire on a value that just fits."""
        raw = "x" * 512
        assert scrub(raw) == raw
