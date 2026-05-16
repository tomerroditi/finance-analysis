"""Unit tests for the pure file-import parser."""

from pathlib import Path

import pytest

from backend.services.file_import_parser import (
    AmountMapping,
    ColumnMapping,
    FieldMapping,
    parse_file,
    parse_file_with_summary,
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
        """Unknown file extensions raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_file(b"x,y\n1,2\n", filename="foo.txt", mapping=_signed_mapping())

    def test_missing_required_column_raises(self):
        """If the mapping references a column the file doesn't have, raise."""
        raw = (FIXTURES / "simple_signed.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.description.column = "doesnotexist"
        with pytest.raises(ValueError, match="doesnotexist"):
            parse_file(raw, filename="simple_signed.csv", mapping=mapping)

    def test_missing_date_format_raises(self):
        """date.format=None raises ValueError so callers don't get silent ISO parsing."""
        raw = (FIXTURES / "simple_signed.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.date.format = None
        with pytest.raises(ValueError, match="date.format is required"):
            parse_file(raw, filename="simple_signed.csv", mapping=mapping)


class TestSplitMode:
    """Debit/credit split amount mode."""

    def test_hapoalim_style(self):
        """CP1255 file with banner rows, Hebrew headers, debit/credit columns."""
        raw = (FIXTURES / "hapoalim_style.csv").read_bytes()
        mapping = ColumnMapping(
            skip_rows=2,
            date=FieldMapping(column="תאריך", format="dd/mm/yyyy"),
            description=FieldMapping(column="תיאור"),
            amount=AmountMapping(
                mode="split",
                debit_column="חובה",
                credit_column="זכות",
            ),
        )
        df, dropped = parse_file_with_summary(
            raw, filename="hapoalim_style.csv", mapping=mapping
        )
        assert dropped == 0
        assert len(df) == 3
        # Coffee: debit 12.50 → amount = 0 - 12.50 = -12.50
        assert df.iloc[0]["amount"] == -12.50
        # Salary: credit 8500 → amount = 8500 - 0 = 8500.00
        assert df.iloc[1]["amount"] == 8500.00
        # Gym: debit 180 → -180.00
        assert df.iloc[2]["amount"] == -180.00
        # Dates converted to ISO
        assert df.iloc[0]["date"] == "2026-03-01"


class TestDateFormats:
    """Non-ISO date formats and auto-detect."""

    def test_dd_mm_yyyy(self):
        """01/03/2026 reads as 1 March, not 3 January."""
        raw = (FIXTURES / "dd_mm_yyyy.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.date.format = "dd/mm/yyyy"
        df, dropped = parse_file_with_summary(
            raw, filename="dd_mm_yyyy.csv", mapping=mapping
        )
        # 3 input rows; 1 has a non-numeric amount → dropped.
        assert dropped == 1
        assert len(df) == 2
        assert df.iloc[0]["date"] == "2026-03-01"

    def test_auto_detect(self):
        """`format='auto'` detects DD/MM from the sample rows."""
        raw = (FIXTURES / "dd_mm_yyyy.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.date.format = "auto"
        df, dropped = parse_file_with_summary(
            raw, filename="dd_mm_yyyy.csv", mapping=mapping
        )
        assert dropped == 1
        assert df.iloc[0]["date"] == "2026-03-01"

    def test_excel_serial(self):
        """Excel serial dates (e.g., 45731 = 2025-03-15) parse correctly."""
        import pandas as pd_local
        df_xl = pd_local.DataFrame({
            "date": [45731, 45733],
            "description": ["A", "B"],
            "amount": [-1, -2],
        })
        path = FIXTURES / "excel_serial.xlsx"
        df_xl.to_excel(path, index=False)
        raw = path.read_bytes()
        mapping = _signed_mapping()
        mapping.date.format = "excel_serial"
        df, dropped = parse_file_with_summary(raw, filename=str(path), mapping=mapping)
        assert dropped == 0
        # 1899-12-30 + 45731 days = 2025-03-15
        assert df.iloc[0]["date"] == "2025-03-15"


class TestRowValidation:
    """Drop-invalid behaviour."""

    def test_drops_unparseable_amount(self):
        """Non-numeric amount rows are silently dropped and counted."""
        raw = (FIXTURES / "dd_mm_yyyy.csv").read_bytes()
        mapping = _signed_mapping()
        mapping.date.format = "dd/mm/yyyy"
        df, dropped = parse_file_with_summary(
            raw, filename="dd_mm_yyyy.csv", mapping=mapping
        )
        assert dropped == 1
        assert "foo" not in df["description"].values
