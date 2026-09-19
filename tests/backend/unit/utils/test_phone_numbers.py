"""Tests for Israeli mobile-number normalization."""

import pytest

from backend.utils.phone_numbers import normalize_israeli_mobile


class TestNormalizeIsraeliMobile:
    """``normalize_israeli_mobile`` maps every common spelling to E.164."""

    @pytest.mark.parametrize(
        "raw",
        [
            "0501234567",
            "050-1234567",
            "501234567",
            "972501234567",
            "+972501234567",
            "+972 50-123-4567",
            "+972-050-1234567",
            "(050) 123 4567",
        ],
    )
    def test_recognised_forms(self, raw):
        """Local, bare and international spellings all normalize to +9725…."""
        assert normalize_israeli_mobile(raw) == "+972501234567"

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("+15551234567", "+15551234567"),
            ("02-1234567", "021234567"),
            ("05012", "05012"),
            ("", ""),
        ],
    )
    def test_unrecognised_forms_pass_through(self, raw, expected):
        """Foreign, landline and truncated numbers only lose separators."""
        assert normalize_israeli_mobile(raw) == expected
