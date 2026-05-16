"""Pure file-to-DataFrame parser for the file-import feature.

Given raw bytes + a column mapping, returns a canonical DataFrame with
columns ``date``, ``description``, ``amount`` (and optional ``category``,
``tag``, ``account_number``). No I/O, no DB. Tested in isolation.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal, Optional

import pandas as pd


@dataclass
class FieldMapping:
    """One file → canonical column mapping."""

    column: str
    format: Optional[str] = None  # only used by date mapping


@dataclass
class AmountMapping:
    """Amount field mapping. Supports single-column and split modes.

    Attributes
    ----------
    mode : {"single", "split"}
        ``"single"``: read ``column`` and apply ``sign_convention``.
        ``"split"``: compute ``amount = credit - debit``.
    column : str | None
        Required for single mode.
    sign_convention : {"positive_is_income", "positive_is_expense"} | None
        Required for single mode. ``positive_is_expense`` flips the sign.
    debit_column, credit_column : str | None
        Required for split mode.
    """

    mode: Literal["single", "split"]
    column: Optional[str] = None
    sign_convention: Optional[
        Literal["positive_is_income", "positive_is_expense"]
    ] = None
    debit_column: Optional[str] = None
    credit_column: Optional[str] = None


@dataclass
class ColumnMapping:
    """Full column mapping for one imported account."""

    date: FieldMapping
    description: FieldMapping
    amount: AmountMapping
    skip_rows: int = 0
    category: Optional[FieldMapping] = None
    tag: Optional[FieldMapping] = None
    account_number: Optional[FieldMapping] = None


def parse_file(
    raw: bytes,
    filename: str,
    mapping: ColumnMapping,
) -> pd.DataFrame:
    """Parse ``raw`` bytes into a canonical transaction DataFrame.

    Parameters
    ----------
    raw : bytes
        Raw file bytes from the multipart upload.
    filename : str
        Original filename — its extension picks the reader (``.csv`` vs
        ``.xlsx``).
    mapping : ColumnMapping
        User-defined column mapping (see ``ColumnMapping`` docstring).

    Returns
    -------
    pd.DataFrame
        Columns: ``date`` (str, YYYY-MM-DD), ``description`` (str),
        ``amount`` (float), and any optional columns the mapping enabled.

    Raises
    ------
    ValueError
        If the file type is unsupported, the file can't be decoded, or
        the mapping references a column the file doesn't have.
    """
    raw_df = _read_raw(raw, filename, skip_rows=mapping.skip_rows)
    _check_columns_exist(raw_df, mapping)

    out = pd.DataFrame()
    out["date"] = _parse_dates(raw_df[mapping.date.column], mapping.date.format)
    out["description"] = raw_df[mapping.description.column].astype(str)
    out["amount"] = _compute_amount(raw_df, mapping.amount)

    if mapping.category and mapping.category.column:
        out["category"] = raw_df[mapping.category.column].astype(str)
    if mapping.tag and mapping.tag.column:
        out["tag"] = raw_df[mapping.tag.column].astype(str)
    if mapping.account_number and mapping.account_number.column:
        out["account_number"] = raw_df[mapping.account_number.column].astype(str)

    return out


# ---------- internals ----------

def _read_raw(raw: bytes, filename: str, *, skip_rows: int) -> pd.DataFrame:
    """Decode raw bytes into a header-aware DataFrame."""
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "csv":
        return _read_csv(raw, skip_rows=skip_rows)
    if ext == "xlsx":
        return pd.read_excel(io.BytesIO(raw), skiprows=skip_rows, engine="openpyxl")
    raise ValueError(f"Unsupported file type: .{ext}")


def _read_csv(raw: bytes, *, skip_rows: int) -> pd.DataFrame:
    """Try UTF-8, fall back to Windows-1255 for Hebrew exports."""
    for encoding in ("utf-8", "cp1255"):
        try:
            return pd.read_csv(io.BytesIO(raw), skiprows=skip_rows, encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV as UTF-8 or Windows-1255")


def _check_columns_exist(df: pd.DataFrame, mapping: ColumnMapping) -> None:
    """Raise if any mapped column is missing from the file's header."""
    required = [mapping.date.column, mapping.description.column]
    if mapping.amount.mode == "single":
        required.append(mapping.amount.column)
    else:
        required.append(mapping.amount.debit_column)
        required.append(mapping.amount.credit_column)
    for opt in (mapping.category, mapping.tag, mapping.account_number):
        if opt and opt.column:
            required.append(opt.column)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Mapping references missing column(s): {missing}")


def _parse_dates(series: pd.Series, fmt: Optional[str]) -> pd.Series:
    """Parse a date series to ``YYYY-MM-DD`` strings.

    Task 4 only handles the ``"iso"`` format. Task 5 adds the other
    formats + ``"auto"`` detection.
    """
    if fmt == "iso" or fmt is None:
        parsed = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    else:
        raise NotImplementedError(f"Date format {fmt!r} not implemented yet")
    return parsed.dt.strftime("%Y-%m-%d")


def _compute_amount(df: pd.DataFrame, amount: AmountMapping) -> pd.Series:
    """Compute the canonical signed amount per row."""
    if amount.mode == "single":
        series = pd.to_numeric(df[amount.column], errors="coerce")
        if amount.sign_convention == "positive_is_expense":
            series = -series
        return series
    raise NotImplementedError("split mode lands in Task 5")
