"""Unit tests for the pure file-import parser."""

from pathlib import Path

import pytest

from backend.services.file_import_parser import (
    AmountMapping,
    ColumnMapping,
    FieldMapping,
    parse_file,
)

FIXTURES = Path(__file__).parent / "fixtures" / "imports"


def _signed_mapping(skip_rows: int = 0) -> ColumnMapping:
    """Helper to build a basic single-signed-amount mapping."""
    return ColumnMapping(
        skip_rows=skip_rows,
        date=FieldMapping(column="date", format="iso"),
        description=FieldMapping(column="description"),
        amount=AmountMapping(
            mode="single",
            column="amount",
            sign_convention="positive_is_income",
        ),
    )


class TestParseSimpleSignedCsv:
    """Parsing a UTF-8 CSV with one signed amount column."""

    def test_csv_basic(self):
        """All 4 rows parse with correct types and order."""
        raw = (FIXTURES / "simple_signed.csv").read_bytes()
        df = parse_file(raw, filename="simple_signed.csv", mapping=_signed_mapping())
        assert len(df) == 4
        assert list(df.columns) == ["date", "description", "amount"]
        assert df.iloc[0]["date"] == "2026-03-01"
        assert df.iloc[0]["description"] == "Coffee shop"
        assert df.iloc[0]["amount"] == -12.50
        assert df.iloc[1]["amount"] == 8500.00

    def test_csv_with_banner_rows(self):
        """skip_rows skips banner lines above the header."""
        raw = (FIXTURES / "simple_signed_with_banner.csv").read_bytes()
        df = parse_file(
            raw,
            filename="simple_signed_with_banner.csv",
            mapping=_signed_mapping(skip_rows=4),
        )
        assert len(df) == 2
        assert df.iloc[0]["description"] == "Coffee shop"

    def test_sign_flip_positive_is_expense(self):
        """When user picks positive_is_expense, signs invert."""
        mapping = _signed_mapping()
        mapping.amount.sign_convention = "positive_is_expense"
        raw = (FIXTURES / "simple_signed.csv").read_bytes()
        df = parse_file(raw, filename="simple_signed.csv", mapping=mapping)
        assert df.iloc[0]["amount"] == 12.50
        assert df.iloc[1]["amount"] == -8500.00

    def test_xlsx_basic(self):
        """An xlsx file parses with the same mapping shape."""
        raw = (FIXTURES / "simple_signed.xlsx").read_bytes()
        df = parse_file(raw, filename="simple_signed.xlsx", mapping=_signed_mapping())
        assert len(df) == 3
        assert df.iloc[0]["description"] == "Coffee shop"
        assert df.iloc[0]["amount"] == -12.50


class TestEncodingFallback:
    """Windows-1255 (Hebrew) fallback when UTF-8 decode fails."""

    def test_cp1255_csv_falls_back(self, tmp_path):
        """A file written in CP1255 with Hebrew columns still parses."""
        path = tmp_path / "cp1255.csv"
        hebrew_header = "תאריך,תיאור,סכום\n"
        rows = "2026-03-01,קפה,-12.50\n2026-03-03,משכורת,8500.00\n"
        path.write_bytes((hebrew_header + rows).encode("cp1255"))

        mapping = ColumnMapping(
            skip_rows=0,
            date=FieldMapping(column="תאריך", format="iso"),
            description=FieldMapping(column="תיאור"),
            amount=AmountMapping(
                mode="single",
                column="סכום",
                sign_convention="positive_is_income",
            ),
        )
        df = parse_file(path.read_bytes(), filename="cp1255.csv", mapping=mapping)
        assert len(df) == 2
        assert df.iloc[0]["description"] == "קפה"
        assert df.iloc[0]["amount"] == -12.50


class TestParseFileValidation:
    """Error cases for parse_file."""

    def test_unknown_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_file(b"x,y\n1,2\n", filename="foo.txt", mapping=_signed_mapping())

    def test_missing_required_column_raises(self):
        """If the mapping references a column the file doesn't have, raise."""
        raw = (FIXTURES / "simple_signed.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.description.column = "doesnotexist"
        with pytest.raises(ValueError, match="doesnotexist"):
            parse_file(raw, filename="simple_signed.csv", mapping=mapping)
