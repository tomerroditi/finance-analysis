# File Import for Transactions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a CSV/XLSX file-import data source to the Data Sources page, with a persistent column mapping per account so users map once and reupload silently.

**Architecture:** New `imported_accounts` table tracks file-based accounts; imported transactions land in the existing `bank_transactions` / `credit_card_transactions` / `cash_transactions` tables. A pure parser turns raw bytes + mapping → canonical DataFrame; the service layer adds dedup, auto-tagging, and cash-balance recalc on insert. Frontend grows a new wizard alongside the existing "Connect Account" flow and merges the two account lists for display.

**Tech Stack:** FastAPI / SQLAlchemy 2 / pandas + openpyxl (backend); React 19 / TanStack Query / Tailwind 4 (frontend); pytest + Playwright (tests).

**Spec:** `docs/superpowers/specs/2026-05-16-file-import-design.md`

**Working dir:** all paths are relative to the repo root (`/Users/tomer/Desktop/finance-analysis/.claude/worktrees/priceless-lamport-a6ce68`). The venv is at `.venv/`; backend tests run via `poetry run pytest`, frontend tests via `cd frontend && npm test`.

---

## Task 1: Add dependencies

`openpyxl` is required for `pandas.read_excel(...)` on `.xlsx` files; `python-multipart` is required by FastAPI to parse `UploadFile` from `multipart/form-data`. Neither is in `pyproject.toml` today.

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the two deps under `[tool.poetry.dependencies]`**

Open `pyproject.toml`. Locate the dependencies block (lines 9–25). Add two lines under `httpx`:

```toml
openpyxl = "^3.1.5"
python-multipart = "^0.0.20"
```

- [ ] **Step 2: Install**

Run: `poetry install --no-root`
Expected: lockfile updated, both packages installed without errors. Check with:
```
poetry run python -c "import openpyxl, multipart; print(openpyxl.__version__, multipart.__version__)"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml poetry.lock
git commit -m "build: add openpyxl + python-multipart for file import"
```

---

## Task 2: `imported_accounts` ORM model + Tables enum

A single-table SQLAlchemy model that follows the existing `Base + TimestampMixin` pattern (see `backend/models/bank_balance.py` for the canonical shape).

**Files:**
- Create: `backend/models/imported_account.py`
- Modify: `backend/constants/tables.py` (add `IMPORTED_ACCOUNTS`)
- Modify: `backend/models/__init__.py` (export the model so `Base.metadata` picks it up)
- Test: `tests/backend/unit/models/test_imported_account_model.py`

- [ ] **Step 1: Write the failing model test**

Create `tests/backend/unit/models/test_imported_account_model.py`:

```python
"""Unit tests for the ImportedAccount ORM model."""

from sqlalchemy.orm import Session

from backend.models.imported_account import ImportedAccount


class TestImportedAccountModel:
    """Tests for the ImportedAccount ORM model."""

    def test_insert_and_retrieve(self, db_session: Session):
        """Insert a record and retrieve it back with all fields preserved."""
        account = ImportedAccount(
            service="banks",
            provider="Hapoalim Manual",
            account_name="Checking",
            mapping_json='{"date": {"column": "Date", "format": "iso"}}',
        )
        db_session.add(account)
        db_session.commit()

        retrieved = db_session.query(ImportedAccount).first()
        assert retrieved.id is not None
        assert retrieved.service == "banks"
        assert retrieved.provider == "Hapoalim Manual"
        assert retrieved.account_name == "Checking"
        assert "Date" in retrieved.mapping_json
        assert retrieved.created_at is not None
        assert retrieved.updated_at is not None

    def test_tablename(self):
        """Table name comes from the Tables enum."""
        from backend.constants.tables import Tables
        assert ImportedAccount.__tablename__ == Tables.IMPORTED_ACCOUNTS.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/backend/unit/models/test_imported_account_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.models.imported_account'`.

- [ ] **Step 3: Add the Tables enum entry**

Open `backend/constants/tables.py`. Inside the `class Tables(Enum):` block, add (alongside the other table entries):

```python
    IMPORTED_ACCOUNTS = "imported_accounts"
```

Place it near `BANK_BALANCES = "bank_balances"` so related tables stay grouped.

- [ ] **Step 4: Create the model**

Create `backend/models/imported_account.py`:

```python
"""Imported-account metadata for file-based data sources.

Each row represents one user-created account that ingests transactions
via uploaded CSV/XLSX files instead of via scraping. The saved
``mapping_json`` blob holds the column mapping the user defined once;
subsequent uploads reuse it.
"""

from sqlalchemy import Column, Integer, String, UniqueConstraint

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class ImportedAccount(Base, TimestampMixin):
    """ORM model for file-import data sources.

    Attributes
    ----------
    id : int
        Auto-incremented primary key.
    service : str
        One of ``"banks"``, ``"credit_cards"``, ``"cash"``. Determines
        which transactions table imported rows land in.
    provider : str
        Free-text provider label (e.g. ``"Hapoalim Manual"``,
        ``"Discover"``, ``"Imported"``).
    account_name : str
        Display label, unique within ``(service, provider)``.
    mapping_json : str
        JSON-encoded column mapping. See the design spec for the schema.
    """

    __tablename__ = Tables.IMPORTED_ACCOUNTS.value
    __table_args__ = (
        UniqueConstraint(
            "service", "provider", "account_name",
            name="uq_imported_accounts_service_provider_name",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    service = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    mapping_json = Column(String, nullable=False)
```

- [ ] **Step 5: Export from `backend/models/__init__.py`**

Open `backend/models/__init__.py`. Add an import line so `Base.metadata.create_all` picks up the new table at startup:

```python
from backend.models.imported_account import ImportedAccount  # noqa: F401
```

(Place alongside the other `from backend.models.X import Y  # noqa: F401` lines.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/models/test_imported_account_model.py -v`
Expected: 2 PASSED.

- [ ] **Step 7: Commit**

```bash
git add backend/models/imported_account.py backend/models/__init__.py backend/constants/tables.py tests/backend/unit/models/test_imported_account_model.py
git commit -m "feat(backend): add ImportedAccount ORM model"
```

---

## Task 3: `ImportedAccountsRepository`

CRUD wrapper around the new table. Follows the pattern in `backend/repositories/bank_balance_repository.py` — returns ORM objects for single-record reads, `pd.DataFrame` for list reads, raises `ValueError` on uniqueness violations.

**Files:**
- Create: `backend/repositories/imported_accounts_repository.py`
- Test: `tests/backend/unit/repositories/test_imported_accounts_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/backend/unit/repositories/test_imported_accounts_repository.py`:

```python
"""Unit tests for ImportedAccountsRepository."""

import pytest
from sqlalchemy.orm import Session

from backend.repositories.imported_accounts_repository import (
    ImportedAccountsRepository,
)


class TestImportedAccountsRepository:
    """Tests for ImportedAccountsRepository CRUD."""

    def test_get_all_empty(self, db_session: Session):
        """Get all returns empty DataFrame when no records exist."""
        repo = ImportedAccountsRepository(db_session)
        result = repo.get_all()
        assert result.empty

    def test_create_and_retrieve(self, db_session: Session):
        """Create persists a record and get_by_id returns it."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create(
            service="banks",
            provider="Hapoalim Manual",
            account_name="Checking",
            mapping_json='{"key": "value"}',
        )
        assert record.id is not None
        fetched = repo.get_by_id(record.id)
        assert fetched is not None
        assert fetched.service == "banks"

    def test_create_duplicate_triple_raises(self, db_session: Session):
        """Creating a second row with same (service, provider, account_name) raises ValueError."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "Hapoalim", "Checking", "{}")
        with pytest.raises(ValueError, match="already exists"):
            repo.create("banks", "Hapoalim", "Checking", "{}")

    def test_create_same_name_different_service_allowed(self, db_session: Session):
        """Same account_name + provider is allowed across different services."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "Generic", "Main", "{}")
        # Different service: allowed.
        repo.create("credit_cards", "Generic", "Main", "{}")
        assert len(repo.get_all()) == 2

    def test_get_all_returns_dataframe(self, db_session: Session):
        """Get all returns a DataFrame with expected columns."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "A", "Acc1", "{}")
        repo.create("credit_cards", "B", "Acc2", "{}")
        result = repo.get_all()
        assert len(result) == 2
        assert {"id", "service", "provider", "account_name", "mapping_json"}.issubset(
            result.columns
        )

    def test_update_mapping(self, db_session: Session):
        """Update mapping mutates only mapping_json."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create("banks", "X", "Y", '{"old": true}')
        updated = repo.update_mapping(record.id, '{"new": true}')
        assert updated.mapping_json == '{"new": true}'
        assert updated.service == "banks"

    def test_update_mapping_not_found_raises(self, db_session: Session):
        """Updating a missing id raises ValueError."""
        repo = ImportedAccountsRepository(db_session)
        with pytest.raises(ValueError, match="not found"):
            repo.update_mapping(999, "{}")

    def test_delete(self, db_session: Session):
        """Delete removes the row and returns True."""
        repo = ImportedAccountsRepository(db_session)
        record = repo.create("banks", "X", "Y", "{}")
        assert repo.delete(record.id) is True
        assert repo.get_by_id(record.id) is None

    def test_delete_not_found(self, db_session: Session):
        """Deleting a missing id returns False."""
        repo = ImportedAccountsRepository(db_session)
        assert repo.delete(999) is False

    def test_exists_for_triple(self, db_session: Session):
        """exists_for_triple flags collisions without raising."""
        repo = ImportedAccountsRepository(db_session)
        repo.create("banks", "X", "Y", "{}")
        assert repo.exists_for_triple("banks", "X", "Y") is True
        assert repo.exists_for_triple("banks", "X", "Z") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/repositories/test_imported_accounts_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.repositories.imported_accounts_repository'`.

- [ ] **Step 3: Create the repository**

Create `backend/repositories/imported_accounts_repository.py`:

```python
"""Repository for ImportedAccount records (CRUD)."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.imported_account import ImportedAccount


class ImportedAccountsRepository:
    """CRUD for file-import data source metadata."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session.
        """
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Return all imported accounts as a DataFrame.

        Returns
        -------
        pd.DataFrame
            Empty DataFrame if no rows; otherwise has columns
            ``id, service, provider, account_name, mapping_json,
            created_at, updated_at``.
        """
        stmt = select(ImportedAccount)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_id(self, account_id: int) -> ImportedAccount | None:
        """Return the ORM row for ``account_id`` or ``None``."""
        return self.db.get(ImportedAccount, account_id)

    def exists_for_triple(
        self, service: str, provider: str, account_name: str
    ) -> bool:
        """True if a row exists for the (service, provider, account_name) triple."""
        stmt = select(ImportedAccount).where(
            ImportedAccount.service == service,
            ImportedAccount.provider == provider,
            ImportedAccount.account_name == account_name,
        )
        return self.db.execute(stmt).first() is not None

    def create(
        self,
        service: str,
        provider: str,
        account_name: str,
        mapping_json: str,
    ) -> ImportedAccount:
        """Insert a new imported account.

        Raises
        ------
        ValueError
            If a row with the same (service, provider, account_name) triple
            already exists.
        """
        record = ImportedAccount(
            service=service,
            provider=provider,
            account_name=account_name,
            mapping_json=mapping_json,
        )
        self.db.add(record)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise ValueError(
                f"Imported account ({service}, {provider}, {account_name}) "
                "already exists"
            )
        self.db.refresh(record)
        return record

    def update_mapping(
        self, account_id: int, mapping_json: str
    ) -> ImportedAccount:
        """Replace ``mapping_json`` for ``account_id``.

        Raises
        ------
        ValueError
            If the row does not exist.
        """
        record = self.db.get(ImportedAccount, account_id)
        if record is None:
            raise ValueError(f"Imported account {account_id} not found")
        record.mapping_json = mapping_json
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, account_id: int) -> bool:
        """Delete the row by id. Returns True if deleted, False if not found."""
        record = self.db.get(ImportedAccount, account_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/repositories/test_imported_accounts_repository.py -v`
Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/imported_accounts_repository.py tests/backend/unit/repositories/test_imported_accounts_repository.py
git commit -m "feat(backend): add ImportedAccountsRepository CRUD"
```

---

## Task 4: File parser — type definitions + simple-mode parsing

The parser is a pure helper: raw file bytes + mapping → canonical DataFrame. Splitting it from the service layer makes it unit-testable in isolation and lets us reuse it for the `/preview` endpoint.

This task covers: the mapping dataclasses, file reading (with UTF-8 → Windows-1255 fallback for CSV), `skip_rows`, header parsing, and the **single-signed-amount** path. Split-mode amount handling and date-format autodetection land in Task 5.

**Files:**
- Create: `backend/services/file_import_parser.py`
- Create: `tests/backend/unit/services/test_file_import_parser.py`
- Create: `tests/backend/unit/services/fixtures/imports/simple_signed.csv`
- Create: `tests/backend/unit/services/fixtures/imports/simple_signed_with_banner.csv`
- Create: `tests/backend/unit/services/fixtures/imports/simple_signed.xlsx` (generated; see step 1)

- [ ] **Step 1: Create the fixture files**

Create `tests/backend/unit/services/fixtures/imports/simple_signed.csv`:

```
date,description,amount
2026-03-01,Coffee shop,-12.50
2026-03-03,Salary,8500.00
2026-03-05,Refund,45.00
2026-03-07,Gym membership,-180.00
```

Create `tests/backend/unit/services/fixtures/imports/simple_signed_with_banner.csv`:

```
Bank Statement Export
Generated 2026-03-15
Account: 12345

date,description,amount
2026-03-01,Coffee shop,-12.50
2026-03-03,Salary,8500.00
```

Generate the xlsx fixture by running the following one-liner from the repo root (after Task 1 installed openpyxl). Run:

```bash
poetry run python -c "
import pandas as pd
import os
os.makedirs('tests/backend/unit/services/fixtures/imports', exist_ok=True)
pd.DataFrame({
    'date': ['2026-03-01', '2026-03-03', '2026-03-05'],
    'description': ['Coffee shop', 'Salary', 'Refund'],
    'amount': [-12.50, 8500.00, 45.00],
}).to_excel('tests/backend/unit/services/fixtures/imports/simple_signed.xlsx', index=False)
print('written')
"
```
Expected output: `written`.

- [ ] **Step 2: Write the failing parser tests**

Create `tests/backend/unit/services/test_file_import_parser.py`:

```python
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
        # Row 0 was -12.50 originally; under flip it becomes +12.50.
        assert df.iloc[0]["amount"] == 12.50
        # Row 1 was +8500 originally; under flip it becomes -8500.
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_file_import_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.file_import_parser'`.

- [ ] **Step 4: Implement the parser (simple mode only — split mode + autodate in Task 5)**

Create `backend/services/file_import_parser.py`:

```python
"""Pure file-to-DataFrame parser for the file-import feature.

Given raw bytes + a column mapping, returns a canonical DataFrame with
columns ``date``, ``description``, ``amount`` (and optional ``category``,
``tag``, ``account_number``). No I/O, no DB. Tested in isolation.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
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
        # Placeholder: full format handling lands in Task 5.
        raise NotImplementedError(f"Date format {fmt!r} not implemented yet")
    return parsed.dt.strftime("%Y-%m-%d")


def _compute_amount(df: pd.DataFrame, amount: AmountMapping) -> pd.Series:
    """Compute the canonical signed amount per row."""
    if amount.mode == "single":
        series = pd.to_numeric(df[amount.column], errors="coerce")
        if amount.sign_convention == "positive_is_expense":
            series = -series
        return series
    # mode == "split": Task 5
    raise NotImplementedError("split mode lands in Task 5")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_file_import_parser.py -v`
Expected: 6 PASSED (the simple-signed CSV, banner, sign flip, xlsx, CP1255, and the two validation tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/file_import_parser.py tests/backend/unit/services/test_file_import_parser.py tests/backend/unit/services/fixtures/
git commit -m "feat(backend): pure file-import parser for single-signed amount mode"
```

---

## Task 5: File parser — split mode, date autodetect, row-validation summary

Adds the rest of the parser:
- **Split amount mode** (`amount = credit − debit`)
- **Date formats** beyond ISO: `dd/mm/yyyy`, `mm/dd/yyyy`, `dd-mm-yyyy`, `dd.mm.yyyy`, `excel_serial`, and `"auto"` detect-from-sample
- **Row-level validation summary** — returns `(df, dropped_invalid_count)` so the caller can report dropped rows. Rows that don't pass validation are silently filtered out of `df`.

**Files:**
- Modify: `backend/services/file_import_parser.py`
- Modify: `tests/backend/unit/services/test_file_import_parser.py`
- Create: `tests/backend/unit/services/fixtures/imports/hapoalim_style.csv` (CP1255, banner rows, split debit/credit)
- Create: `tests/backend/unit/services/fixtures/imports/dd_mm_yyyy.csv`

- [ ] **Step 1: Create the new fixtures**

Create `tests/backend/unit/services/fixtures/imports/dd_mm_yyyy.csv`:

```
date,description,amount
01/03/2026,Coffee,-12.50
03/03/2026,Salary,8500.00
15/03/2026,Bad date row,foo
```

Create the Hapoalim-style CP1255 fixture by running:

```bash
poetry run python -c "
from pathlib import Path
out = Path('tests/backend/unit/services/fixtures/imports/hapoalim_style.csv')
# Two banner rows, then header with Hebrew column names, then 3 data rows.
content = (
    'Hapoalim Export\n'
    'Generated 2026-03-15\n'
    'תאריך,תיאור,חובה,זכות\n'
    '01/03/2026,קפה,12.50,\n'
    '03/03/2026,משכורת,,8500\n'
    '07/03/2026,חדר כושר,180,\n'
)
out.write_bytes(content.encode('cp1255'))
print('written')
"
```

- [ ] **Step 2: Write the new failing tests**

Append to `tests/backend/unit/services/test_file_import_parser.py`:

```python
from backend.services.file_import_parser import parse_file_with_summary


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
        """Excel serial dates (e.g., 45717 = 2025-03-15) parse correctly."""
        import pandas as pd_local
        df_xl = pd_local.DataFrame({
            "date": [45717, 45719],
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
        # 1899-12-30 + 45717 days = 2025-03-15
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
```

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `poetry run pytest tests/backend/unit/services/test_file_import_parser.py -v`
Expected: the 6 original tests still pass; the new tests fail (split mode `NotImplementedError`, missing `parse_file_with_summary`).

- [ ] **Step 4: Extend the parser**

In `backend/services/file_import_parser.py`, replace the existing `_parse_dates` and `_compute_amount` functions and add a `parse_file_with_summary` entry point:

```python
def parse_file_with_summary(
    raw: bytes,
    filename: str,
    mapping: ColumnMapping,
) -> tuple[pd.DataFrame, int]:
    """Like ``parse_file`` but also drops invalid rows and counts them.

    Returns
    -------
    tuple
        ``(canonical_df_with_only_valid_rows, dropped_invalid_count)``.
    """
    raw_df = _read_raw(raw, filename, skip_rows=mapping.skip_rows)
    _check_columns_exist(raw_df, mapping)

    parsed = pd.DataFrame()
    parsed["date"] = _parse_dates(raw_df[mapping.date.column], mapping.date.format)
    parsed["description"] = raw_df[mapping.description.column].astype(str)
    parsed["amount"] = _compute_amount(raw_df, mapping.amount)

    if mapping.category and mapping.category.column:
        parsed["category"] = raw_df[mapping.category.column].astype(str)
    if mapping.tag and mapping.tag.column:
        parsed["tag"] = raw_df[mapping.tag.column].astype(str)
    if mapping.account_number and mapping.account_number.column:
        parsed["account_number"] = raw_df[mapping.account_number.column].astype(str)

    # A row is invalid if date didn't parse or amount didn't parse to a number.
    invalid_mask = parsed["date"].isna() | parsed["amount"].isna()
    dropped = int(invalid_mask.sum())
    cleaned = parsed.loc[~invalid_mask].reset_index(drop=True)
    return cleaned, dropped
```

Replace the previous `_parse_dates` with the full multi-format version:

```python
_DATE_FORMATS: dict[str, str] = {
    "iso": "%Y-%m-%d",
    "dd/mm/yyyy": "%d/%m/%Y",
    "mm/dd/yyyy": "%m/%d/%Y",
    "dd-mm-yyyy": "%d-%m-%Y",
    "dd.mm.yyyy": "%d.%m.%Y",
}


def _parse_dates(series: pd.Series, fmt: Optional[str]) -> pd.Series:
    """Parse a date series to ``YYYY-MM-DD`` strings (or NaT for invalid)."""
    if fmt is None or fmt == "auto":
        chosen = _autodetect_format(series)
        return _apply_format(series, chosen)
    if fmt == "excel_serial":
        numeric = pd.to_numeric(series, errors="coerce")
        parsed = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
        return parsed.dt.strftime("%Y-%m-%d")
    if fmt in _DATE_FORMATS:
        return _apply_format(series, _DATE_FORMATS[fmt])
    raise ValueError(f"Unknown date format: {fmt!r}")


def _apply_format(series: pd.Series, fmt: str) -> pd.Series:
    """Apply a strptime-style format and emit ISO strings."""
    parsed = pd.to_datetime(series, format=fmt, errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def _autodetect_format(series: pd.Series) -> str:
    """Pick the format that parses the highest fraction of sample values."""
    sample = series.dropna().astype(str).head(20)
    if len(sample) == 0:
        return _DATE_FORMATS["iso"]
    best_fmt = _DATE_FORMATS["iso"]
    best_ok = -1
    for fmt in _DATE_FORMATS.values():
        parsed = pd.to_datetime(sample, format=fmt, errors="coerce")
        ok = parsed.notna().sum()
        if ok > best_ok:
            best_ok = ok
            best_fmt = fmt
    return best_fmt
```

Replace `_compute_amount` with the split-mode-aware version:

```python
def _compute_amount(df: pd.DataFrame, amount: AmountMapping) -> pd.Series:
    """Compute the canonical signed amount per row.

    - ``single`` mode: read the column, optionally flip the sign.
    - ``split`` mode: ``amount = credit - debit``; empty cells treated as 0.
    """
    if amount.mode == "single":
        series = pd.to_numeric(df[amount.column], errors="coerce")
        if amount.sign_convention == "positive_is_expense":
            series = -series
        return series
    # split mode
    debit = pd.to_numeric(df[amount.debit_column], errors="coerce").fillna(0)
    credit = pd.to_numeric(df[amount.credit_column], errors="coerce").fillna(0)
    return credit - debit
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `poetry run pytest tests/backend/unit/services/test_file_import_parser.py -v`
Expected: all tests PASS (10+ total).

- [ ] **Step 6: Commit**

```bash
git add backend/services/file_import_parser.py tests/backend/unit/services/test_file_import_parser.py tests/backend/unit/services/fixtures/imports/
git commit -m "feat(backend): split-amount mode, date format autodetect, row drops"
```

---

## Task 6: `ImportedAccountsService` — CRUD wrapper (no import flow yet)

Service-layer wrapper around the repo. Handles uniqueness checks **across both** `imported_accounts` and `credentials` (since the data sources list joins them) and JSON serialisation of `mapping_json`. The import-execution flow lands in Task 7.

**Files:**
- Create: `backend/services/imported_accounts_service.py`
- Create: `tests/backend/unit/services/test_imported_accounts_service_crud.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/backend/unit/services/test_imported_accounts_service_crud.py`:

```python
"""Unit tests for ImportedAccountsService — CRUD path."""

import pytest
from sqlalchemy.orm import Session

from backend.repositories.credentials_repository import CredentialsRepository
from backend.services.imported_accounts_service import (
    ImportedAccountsService,
    ImportedAccountDTO,
)


def _default_mapping() -> dict:
    return {
        "skip_rows": 0,
        "date": {"column": "date", "format": "iso"},
        "description": {"column": "description"},
        "amount": {
            "mode": "single",
            "column": "amount",
            "sign_convention": "positive_is_income",
        },
    }


class TestImportedAccountsServiceCrud:
    """CRUD wrapper behaviour."""

    def test_list_empty(self, db_session: Session):
        """list_accounts returns [] on an empty DB."""
        service = ImportedAccountsService(db_session)
        assert service.list_accounts() == []

    def test_create_returns_dto(self, db_session: Session):
        """create returns an ImportedAccountDTO with the new id."""
        service = ImportedAccountsService(db_session)
        dto = service.create(
            service_type="banks",
            provider="Hapoalim",
            account_name="Checking",
            mapping=_default_mapping(),
        )
        assert isinstance(dto, ImportedAccountDTO)
        assert dto.id is not None
        assert dto.service == "banks"
        assert dto.mapping["amount"]["mode"] == "single"

    def test_create_duplicate_in_imported_raises(self, db_session: Session):
        """Creating the same triple twice raises ValueError."""
        service = ImportedAccountsService(db_session)
        service.create("banks", "H", "A", _default_mapping())
        with pytest.raises(ValueError, match="already exists"):
            service.create("banks", "H", "A", _default_mapping())

    def test_create_collides_with_credential_raises(self, db_session: Session, monkeypatch):
        """If a credential exists for the same triple, creation is blocked."""
        # Seed a credential row. CredentialsRepository writes to keyring +
        # YAML; for this test we bypass with a small monkeypatch.
        service = ImportedAccountsService(db_session)

        def fake_collides(_service, _provider, _account_name):
            return True

        monkeypatch.setattr(
            service,
            "_credential_collision",
            fake_collides,
        )
        with pytest.raises(ValueError, match="connected account"):
            service.create("banks", "H", "A", _default_mapping())

    def test_update_mapping(self, db_session: Session):
        """update_mapping persists a new mapping json."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "H", "A", _default_mapping())
        new_mapping = _default_mapping()
        new_mapping["skip_rows"] = 3
        updated = service.update_mapping(dto.id, new_mapping)
        assert updated.mapping["skip_rows"] == 3

    def test_delete_cascades_transactions(self, db_session: Session):
        """Deleting an account also removes its imported transactions."""
        from backend.models.transaction import BankTransaction

        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "H", "Acc", _default_mapping())
        # Seed a transaction that belongs to this account.
        db_session.add(BankTransaction(
            id="x1", date="2026-03-01", provider="H", account_name="Acc",
            description="Coffee", amount=-12.5, source="bank_transactions",
            type="normal", status="completed",
        ))
        # Seed an unrelated transaction (different account) — must survive.
        db_session.add(BankTransaction(
            id="x2", date="2026-03-01", provider="H", account_name="Other",
            description="Other", amount=-10, source="bank_transactions",
            type="normal", status="completed",
        ))
        db_session.commit()

        service.delete(dto.id)

        remaining = db_session.query(BankTransaction).all()
        assert len(remaining) == 1
        assert remaining[0].account_name == "Other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_imported_accounts_service_crud.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the service**

Create `backend/services/imported_accounts_service.py`:

```python
"""Service for file-import data source CRUD and import execution.

This module currently exposes the CRUD surface. The import-execution
path (parse → dedup → tag → insert) lands in a follow-on task.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.models.transaction import (
    BankTransaction,
    CashTransaction,
    CreditCardTransaction,
)
from backend.repositories.credentials_repository import CredentialsRepository
from backend.repositories.imported_accounts_repository import (
    ImportedAccountsRepository,
)


ServiceType = Literal["banks", "credit_cards", "cash"]

_TX_MODEL_BY_SERVICE = {
    "banks": BankTransaction,
    "credit_cards": CreditCardTransaction,
    "cash": CashTransaction,
}


@dataclass
class ImportedAccountDTO:
    """Frontend-friendly view of an imported account row."""

    id: int
    service: str
    provider: str
    account_name: str
    mapping: dict[str, Any]


class ImportedAccountsService:
    """CRUD + import execution for file-import data sources."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session.
        """
        self.db = db
        self.repo = ImportedAccountsRepository(db)

    # ---------- CRUD ----------

    def list_accounts(self) -> list[ImportedAccountDTO]:
        """Return all imported accounts as DTOs."""
        df = self.repo.get_all()
        if df.empty:
            return []
        return [
            ImportedAccountDTO(
                id=int(row.id),
                service=row.service,
                provider=row.provider,
                account_name=row.account_name,
                mapping=json.loads(row.mapping_json),
            )
            for row in df.itertuples(index=False)
        ]

    def create(
        self,
        service_type: ServiceType,
        provider: str,
        account_name: str,
        mapping: dict[str, Any],
    ) -> ImportedAccountDTO:
        """Create a new imported account after validating the triple is unique
        across both imported accounts and connected (scraped) accounts.

        Raises
        ------
        ValueError
            If a connected account or imported account already uses the
            (service_type, provider, account_name) triple.
        """
        if self._credential_collision(service_type, provider, account_name):
            raise ValueError(
                f"A connected account already uses ({service_type}, "
                f"{provider}, {account_name})"
            )
        record = self.repo.create(
            service=service_type,
            provider=provider,
            account_name=account_name,
            mapping_json=json.dumps(mapping),
        )
        return ImportedAccountDTO(
            id=record.id,
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            mapping=mapping,
        )

    def update_mapping(
        self, account_id: int, mapping: dict[str, Any]
    ) -> ImportedAccountDTO:
        """Replace the saved mapping for ``account_id``."""
        record = self.repo.update_mapping(account_id, json.dumps(mapping))
        return ImportedAccountDTO(
            id=record.id,
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            mapping=mapping,
        )

    def delete(self, account_id: int) -> bool:
        """Delete an imported account and cascade-delete its transactions.

        Returns
        -------
        bool
            ``True`` if the account was deleted, ``False`` if it didn't exist.
        """
        record = self.repo.get_by_id(account_id)
        if record is None:
            return False
        model = _TX_MODEL_BY_SERVICE[record.service]
        self.db.execute(
            delete(model).where(
                model.provider == record.provider,
                model.account_name == record.account_name,
            )
        )
        return self.repo.delete(account_id)

    # ---------- helpers ----------

    def _credential_collision(
        self, service_type: str, provider: str, account_name: str
    ) -> bool:
        """True if a connected (scraped) account exists for the triple.

        Implemented as a method so tests can monkeypatch it without
        touching the OS keyring.
        """
        try:
            creds = CredentialsRepository(self.db)
            accounts = creds.get_accounts()
        except Exception:
            # CredentialsRepository can raise on missing YAML / keyring in
            # some environments; treat as "no collision".
            return False
        for acc in accounts:
            if (
                acc.get("service") == service_type
                and acc.get("provider") == provider
                and acc.get("account_name") == account_name
            ):
                return True
        return False
```

- [ ] **Step 4: Verify `CredentialsRepository.get_accounts()` exists**

Run: `grep -n "def get_accounts" backend/repositories/credentials_repository.py`
Expected: a method definition. If the method is named differently (e.g. `list_accounts`), update the call in `_credential_collision` to match and re-run.

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_imported_accounts_service_crud.py -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/services/imported_accounts_service.py tests/backend/unit/services/test_imported_accounts_service_crud.py
git commit -m "feat(backend): ImportedAccountsService CRUD + collision check"
```

---

## Task 7: `ImportedAccountsService` — import execution

Adds the actual import flow: parse the uploaded file with the saved mapping, dedup against existing transactions for this account (content hash), auto-tag rows without mapped category/tag, bulk-insert into the right transactions table, and trigger cash-balance recalculation when applicable.

**Files:**
- Modify: `backend/services/imported_accounts_service.py`
- Create: `tests/backend/unit/services/test_imported_accounts_service_import.py`

- [ ] **Step 1: Write failing import-flow tests**

Create `tests/backend/unit/services/test_imported_accounts_service_import.py`:

```python
"""Unit tests for ImportedAccountsService — import execution."""

from sqlalchemy.orm import Session

from backend.models.transaction import BankTransaction, CashTransaction
from backend.services.imported_accounts_service import (
    ImportedAccountsService,
)


CSV_BYTES = (
    b"date,description,amount\n"
    b"2026-03-01,Coffee shop,-12.50\n"
    b"2026-03-03,Salary,8500.00\n"
    b"2026-03-05,Refund,45.00\n"
)


MAPPING = {
    "skip_rows": 0,
    "date": {"column": "date", "format": "iso"},
    "description": {"column": "description"},
    "amount": {
        "mode": "single",
        "column": "amount",
        "sign_convention": "positive_is_income",
    },
    "category": {"column": None},
    "tag": {"column": None},
    "account_number": {"column": None},
}


class TestImportExecution:
    """Import flow: parse, dedup, tag, insert."""

    def test_first_upload_inserts_all_rows(self, db_session: Session):
        """A fresh import inserts every row into the matching service's table."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)

        summary = service.import_file(
            account_id=dto.id, raw=CSV_BYTES, filename="test.csv"
        )

        assert summary["inserted"] == 3
        assert summary["skipped_duplicates"] == 0
        assert summary["dropped_invalid"] == 0

        rows = db_session.query(BankTransaction).filter_by(
            provider="Hapoalim", account_name="Checking"
        ).all()
        assert len(rows) == 3
        # Provider + account_name + source baked in.
        assert all(r.source == "bank_transactions" for r in rows)
        assert all(r.type == "normal" for r in rows)

    def test_dedup_skips_repeats(self, db_session: Session):
        """Reuploading the same file inserts nothing new."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="test.csv")
        summary = service.import_file(
            account_id=dto.id, raw=CSV_BYTES, filename="test.csv"
        )
        assert summary["inserted"] == 0
        assert summary["skipped_duplicates"] == 3

    def test_partial_overlap_only_new_rows_inserted(self, db_session: Session):
        """A second file that overlaps with the first imports only the new rows."""
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "Hapoalim", "Checking", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="first.csv")

        second_file = (
            b"date,description,amount\n"
            b"2026-03-03,Salary,8500.00\n"     # dup
            b"2026-03-05,Refund,45.00\n"        # dup
            b"2026-03-10,Withdrawal,-200.00\n"  # new
        )
        summary = service.import_file(
            account_id=dto.id, raw=second_file, filename="second.csv"
        )
        assert summary["inserted"] == 1
        assert summary["skipped_duplicates"] == 2

    def test_cash_service_recalculates_balance(self, db_session: Session, monkeypatch):
        """Cash imports trigger CashBalanceService.recalculate_current_balance."""
        from backend.services import imported_accounts_service as iam

        called = {"with_account": None}

        class FakeCashService:
            def __init__(self, _db):
                pass
            def recalculate_current_balance(self, account_name):
                called["with_account"] = account_name

        monkeypatch.setattr(iam, "CashBalanceService", FakeCashService)

        service = ImportedAccountsService(db_session)
        dto = service.create("cash", "MANUAL", "Wallet", MAPPING)
        service.import_file(account_id=dto.id, raw=CSV_BYTES, filename="test.csv")

        # Rows landed in cash_transactions
        rows = db_session.query(CashTransaction).filter_by(account_name="Wallet").all()
        assert len(rows) == 3
        assert called["with_account"] == "Wallet"

    def test_dropped_invalid_counted(self, db_session: Session):
        """Rows with unparseable amount/date are dropped and reported."""
        bad_csv = (
            b"date,description,amount\n"
            b"2026-03-01,ok,-12.50\n"
            b"2026-03-03,bad,notanumber\n"
        )
        service = ImportedAccountsService(db_session)
        dto = service.create("banks", "X", "Y", MAPPING)
        summary = service.import_file(
            account_id=dto.id, raw=bad_csv, filename="bad.csv"
        )
        assert summary["inserted"] == 1
        assert summary["dropped_invalid"] == 1

    def test_account_not_found_raises(self, db_session: Session):
        """Importing to a non-existent account raises ValueError."""
        import pytest
        service = ImportedAccountsService(db_session)
        with pytest.raises(ValueError, match="not found"):
            service.import_file(account_id=999, raw=CSV_BYTES, filename="x.csv")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_imported_accounts_service_import.py -v`
Expected: FAIL — `import_file` not defined.

- [ ] **Step 3: Extend the service**

Add to `backend/services/imported_accounts_service.py` (at the bottom of the class, and add a few imports at the top of the file):

At the top, alongside the existing imports, add:

```python
import hashlib

import pandas as pd
from sqlalchemy import select

from backend.services.cash_balance_service import CashBalanceService
from backend.services.file_import_parser import (
    AmountMapping,
    ColumnMapping,
    FieldMapping,
    parse_file_with_summary,
)
from backend.services.tagging_rules_service import TaggingRulesService
```

Inside the `ImportedAccountsService` class, add:

```python
    # ---------- Import execution ----------

    def import_file(
        self,
        account_id: int,
        raw: bytes,
        filename: str,
    ) -> dict[str, int]:
        """Parse, dedup, auto-tag, and insert rows from a file upload.

        Parameters
        ----------
        account_id : int
            ID of the imported account this upload belongs to.
        raw : bytes
            Raw uploaded file bytes.
        filename : str
            Original filename (used to pick CSV vs XLSX reader).

        Returns
        -------
        dict
            ``{"inserted": N, "skipped_duplicates": M, "dropped_invalid": K}``.

        Raises
        ------
        ValueError
            If the account does not exist, or parsing fails fundamentally.
        """
        record = self.repo.get_by_id(account_id)
        if record is None:
            raise ValueError(f"Imported account {account_id} not found")
        mapping_dict = json.loads(record.mapping_json)
        mapping = _dict_to_mapping(mapping_dict)

        parsed_df, dropped = parse_file_with_summary(
            raw, filename=filename, mapping=mapping
        )
        if parsed_df.empty:
            return {"inserted": 0, "skipped_duplicates": 0, "dropped_invalid": dropped}

        # Dedup against existing transactions for this account in the file's date range.
        existing_hashes = self._existing_hashes_for_account(
            service=record.service,
            provider=record.provider,
            account_name=record.account_name,
            min_date=parsed_df["date"].min(),
            max_date=parsed_df["date"].max(),
        )
        parsed_df["_hash"] = parsed_df.apply(_row_hash, axis=1)
        new_rows = parsed_df[~parsed_df["_hash"].isin(existing_hashes)].copy()
        skipped = len(parsed_df) - len(new_rows)
        if new_rows.empty:
            return {
                "inserted": 0,
                "skipped_duplicates": skipped,
                "dropped_invalid": dropped,
            }
        new_rows = new_rows.drop(columns=["_hash"])

        # Auto-tag rows that didn't get a category/tag from the file.
        rules_service = TaggingRulesService(self.db)
        for idx, row in new_rows.iterrows():
            has_category = "category" in new_rows.columns and bool(row.get("category"))
            has_tag = "tag" in new_rows.columns and bool(row.get("tag"))
            if has_category and has_tag:
                continue
            suggestion = rules_service.apply_rules_to_transaction({
                "description": row["description"],
                "amount": row["amount"],
                "provider": record.provider,
                "account_name": record.account_name,
                "service": record.service,
            })
            if suggestion:
                if not has_category:
                    new_rows.at[idx, "category"] = suggestion.get("category")
                if not has_tag:
                    new_rows.at[idx, "tag"] = suggestion.get("tag")

        # Bulk-insert into the matching service's table.
        model = _TX_MODEL_BY_SERVICE[record.service]
        source = model.__tablename__
        inserted = 0
        for _, row in new_rows.iterrows():
            tx = model(
                id=row.get("_hash") or _row_hash(row),
                date=row["date"],
                provider=record.provider,
                account_name=record.account_name,
                account_number=row.get("account_number"),
                description=row["description"],
                amount=float(row["amount"]),
                category=row.get("category"),
                tag=row.get("tag"),
                source=source,
                type="normal",
                status="completed",
            )
            self.db.add(tx)
            inserted += 1
        self.db.commit()

        # Side effect: cash balance.
        if record.service == "cash":
            CashBalanceService(self.db).recalculate_current_balance(record.account_name)

        return {
            "inserted": inserted,
            "skipped_duplicates": skipped,
            "dropped_invalid": dropped,
        }

    def _existing_hashes_for_account(
        self,
        service: str,
        provider: str,
        account_name: str,
        min_date: str,
        max_date: str,
    ) -> set[str]:
        """Hash existing transactions for this account in the [min_date, max_date] range."""
        model = _TX_MODEL_BY_SERVICE[service]
        stmt = select(
            model.date, model.description, model.amount
        ).where(
            model.provider == provider,
            model.account_name == account_name,
            model.date >= min_date,
            model.date <= max_date,
        )
        out: set[str] = set()
        for row in self.db.execute(stmt):
            out.add(_hash_triple(row.date, row.description, row.amount))
        return out
```

Outside the class (module-level), add the helpers:

```python
def _row_hash(row: pd.Series) -> str:
    """Content hash for dedup: (date, description, amount)."""
    return _hash_triple(row["date"], row["description"], row["amount"])


def _hash_triple(date: str, description: str, amount: float) -> str:
    """Stable content hash used for dedup."""
    blob = f"{date}|{description}|{amount:.4f}".encode("utf-8")
    return hashlib.sha1(blob, usedforsecurity=False).hexdigest()


def _dict_to_mapping(d: dict) -> ColumnMapping:
    """Inflate a JSON mapping dict into a ColumnMapping dataclass."""
    def field(spec: dict | None) -> FieldMapping | None:
        if not spec or not spec.get("column"):
            return None
        return FieldMapping(column=spec["column"], format=spec.get("format"))

    amt = d["amount"]
    if amt["mode"] == "single":
        amount = AmountMapping(
            mode="single",
            column=amt["column"],
            sign_convention=amt.get("sign_convention", "positive_is_income"),
        )
    else:
        amount = AmountMapping(
            mode="split",
            debit_column=amt["debit_column"],
            credit_column=amt["credit_column"],
        )

    return ColumnMapping(
        skip_rows=d.get("skip_rows", 0),
        date=FieldMapping(column=d["date"]["column"], format=d["date"].get("format")),
        description=FieldMapping(column=d["description"]["column"]),
        amount=amount,
        category=field(d.get("category")),
        tag=field(d.get("tag")),
        account_number=field(d.get("account_number")),
    )
```

- [ ] **Step 4: Confirm `TaggingRulesService.apply_rules_to_transaction` exists with the expected shape**

Run: `grep -n "def apply_rules" backend/services/tagging_rules_service.py`
Expected: a method that takes a dict and returns `{"category": ..., "tag": ...}` (or `None`). If the public method has a different name or shape, update the call site in `import_file` accordingly. Common alternatives in this codebase: `find_matching_rule` returns the rule (not category/tag); in that case, transform inside the import flow.

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_imported_accounts_service_import.py -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/services/imported_accounts_service.py tests/backend/unit/services/test_imported_accounts_service_import.py
git commit -m "feat(backend): file import flow with dedup + auto-tag + cash balance hook"
```

---

## Task 8: Routes + template + preview endpoint

Wire up the HTTP surface. Six endpoints, registered in `main.py`. The `/template` endpoint serves a static CSV; the `/preview` endpoint runs the parser without persisting.

**Files:**
- Create: `backend/routes/imported_accounts.py`
- Modify: `backend/main.py` (register the router)
- Modify: `backend/services/imported_accounts_service.py` (add a `preview` method used by the route)
- Create: `tests/backend/routes/test_imported_accounts_routes.py`

- [ ] **Step 1: Add `preview` method to the service**

Append to `ImportedAccountsService` in `backend/services/imported_accounts_service.py`:

```python
    def preview(
        self,
        raw: bytes,
        filename: str,
        mapping: dict,
    ) -> dict:
        """Parse a file with a mapping and return the first 5 mapped rows.

        Used by the column-mapping wizard's live preview — runs the parser
        in-memory, no DB writes.

        Returns
        -------
        dict
            ``{"rows": [...], "dropped_invalid": K, "raw_headers": [...]}``.
            ``rows`` contains up to 5 records as dicts.
        """
        from backend.services.file_import_parser import _read_raw  # local import

        try:
            raw_df = _read_raw(raw, filename, skip_rows=mapping.get("skip_rows", 0))
        except Exception as e:
            raise ValueError(f"Could not parse file: {e}") from e
        headers = list(raw_df.columns)

        parsed_df, dropped = parse_file_with_summary(
            raw, filename=filename, mapping=_dict_to_mapping(mapping)
        )
        rows = parsed_df.head(5).to_dict(orient="records")
        return {"rows": rows, "dropped_invalid": dropped, "raw_headers": headers}
```

- [ ] **Step 2: Write failing route tests**

Create `tests/backend/routes/test_imported_accounts_routes.py`:

```python
"""Route tests for imported-accounts endpoints."""

from fastapi.testclient import TestClient


VALID_MAPPING = {
    "skip_rows": 0,
    "date": {"column": "date", "format": "iso"},
    "description": {"column": "description"},
    "amount": {
        "mode": "single",
        "column": "amount",
        "sign_convention": "positive_is_income",
    },
    "category": {"column": None},
    "tag": {"column": None},
    "account_number": {"column": None},
}


CSV = (
    b"date,description,amount\n"
    b"2026-03-01,Coffee shop,-12.50\n"
    b"2026-03-03,Salary,8500.00\n"
)


class TestImportedAccountsRoutes:
    """Endpoint-level smoke tests."""

    def test_create_and_list(self, test_client: TestClient):
        """POST then GET returns the created row."""
        resp = test_client.post("/api/imported-accounts/", json={
            "service": "banks",
            "provider": "Hapoalim",
            "account_name": "Checking",
            "mapping": VALID_MAPPING,
        })
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["id"]

        listed = test_client.get("/api/imported-accounts/").json()
        assert len(listed) == 1
        assert listed[0]["account_name"] == "Checking"

    def test_create_duplicate_returns_400(self, test_client: TestClient):
        body = {
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }
        test_client.post("/api/imported-accounts/", json=body)
        resp = test_client.post("/api/imported-accounts/", json=body)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_mapping(self, test_client: TestClient):
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        new_mapping = {**VALID_MAPPING, "skip_rows": 2}
        resp = test_client.put(
            f"/api/imported-accounts/{created['id']}",
            json={"mapping": new_mapping},
        )
        assert resp.status_code == 200
        assert resp.json()["mapping"]["skip_rows"] == 2

    def test_delete(self, test_client: TestClient):
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        resp = test_client.delete(f"/api/imported-accounts/{created['id']}")
        assert resp.status_code == 200
        assert test_client.get("/api/imported-accounts/").json() == []

    def test_upload(self, test_client: TestClient):
        created = test_client.post("/api/imported-accounts/", json={
            "service": "banks", "provider": "H", "account_name": "A",
            "mapping": VALID_MAPPING,
        }).json()
        resp = test_client.post(
            f"/api/imported-accounts/{created['id']}/upload",
            files={"file": ("test.csv", CSV, "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        assert summary["inserted"] == 2

    def test_preview(self, test_client: TestClient):
        import json
        resp = test_client.post(
            "/api/imported-accounts/preview",
            files={"file": ("test.csv", CSV, "text/csv")},
            data={"mapping": json.dumps(VALID_MAPPING)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["rows"]) == 2
        assert body["dropped_invalid"] == 0
        assert "date" in body["raw_headers"]

    def test_template(self, test_client: TestClient):
        resp = test_client.get("/api/imported-accounts/template")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        body = resp.content.decode("utf-8")
        assert body.startswith("date,description,amount,category,tag")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/routes/test_imported_accounts_routes.py -v`
Expected: 404 / module not found.

- [ ] **Step 4: Create the route module**

Create `backend/routes/imported_accounts.py`:

```python
"""API routes for file-import data sources."""

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.imported_accounts_service import ImportedAccountsService

router = APIRouter()


class CreateRequest(BaseModel):
    service: str
    provider: str
    account_name: str
    mapping: dict[str, Any]


class UpdateMappingRequest(BaseModel):
    mapping: dict[str, Any]


_TEMPLATE_CSV = (
    "date,description,amount,category,tag\n"
    "2026-03-01,Coffee shop,-12.50,Food,Coffee\n"
    "2026-03-03,Salary,8500.00,Salary,Salary\n"
    "2026-03-05,Refund,45.00,Food,Groceries\n"
    "2026-03-07,Gym membership,-180.00,,\n"
    "2026-03-10,Withdrawal,-200.00,,\n"
)


@router.get("/")
async def list_imported_accounts(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """List all file-import accounts."""
    service = ImportedAccountsService(db)
    return [dto.__dict__ for dto in service.list_accounts()]


@router.post("/")
async def create_imported_account(
    req: CreateRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Create a new file-import account."""
    service = ImportedAccountsService(db)
    try:
        dto = service.create(
            service_type=req.service,
            provider=req.provider,
            account_name=req.account_name,
            mapping=req.mapping,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dto.__dict__


@router.put("/{account_id}")
async def update_imported_account_mapping(
    account_id: int,
    req: UpdateMappingRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Update only the saved mapping for an account."""
    service = ImportedAccountsService(db)
    try:
        dto = service.update_mapping(account_id, req.mapping)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return dto.__dict__


@router.delete("/{account_id}")
async def delete_imported_account(
    account_id: int,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete an imported account + cascade-delete its transactions."""
    service = ImportedAccountsService(db)
    if not service.delete(account_id):
        raise HTTPException(status_code=404, detail="Imported account not found")
    return {"status": "deleted"}


@router.post("/{account_id}/upload")
async def upload_file(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_database),
) -> dict[str, int]:
    """Run an import against the saved mapping for ``account_id``."""
    raw = await file.read()
    service = ImportedAccountsService(db)
    try:
        return service.import_file(
            account_id=account_id,
            raw=raw,
            filename=file.filename or "upload",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Preview the first 5 mapped rows. Does not persist."""
    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="mapping is not valid JSON")
    raw = await file.read()
    service = ImportedAccountsService(db)
    try:
        return service.preview(
            raw=raw, filename=file.filename or "upload", mapping=mapping_dict
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/template")
async def download_template() -> Response:
    """Return a sample CSV the user can edit."""
    return Response(
        content=_TEMPLATE_CSV,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="finance-analysis-template.csv"',
        },
    )
```

- [ ] **Step 5: Register the router in `main.py`**

Open `backend/main.py`. Find the block where the other routers are registered (around line 247 onward). Add:

```python
from backend.routes import imported_accounts as imported_accounts_route
```

(at the top with the other route imports), and near the other `app.include_router` lines:

```python
app.include_router(
    imported_accounts_route.router,
    prefix="/api/imported-accounts",
    tags=["ImportedAccounts"],
)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/routes/test_imported_accounts_routes.py -v`
Expected: 7 PASSED.

- [ ] **Step 7: Spot-check the full backend suite still passes**

Run: `poetry run pytest`
Expected: full suite green. If anything else broke, fix before continuing.

- [ ] **Step 8: Commit**

```bash
git add backend/routes/imported_accounts.py backend/main.py backend/services/imported_accounts_service.py tests/backend/routes/test_imported_accounts_routes.py
git commit -m "feat(backend): /api/imported-accounts routes (CRUD + upload + preview + template)"
```

---

## Task 9: Frontend — types, API client, i18n keys

Pure-data foundation for the UI tasks that follow. No components yet.

**Files:**
- Create: `frontend/src/types/importedAccount.ts`
- Modify: `frontend/src/services/api.ts` (append `importedAccountsApi`)
- Modify: `frontend/src/locales/en.json` (new section `dataSources.import.*`)
- Modify: `frontend/src/locales/he.json` (same keys in Hebrew)

- [ ] **Step 1: Create the type module**

Create `frontend/src/types/importedAccount.ts`:

```ts
// Type definitions for the file-import data-source feature.
// Mirrors backend/services/file_import_parser.py + backend/routes/imported_accounts.py.

export type ImportService = "banks" | "credit_cards" | "cash";

export type AmountMode = "single" | "split";
export type SignConvention = "positive_is_income" | "positive_is_expense";

export type DateFormat =
  | "auto"
  | "iso"
  | "dd/mm/yyyy"
  | "mm/dd/yyyy"
  | "dd-mm-yyyy"
  | "dd.mm.yyyy"
  | "excel_serial";

export interface FieldRef {
  column: string | null;
  format?: DateFormat;
}

export type AmountMapping =
  | {
      mode: "single";
      column: string;
      sign_convention: SignConvention;
    }
  | {
      mode: "split";
      debit_column: string;
      credit_column: string;
    };

export interface ColumnMapping {
  skip_rows: number;
  date: { column: string; format: DateFormat };
  description: { column: string };
  amount: AmountMapping;
  category: FieldRef;
  tag: FieldRef;
  account_number: FieldRef;
}

export interface ImportedAccount {
  id: number;
  service: ImportService;
  provider: string;
  account_name: string;
  mapping: ColumnMapping;
}

export interface PreviewResponse {
  rows: Array<{
    date: string;
    description: string;
    amount: number;
    category?: string;
    tag?: string;
    account_number?: string;
  }>;
  dropped_invalid: number;
  raw_headers: string[];
}

export interface ImportSummary {
  inserted: number;
  skipped_duplicates: number;
  dropped_invalid: number;
}
```

- [ ] **Step 2: Append the API client block to `services/api.ts`**

Open `frontend/src/services/api.ts`. Add the import near the top:

```ts
import type {
  ColumnMapping,
  ImportedAccount,
  ImportSummary,
  PreviewResponse,
} from "../types/importedAccount";
```

Append after the existing API client blocks (anywhere logical near the end):

```ts
export const importedAccountsApi = {
  getAll: () => api.get<ImportedAccount[]>("/imported-accounts/"),
  create: (data: {
    service: string;
    provider: string;
    account_name: string;
    mapping: ColumnMapping;
  }) => api.post<ImportedAccount>("/imported-accounts/", data),
  updateMapping: (id: number, mapping: ColumnMapping) =>
    api.put<ImportedAccount>(`/imported-accounts/${id}`, { mapping }),
  delete: (id: number) => api.delete(`/imported-accounts/${id}`),
  upload: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post<ImportSummary>(`/imported-accounts/${id}/upload`, fd);
  },
  preview: (file: File, mapping: ColumnMapping) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mapping", JSON.stringify(mapping));
    return api.post<PreviewResponse>("/imported-accounts/preview", fd);
  },
  templateUrl: () => "/api/imported-accounts/template",
};
```

- [ ] **Step 3: Add i18n keys to `en.json`**

Open `frontend/src/locales/en.json`. Inside the `"dataSources"` section, add a new nested key `"import"` with all keys we'll need. Insert before the closing brace of `dataSources`:

```json
    "import": {
      "buttonLabel": "Import from File",
      "wizardTitle": "Import from a file",
      "editTitle": "Edit mapping",
      "stepServiceLabel": "What kind of account is this?",
      "stepMetaLabel": "Account details",
      "stepUploadLabel": "Upload your first file",
      "providerLabel": "Provider",
      "providerPlaceholder": "e.g. Hapoalim Manual, Discover, Generic",
      "accountNameLabel": "Account name",
      "accountNamePlaceholder": "e.g. Checking, Travel Card",
      "uploadDropzoneHint": "Drag a CSV or XLSX file here, or click to browse",
      "uploadFileTooLarge": "Files must be 10 MB or smaller",
      "uploadUnsupportedType": "Only .csv and .xlsx files are supported",
      "uploadButton": "Upload new file",
      "editMappingButton": "Edit mapping",
      "importedBadge": "Imported",
      "lastImport": "Last import",
      "mappingTitle": "Map columns",
      "mappingRawPreview": "Your file",
      "mappingMappedPreview": "How rows will be imported",
      "mappingSaveButton": "Save mapping & import",
      "mappingSaveOnlyButton": "Save mapping",
      "mappingValidationDate": "Pick a date column",
      "mappingValidationFormat": "Pick a date format",
      "mappingValidationDescription": "Pick a description column",
      "mappingValidationAmount": "Pick an amount column",
      "mappingValidationDebit": "Pick a debit column",
      "mappingValidationCredit": "Pick a credit column",
      "fieldDate": "Date column",
      "fieldDateFormat": "Date format",
      "fieldDescription": "Description column",
      "fieldAmountMode": "How is the amount represented?",
      "fieldAmountModeSingle": "Single signed column",
      "fieldAmountModeSplit": "Debit + Credit columns",
      "fieldAmountColumn": "Amount column",
      "fieldSignConvention": "Sign convention",
      "fieldSignPositiveIncome": "Positive = money in",
      "fieldSignPositiveExpense": "Positive = money out (most bank exports)",
      "fieldDebitColumn": "Debit column",
      "fieldCreditColumn": "Credit column",
      "fieldCategoryColumn": "Category column (optional)",
      "fieldTagColumn": "Tag column (optional)",
      "fieldAccountNumberColumn": "Account number column (optional)",
      "fieldSkipRows": "Skip rows above the header",
      "noneOption": "(none)",
      "dateFormatAuto": "Auto-detect",
      "dateFormatIso": "YYYY-MM-DD (ISO)",
      "dateFormatDdMmYyyy": "DD/MM/YYYY",
      "dateFormatMmDdYyyy": "MM/DD/YYYY",
      "dateFormatDdMmYyyyDash": "DD-MM-YYYY",
      "dateFormatDdMmYyyyDot": "DD.MM.YYYY",
      "dateFormatExcelSerial": "Excel serial",
      "docsTitle": "Expected file format",
      "docsRequired": "Required columns: date, description, and either one signed amount column or a debit + credit pair.",
      "docsOptional": "Optional columns: category, tag, account number.",
      "docsTypes": "Supported file types: .csv (UTF-8 or Windows-1255) and .xlsx.",
      "docsSign": "If your file shows expenses as positive numbers (most bank exports), pick that option in the mapping — we'll flip the sign so expenses are stored as negative.",
      "docsBanner": "If your file has banner rows above the actual column names, set Skip rows to the number of rows to ignore.",
      "docsTemplate": "Download template CSV",
      "importSummary": "Imported {{inserted}} new transactions, skipped {{duplicates}} duplicates, dropped {{invalid}} invalid rows.",
      "importFailed": "Couldn't import the file. Check the mapping and try again.",
      "deleteConfirmTitle": "Delete imported account",
      "deleteConfirmMessage": "Delete {{name}}? This will also delete all transactions imported from this account.",
      "createSuccess": "Imported account created."
    }
```

- [ ] **Step 4: Add the same keys (translated) to `he.json`**

Open `frontend/src/locales/he.json`. Inside `"dataSources"`, add the matching `"import"` section. Keep the JSON structure identical to `en.json`; only the right-hand strings change.

```json
    "import": {
      "buttonLabel": "ייבוא מקובץ",
      "wizardTitle": "ייבוא מקובץ",
      "editTitle": "עריכת מיפוי",
      "stepServiceLabel": "איזה סוג חשבון זה?",
      "stepMetaLabel": "פרטי חשבון",
      "stepUploadLabel": "העלאת הקובץ הראשון",
      "providerLabel": "ספק",
      "providerPlaceholder": "לדוגמה: הפועלים ידני, Discover, גנרי",
      "accountNameLabel": "שם החשבון",
      "accountNamePlaceholder": "לדוגמה: עו״ש, כרטיס נסיעות",
      "uploadDropzoneHint": "גרור קובץ CSV או XLSX לכאן, או לחץ לבחירה",
      "uploadFileTooLarge": "הקובץ חייב להיות עד 10MB",
      "uploadUnsupportedType": "נתמכים רק קבצי .csv ו-.xlsx",
      "uploadButton": "העלאת קובץ חדש",
      "editMappingButton": "עריכת מיפוי",
      "importedBadge": "מיובא",
      "lastImport": "ייבוא אחרון",
      "mappingTitle": "מיפוי עמודות",
      "mappingRawPreview": "הקובץ שלך",
      "mappingMappedPreview": "איך השורות יוכנסו",
      "mappingSaveButton": "שמור מיפוי וייבא",
      "mappingSaveOnlyButton": "שמור מיפוי",
      "mappingValidationDate": "בחר עמודת תאריך",
      "mappingValidationFormat": "בחר פורמט תאריך",
      "mappingValidationDescription": "בחר עמודת תיאור",
      "mappingValidationAmount": "בחר עמודת סכום",
      "mappingValidationDebit": "בחר עמודת חובה",
      "mappingValidationCredit": "בחר עמודת זכות",
      "fieldDate": "עמודת תאריך",
      "fieldDateFormat": "פורמט תאריך",
      "fieldDescription": "עמודת תיאור",
      "fieldAmountMode": "איך מיוצג הסכום?",
      "fieldAmountModeSingle": "עמודה אחת עם סימן",
      "fieldAmountModeSplit": "עמודות חובה + זכות",
      "fieldAmountColumn": "עמודת סכום",
      "fieldSignConvention": "מוסכמת סימן",
      "fieldSignPositiveIncome": "חיובי = הכנסה",
      "fieldSignPositiveExpense": "חיובי = הוצאה (רוב הייצואים של הבנקים)",
      "fieldDebitColumn": "עמודת חובה",
      "fieldCreditColumn": "עמודת זכות",
      "fieldCategoryColumn": "עמודת קטגוריה (אופציונלי)",
      "fieldTagColumn": "עמודת תג (אופציונלי)",
      "fieldAccountNumberColumn": "עמודת מספר חשבון (אופציונלי)",
      "fieldSkipRows": "דלג על שורות שמעל הכותרת",
      "noneOption": "(ללא)",
      "dateFormatAuto": "זיהוי אוטומטי",
      "dateFormatIso": "YYYY-MM-DD (ISO)",
      "dateFormatDdMmYyyy": "DD/MM/YYYY",
      "dateFormatMmDdYyyy": "MM/DD/YYYY",
      "dateFormatDdMmYyyyDash": "DD-MM-YYYY",
      "dateFormatDdMmYyyyDot": "DD.MM.YYYY",
      "dateFormatExcelSerial": "Excel סידורי",
      "docsTitle": "פורמט קובץ צפוי",
      "docsRequired": "עמודות חובה: תאריך, תיאור, ועמודת סכום עם סימן או זוג חובה + זכות.",
      "docsOptional": "עמודות אופציונליות: קטגוריה, תג, מספר חשבון.",
      "docsTypes": "סוגי קבצים נתמכים: .csv (UTF-8 או Windows-1255) ו-.xlsx.",
      "docsSign": "אם הקובץ שלך מציג הוצאות כמספרים חיוביים (רוב הייצואים של הבנקים), בחר באפשרות זו במיפוי — נהפוך את הסימן כדי שהוצאות יישמרו שליליות.",
      "docsBanner": "אם בקובץ יש שורות באנר מעל הכותרת, קבע ״דלג על שורות״ למספר השורות שיש לדלג עליהן.",
      "docsTemplate": "הורד CSV לדוגמה",
      "importSummary": "יובאו {{inserted}} עסקאות חדשות, דולגו {{duplicates}} כפילויות, נזרקו {{invalid}} שורות לא תקינות.",
      "importFailed": "הייבוא נכשל. בדוק את המיפוי ונסה שוב.",
      "deleteConfirmTitle": "מחיקת חשבון מיובא",
      "deleteConfirmMessage": "למחוק את {{name}}? גם כל העסקאות שיובאו מחשבון זה יימחקו.",
      "createSuccess": "החשבון המיובא נוצר."
    }
```

- [ ] **Step 5: Confirm both locale files still parse**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/en.json')); JSON.parse(require('fs').readFileSync('src/locales/he.json')); console.log('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/importedAccount.ts frontend/src/services/api.ts frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(frontend): types, API client, i18n for file import"
```

---

## Task 10: `ColumnMappingWizard` + `MappingPreviewTable`

The core of the new UI. Pure presentational + local-state — no API calls, just produces a `ColumnMapping` and emits it via `onSave`. The parent (Task 11) wires `onSave` to the create/update API.

**Files:**
- Create: `frontend/src/components/dataSources/MappingPreviewTable.tsx`
- Create: `frontend/src/components/dataSources/ColumnMappingWizard.tsx`
- Create: `frontend/src/components/dataSources/ColumnMappingWizard.test.tsx`

- [ ] **Step 1: Write the failing component test**

Create `frontend/src/components/dataSources/ColumnMappingWizard.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ColumnMappingWizard } from "./ColumnMappingWizard";

// Stub out the preview API call so the test doesn't hit the network.
vi.mock("../../services/api", () => ({
  importedAccountsApi: {
    preview: vi.fn().mockResolvedValue({
      data: {
        rows: [
          { date: "2026-03-01", description: "Coffee", amount: -12.5 },
        ],
        dropped_invalid: 0,
        raw_headers: ["date", "description", "amount"],
      },
    }),
    templateUrl: () => "/api/imported-accounts/template",
  },
}));

const FILE = new File(
  ["date,description,amount\n2026-03-01,Coffee,-12.5\n"],
  "test.csv",
  { type: "text/csv" },
);

describe("ColumnMappingWizard", () => {
  it("blocks save until required fields are mapped", async () => {
    const onSave = vi.fn();
    render(<ColumnMappingWizard file={FILE} initialMapping={null} onSave={onSave} />);
    // Save button starts disabled because no date column is picked yet.
    const saveBtn = await screen.findByRole("button", { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it("emits a complete ColumnMapping when the user fills in required fields", async () => {
    const onSave = vi.fn();
    render(<ColumnMappingWizard file={FILE} initialMapping={null} onSave={onSave} />);

    // Wait for the headers to load
    await screen.findByText(/date/i);

    // Pick date column
    fireEvent.change(screen.getByLabelText(/date column/i), {
      target: { value: "date" },
    });
    // Pick description column
    fireEvent.change(screen.getByLabelText(/description column/i), {
      target: { value: "description" },
    });
    // Pick amount column
    fireEvent.change(screen.getByLabelText(/^amount column/i), {
      target: { value: "amount" },
    });

    const saveBtn = await screen.findByRole("button", { name: /save/i });
    await waitFor(() => expect(saveBtn).not.toBeDisabled());
    fireEvent.click(saveBtn);
    expect(onSave).toHaveBeenCalledTimes(1);
    const mapping = onSave.mock.calls[0][0];
    expect(mapping.date.column).toBe("date");
    expect(mapping.amount.mode).toBe("single");
    expect(mapping.amount.column).toBe("amount");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --run ColumnMappingWizard`
Expected: FAIL — component not found.

- [ ] **Step 3: Create `MappingPreviewTable.tsx`**

Create `frontend/src/components/dataSources/MappingPreviewTable.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

interface PreviewRow {
  date: string;
  description: string;
  amount: number;
  category?: string;
  tag?: string;
}

interface Props {
  rows: PreviewRow[];
}

/**
 * Read-only table showing how the first few rows of an uploaded file
 * will look after the column mapping is applied.
 */
export function MappingPreviewTable({ rows }: Props) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <div className="text-xs text-[var(--text-muted)] italic">
        {t("dataSources.import.mappingMappedPreview")}…
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--surface-light)]">
      <table className="w-full min-w-[480px] text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)] bg-[var(--surface-light)]/40">
            <th className="text-start px-3 py-2 font-bold whitespace-nowrap">
              {t("common.date")}
            </th>
            <th className="text-start px-3 py-2 font-bold whitespace-nowrap">
              {t("common.description")}
            </th>
            <th className="text-center px-3 py-2 font-bold whitespace-nowrap">
              {t("common.amount")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={`${row.date}-${idx}`}
              className="border-b border-[var(--surface-light)]/40"
            >
              <td className="text-start px-3 py-2 whitespace-nowrap font-mono">
                {row.date}
              </td>
              <td
                className="text-start px-3 py-2 whitespace-nowrap truncate max-w-[240px]"
                dir="auto"
              >
                {row.description}
              </td>
              <td className="text-center px-3 py-2 whitespace-nowrap">
                <span dir="ltr">{formatCurrency(row.amount)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Create `ColumnMappingWizard.tsx`**

Create `frontend/src/components/dataSources/ColumnMappingWizard.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { importedAccountsApi } from "../../services/api";
import type {
  AmountMode,
  ColumnMapping,
  DateFormat,
  SignConvention,
} from "../../types/importedAccount";
import { MappingPreviewTable } from "./MappingPreviewTable";

interface Props {
  file: File;
  initialMapping: ColumnMapping | null;
  saveLabelKey?: "dataSources.import.mappingSaveButton" | "dataSources.import.mappingSaveOnlyButton";
  onSave: (mapping: ColumnMapping) => void;
}

const DATE_FORMATS: DateFormat[] = [
  "auto",
  "iso",
  "dd/mm/yyyy",
  "mm/dd/yyyy",
  "dd-mm-yyyy",
  "dd.mm.yyyy",
  "excel_serial",
];

const DATE_FORMAT_LABEL_KEY: Record<DateFormat, string> = {
  auto: "dataSources.import.dateFormatAuto",
  iso: "dataSources.import.dateFormatIso",
  "dd/mm/yyyy": "dataSources.import.dateFormatDdMmYyyy",
  "mm/dd/yyyy": "dataSources.import.dateFormatMmDdYyyy",
  "dd-mm-yyyy": "dataSources.import.dateFormatDdMmYyyyDash",
  "dd.mm.yyyy": "dataSources.import.dateFormatDdMmYyyyDot",
  excel_serial: "dataSources.import.dateFormatExcelSerial",
};

function emptyMapping(): ColumnMapping {
  return {
    skip_rows: 0,
    date: { column: "", format: "auto" },
    description: { column: "" },
    amount: {
      mode: "single",
      column: "",
      sign_convention: "positive_is_income",
    },
    category: { column: null },
    tag: { column: null },
    account_number: { column: null },
  };
}

/**
 * Mapping form + live preview. Pure local state — the parent decides
 * what to do with the produced mapping (create account, update mapping,
 * etc.) via `onSave`.
 */
export function ColumnMappingWizard({
  file,
  initialMapping,
  saveLabelKey = "dataSources.import.mappingSaveButton",
  onSave,
}: Props) {
  const { t } = useTranslation();
  const [mapping, setMapping] = useState<ColumnMapping>(
    initialMapping ?? emptyMapping(),
  );
  const [headers, setHeaders] = useState<string[]>([]);
  const [previewRows, setPreviewRows] = useState<
    Array<{ date: string; description: string; amount: number }>
  >([]);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Whenever the mapping changes meaningfully, re-fetch the preview.
  useEffect(() => {
    let cancelled = false;
    importedAccountsApi
      .preview(file, mapping)
      .then((resp) => {
        if (cancelled) return;
        setHeaders(resp.data.raw_headers);
        setPreviewRows(resp.data.rows);
        setPreviewError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setPreviewRows([]);
        setPreviewError(t("dataSources.import.importFailed"));
      });
    return () => {
      cancelled = true;
    };
  }, [file, mapping, t]);

  const isValid = useMemo(() => isMappingValid(mapping), [mapping]);

  return (
    <div className="space-y-4">
      {previewError && (
        <div className="text-xs text-red-400">{previewError}</div>
      )}

      {/* Mapping form */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Date column */}
        <Labeled label={t("dataSources.import.fieldDate")} htmlFor="map-date">
          <ColumnSelect
            id="map-date"
            value={mapping.date.column}
            headers={headers}
            onChange={(v) =>
              setMapping((m) => ({ ...m, date: { ...m.date, column: v } }))
            }
          />
        </Labeled>

        {/* Date format */}
        <Labeled
          label={t("dataSources.import.fieldDateFormat")}
          htmlFor="map-date-format"
        >
          <select
            id="map-date-format"
            value={mapping.date.format}
            onChange={(e) =>
              setMapping((m) => ({
                ...m,
                date: { ...m.date, format: e.target.value as DateFormat },
              }))
            }
            className={selectCls}
          >
            {DATE_FORMATS.map((f) => (
              <option key={f} value={f}>
                {t(DATE_FORMAT_LABEL_KEY[f])}
              </option>
            ))}
          </select>
        </Labeled>

        {/* Description column */}
        <Labeled
          label={t("dataSources.import.fieldDescription")}
          htmlFor="map-desc"
        >
          <ColumnSelect
            id="map-desc"
            value={mapping.description.column}
            headers={headers}
            onChange={(v) =>
              setMapping((m) => ({ ...m, description: { column: v } }))
            }
          />
        </Labeled>

        {/* Amount mode */}
        <Labeled label={t("dataSources.import.fieldAmountMode")} htmlFor="">
          <div className="flex gap-2 text-xs">
            {(["single", "split"] as AmountMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() =>
                  setMapping((m) => ({
                    ...m,
                    amount:
                      mode === "single"
                        ? {
                            mode: "single",
                            column: "",
                            sign_convention: "positive_is_income",
                          }
                        : { mode: "split", debit_column: "", credit_column: "" },
                  }))
                }
                className={`flex-1 px-3 py-2 rounded-lg border ${
                  mapping.amount.mode === mode
                    ? "border-[var(--primary)] bg-[var(--primary)]/10"
                    : "border-[var(--surface-light)]"
                }`}
              >
                {t(
                  mode === "single"
                    ? "dataSources.import.fieldAmountModeSingle"
                    : "dataSources.import.fieldAmountModeSplit",
                )}
              </button>
            ))}
          </div>
        </Labeled>

        {/* Amount fields conditional on mode */}
        {mapping.amount.mode === "single" ? (
          <>
            <Labeled
              label={t("dataSources.import.fieldAmountColumn")}
              htmlFor="map-amt"
            >
              <ColumnSelect
                id="map-amt"
                value={mapping.amount.column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "single"
                      ? { ...m, amount: { ...m.amount, column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
            <Labeled
              label={t("dataSources.import.fieldSignConvention")}
              htmlFor="map-sign"
            >
              <select
                id="map-sign"
                value={mapping.amount.sign_convention}
                onChange={(e) =>
                  setMapping((m) =>
                    m.amount.mode === "single"
                      ? {
                          ...m,
                          amount: {
                            ...m.amount,
                            sign_convention: e.target.value as SignConvention,
                          },
                        }
                      : m,
                  )
                }
                className={selectCls}
              >
                <option value="positive_is_income">
                  {t("dataSources.import.fieldSignPositiveIncome")}
                </option>
                <option value="positive_is_expense">
                  {t("dataSources.import.fieldSignPositiveExpense")}
                </option>
              </select>
            </Labeled>
          </>
        ) : (
          <>
            <Labeled
              label={t("dataSources.import.fieldDebitColumn")}
              htmlFor="map-debit"
            >
              <ColumnSelect
                id="map-debit"
                value={mapping.amount.debit_column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "split"
                      ? { ...m, amount: { ...m.amount, debit_column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
            <Labeled
              label={t("dataSources.import.fieldCreditColumn")}
              htmlFor="map-credit"
            >
              <ColumnSelect
                id="map-credit"
                value={mapping.amount.credit_column}
                headers={headers}
                onChange={(v) =>
                  setMapping((m) =>
                    m.amount.mode === "split"
                      ? { ...m, amount: { ...m.amount, credit_column: v } }
                      : m,
                  )
                }
              />
            </Labeled>
          </>
        )}

        {/* Optional category */}
        <Labeled
          label={t("dataSources.import.fieldCategoryColumn")}
          htmlFor="map-cat"
        >
          <ColumnSelect
            id="map-cat"
            value={mapping.category.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({
                ...m,
                category: { column: v || null },
              }))
            }
          />
        </Labeled>

        {/* Optional tag */}
        <Labeled
          label={t("dataSources.import.fieldTagColumn")}
          htmlFor="map-tag"
        >
          <ColumnSelect
            id="map-tag"
            value={mapping.tag.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({ ...m, tag: { column: v || null } }))
            }
          />
        </Labeled>

        {/* Optional account number */}
        <Labeled
          label={t("dataSources.import.fieldAccountNumberColumn")}
          htmlFor="map-acc"
        >
          <ColumnSelect
            id="map-acc"
            value={mapping.account_number.column ?? ""}
            headers={headers}
            allowNone
            onChange={(v) =>
              setMapping((m) => ({
                ...m,
                account_number: { column: v || null },
              }))
            }
          />
        </Labeled>

        {/* Skip rows */}
        <Labeled
          label={t("dataSources.import.fieldSkipRows")}
          htmlFor="map-skip"
        >
          <input
            id="map-skip"
            type="number"
            min={0}
            value={mapping.skip_rows}
            onChange={(e) =>
              setMapping((m) => ({
                ...m,
                skip_rows: Number.parseInt(e.target.value || "0", 10),
              }))
            }
            className={selectCls}
          />
        </Labeled>
      </div>

      {/* Live mapped preview */}
      <div>
        <h4 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-widest mb-2">
          {t("dataSources.import.mappingMappedPreview")}
        </h4>
        <MappingPreviewTable rows={previewRows} />
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          disabled={!isValid}
          onClick={() => onSave(mapping)}
          className="px-5 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold disabled:opacity-50"
        >
          {t(saveLabelKey)}
        </button>
      </div>
    </div>
  );
}

// ----- helpers -----

const selectCls =
  "w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-3 py-2 text-sm outline-none focus:border-[var(--primary)]";

function Labeled({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5"
      >
        {label}
      </label>
      {children}
    </div>
  );
}

interface ColumnSelectProps {
  id: string;
  value: string;
  headers: string[];
  allowNone?: boolean;
  onChange: (v: string) => void;
}

function ColumnSelect({
  id,
  value,
  headers,
  allowNone,
  onChange,
}: ColumnSelectProps) {
  const { t } = useTranslation();
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={selectCls}
    >
      <option value="">
        {allowNone ? t("dataSources.import.noneOption") : "—"}
      </option>
      {headers.map((h) => (
        <option key={h} value={h}>
          {h}
        </option>
      ))}
    </select>
  );
}

function isMappingValid(m: ColumnMapping): boolean {
  if (!m.date.column || !m.date.format) return false;
  if (!m.description.column) return false;
  if (m.amount.mode === "single") {
    if (!m.amount.column || !m.amount.sign_convention) return false;
  } else {
    if (!m.amount.debit_column || !m.amount.credit_column) return false;
  }
  return true;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- --run ColumnMappingWizard`
Expected: 2 PASSED.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dataSources/MappingPreviewTable.tsx frontend/src/components/dataSources/ColumnMappingWizard.tsx frontend/src/components/dataSources/ColumnMappingWizard.test.tsx
git commit -m "feat(frontend): ColumnMappingWizard + MappingPreviewTable"
```

---

## Task 11: Wizard shell — `ImportAccountWizard`, `ImportFileButton`, `UploadFileDropzone`, `FormatDocsCallout`

The wrapper that ties everything together: the 3-step modal flow (service → metadata → upload+map). Reused for "Edit mapping" by skipping steps 1–2.

**Files:**
- Create: `frontend/src/components/dataSources/UploadFileDropzone.tsx`
- Create: `frontend/src/components/dataSources/FormatDocsCallout.tsx`
- Create: `frontend/src/components/dataSources/ImportFileButton.tsx`
- Create: `frontend/src/components/dataSources/ImportAccountWizard.tsx`

Tests for the wizard shell are deliberately light — the meat is in `ColumnMappingWizard.test.tsx` (Task 10) and the Playwright spec (Task 14). The DataSources merging/rendering tests get an update in Task 12.

- [ ] **Step 1: Create `FormatDocsCallout.tsx`**

Create `frontend/src/components/dataSources/FormatDocsCallout.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { Info, Download } from "lucide-react";

import { importedAccountsApi } from "../../services/api";

/**
 * Inline help block above the upload dropzone. Lists what columns the
 * importer expects and links to a downloadable template CSV.
 */
export function FormatDocsCallout() {
  const { t } = useTranslation();
  return (
    <div className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/15 space-y-2">
      <div className="flex items-center gap-2 text-blue-400">
        <Info size={16} />
        <span className="text-xs font-bold uppercase tracking-widest">
          {t("dataSources.import.docsTitle")}
        </span>
      </div>
      <ul className="text-xs text-blue-400/85 space-y-1 list-disc list-inside">
        <li>{t("dataSources.import.docsRequired")}</li>
        <li>{t("dataSources.import.docsOptional")}</li>
        <li>{t("dataSources.import.docsTypes")}</li>
        <li>{t("dataSources.import.docsSign")}</li>
        <li>{t("dataSources.import.docsBanner")}</li>
      </ul>
      <a
        href={importedAccountsApi.templateUrl()}
        download
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-300 hover:text-blue-200 underline"
      >
        <Download size={14} />
        {t("dataSources.import.docsTemplate")}
      </a>
    </div>
  );
}
```

- [ ] **Step 2: Create `UploadFileDropzone.tsx`**

Create `frontend/src/components/dataSources/UploadFileDropzone.tsx`:

```tsx
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadCloud } from "lucide-react";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".csv,.xlsx";

interface Props {
  onFile: (file: File) => void;
}

/**
 * Drag-and-drop file zone with click-to-browse fallback. Enforces
 * 10 MB size cap and .csv/.xlsx extension whitelist.
 */
export function UploadFileDropzone({ onFile }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  function validateAndEmit(file: File) {
    if (file.size > MAX_BYTES) {
      setError(t("dataSources.import.uploadFileTooLarge"));
      return;
    }
    const name = file.name.toLowerCase();
    if (!name.endsWith(".csv") && !name.endsWith(".xlsx")) {
      setError(t("dataSources.import.uploadUnsupportedType"));
      return;
    }
    setError(null);
    onFile(file);
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) validateAndEmit(file);
        }}
        className={`w-full flex flex-col items-center justify-center gap-2 p-8 rounded-2xl border-2 border-dashed transition-colors ${
          isDragOver
            ? "border-[var(--primary)] bg-[var(--primary)]/5"
            : "border-[var(--surface-light)]"
        }`}
      >
        <UploadCloud size={32} className="text-[var(--text-muted)]" />
        <span className="text-sm text-[var(--text-muted)]">
          {t("dataSources.import.uploadDropzoneHint")}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) validateAndEmit(file);
          // reset so re-selecting the same file fires onChange.
          e.target.value = "";
        }}
      />
      {error && <div className="text-xs text-red-400">{error}</div>}
    </div>
  );
}
```

- [ ] **Step 3: Create `ImportAccountWizard.tsx`**

Create `frontend/src/components/dataSources/ImportAccountWizard.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Landmark, CreditCard, DollarSign, ChevronRight } from "lucide-react";

import { Modal } from "../common/Modal";
import { importedAccountsApi } from "../../services/api";
import { useNotify } from "../../context/DialogContext";
import type {
  ColumnMapping,
  ImportService,
  ImportedAccount,
  ImportSummary,
} from "../../types/importedAccount";
import { FormatDocsCallout } from "./FormatDocsCallout";
import { UploadFileDropzone } from "./UploadFileDropzone";
import { ColumnMappingWizard } from "./ColumnMappingWizard";

interface CreateProps {
  mode: "create";
  isOpen: boolean;
  onClose: () => void;
}

interface EditProps {
  mode: "edit-mapping";
  isOpen: boolean;
  onClose: () => void;
  account: ImportedAccount;
}

type Props = CreateProps | EditProps;

/**
 * 3-step modal: service → metadata → upload + map.
 *
 * For mode="edit-mapping", steps 1–2 are skipped and the upload step
 * leads to a mapping wizard pre-filled with the saved mapping. Saving
 * updates `mapping_json` only; no import is run.
 */
export function ImportAccountWizard(props: Props) {
  const { t } = useTranslation();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const isEdit = props.mode === "edit-mapping";

  const [step, setStep] = useState<1 | 2 | 3>(isEdit ? 3 : 1);
  const [service, setService] = useState<ImportService | "">(
    isEdit ? props.account.service : "",
  );
  const [provider, setProvider] = useState(isEdit ? props.account.provider : "");
  const [accountName, setAccountName] = useState(
    isEdit ? props.account.account_name : "",
  );
  const [file, setFile] = useState<File | null>(null);

  const createMutation = useMutation({
    mutationFn: async (mapping: ColumnMapping) => {
      const created = await importedAccountsApi.create({
        service,
        provider,
        account_name: accountName,
        mapping,
      });
      // Immediately run the first import.
      const summary = await importedAccountsApi.upload(
        created.data.id,
        file as File,
      );
      return { created: created.data, summary: summary.data };
    },
    onSuccess: ({ summary }) => {
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] });
      notify.success(
        t("dataSources.import.importSummary", {
          inserted: summary.inserted,
          duplicates: summary.skipped_duplicates,
          invalid: summary.dropped_invalid,
        }),
      );
      reset();
      props.onClose();
    },
    onError: () => notify.error(t("dataSources.import.importFailed")),
  });

  const updateMappingMutation = useMutation({
    mutationFn: (mapping: ColumnMapping) => {
      if (!isEdit) throw new Error("not in edit mode");
      return importedAccountsApi.updateMapping(props.account.id, mapping);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] });
      notify.success(t("dataSources.import.createSuccess"));
      reset();
      props.onClose();
    },
    onError: () => notify.error(t("dataSources.import.importFailed")),
  });

  function reset() {
    setStep(isEdit ? 3 : 1);
    if (!isEdit) {
      setService("");
      setProvider("");
      setAccountName("");
    }
    setFile(null);
  }

  return (
    <Modal
      isOpen={props.isOpen}
      onClose={props.onClose}
      title={t(isEdit ? "dataSources.import.editTitle" : "dataSources.import.wizardTitle")}
      maxWidth="2xl"
    >
      <div className="p-4 md:p-6 space-y-4 overflow-y-auto">
        {/* Progress dots (creation only) */}
        {!isEdit && (
          <div className="flex gap-2 mb-2">
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-1.5 flex-1 rounded-full transition-all ${
                  step >= s ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"
                }`}
              />
            ))}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-[var(--text-muted)] text-sm">
              {t("dataSources.import.stepServiceLabel")}
            </p>
            <ServicePickRow
              icon={<Landmark size={22} />}
              label={t("dataSources.bankAccount")}
              onClick={() => {
                setService("banks");
                setStep(2);
              }}
            />
            <ServicePickRow
              icon={<CreditCard size={22} />}
              label={t("dataSources.creditCard")}
              onClick={() => {
                setService("credit_cards");
                setStep(2);
              }}
            />
            <ServicePickRow
              icon={<DollarSign size={22} />}
              label={t("dataSources.cash") /* existing key in dataSources.* */}
              onClick={() => {
                setService("cash");
                setStep(2);
              }}
            />
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-[var(--text-muted)] text-sm">
              {t("dataSources.import.stepMetaLabel")}
            </p>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
                {t("dataSources.import.providerLabel")}
              </label>
              <input
                type="text"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder={t("dataSources.import.providerPlaceholder")}
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-sm outline-none focus:border-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
                {t("dataSources.import.accountNameLabel")}
              </label>
              <input
                type="text"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                placeholder={t("dataSources.import.accountNamePlaceholder")}
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-sm outline-none focus:border-[var(--primary)]"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-4 py-2 text-sm text-[var(--text-muted)] hover:text-white"
              >
                {t("common.back")}
              </button>
              <button
                type="button"
                disabled={!provider.trim() || !accountName.trim()}
                onClick={() => setStep(3)}
                className="px-5 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold disabled:opacity-50"
              >
                {t("common.next") /* existing key */}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            {!isEdit && <FormatDocsCallout />}
            {!file ? (
              <UploadFileDropzone onFile={setFile} />
            ) : (
              <ColumnMappingWizard
                file={file}
                initialMapping={isEdit ? props.account.mapping : null}
                saveLabelKey={
                  isEdit
                    ? "dataSources.import.mappingSaveOnlyButton"
                    : "dataSources.import.mappingSaveButton"
                }
                onSave={(mapping) => {
                  if (isEdit) {
                    updateMappingMutation.mutate(mapping);
                  } else {
                    createMutation.mutate(mapping);
                  }
                }}
              />
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function ServicePickRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between p-4 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all"
    >
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)]">
          {icon}
        </div>
        <span className="font-bold text-base text-white">{label}</span>
      </div>
      <ChevronRight className="text-[var(--text-muted)]" />
    </button>
  );
}
```

- [ ] **Step 4: Create `ImportFileButton.tsx`**

Create `frontend/src/components/dataSources/ImportFileButton.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp } from "lucide-react";

import { ImportAccountWizard } from "./ImportAccountWizard";

/**
 * Top-level "Import from File" button + creation wizard.
 */
export function ImportFileButton() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] text-white rounded-xl font-bold hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all"
      >
        <FileUp size={16} />
        {t("dataSources.import.buttonLabel")}
      </button>
      {isOpen && (
        <ImportAccountWizard
          mode="create"
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 5: Confirm the existing locale already has `common.back`, `common.next`, `dataSources.cash`**

Run:
```bash
grep -E '"back"|"next"' frontend/src/locales/en.json
grep '"cash"' frontend/src/locales/en.json
```
If `dataSources.cash` doesn't exist, add it now to both locale files:
- en: `"cash": "Cash Envelope",`
- he: `"cash": "מעטפת מזומן",`
If `common.next` doesn't exist either, add it: `"next": "Next"` / `"הבא"`.

- [ ] **Step 6: Run frontend tests to make sure nothing regressed**

Run: `cd frontend && npm test -- --run`
Expected: all tests still PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/dataSources/
git add frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(frontend): ImportAccountWizard shell + dropzone + format docs"
```

---

## Task 12: `DataSources.tsx` — merge lists, Upload action, Imported badge, edit-mapping flow

The biggest frontend diff. Adds a second `useQuery` for imported accounts, builds a merged list keyed by `origin`, and branches the card rendering to swap the scrape button for an upload button on imported cards.

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx`
- Modify: `frontend/src/pages/DataSources.test.tsx`

- [ ] **Step 1: Extend the test file with a new test**

Open `frontend/src/pages/DataSources.test.tsx`. Add a new test (keep the existing ones). The shape below assumes the file already mocks the credentials/scraping APIs and exposes a render helper; adapt to whatever helpers exist in the file:

```tsx
import { vi } from "vitest";

// At the top of the file, add a mock for importedAccountsApi alongside the
// existing mocks for credentialsApi. If the file already mocks
// "../services/api", extend that mock object instead of creating a second one.
vi.mock("../services/api", async (original) => {
  const actual = (await original()) as object;
  return {
    ...actual,
    importedAccountsApi: {
      getAll: vi.fn().mockResolvedValue({
        data: [
          {
            id: 99,
            service: "banks",
            provider: "Hapoalim Manual",
            account_name: "Imported Checking",
            mapping: { skip_rows: 0 },
          },
        ],
      }),
      delete: vi.fn(),
      templateUrl: () => "/api/imported-accounts/template",
    },
  };
});

it("renders imported accounts alongside scraped accounts with an Imported badge and Upload action", async () => {
  /* render the DataSources page using whatever helper the file already uses */
  // Once the page mounts and queries resolve:
  expect(await screen.findByText("Imported Checking")).toBeInTheDocument();
  expect(screen.getByText(/imported/i)).toBeInTheDocument();
  // Upload action shows for imported account.
  expect(screen.getByLabelText(/upload new file/i)).toBeInTheDocument();
});
```

If the test file doesn't have a render helper, use the same imports the existing tests use (e.g. `render(<QueryClientProvider…><DataSources /></QueryClientProvider>)`). Re-running the existing tests in the file should still pass after your changes.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- --run DataSources`
Expected: the new test fails because the page doesn't render imported accounts yet. Existing tests should still pass.

- [ ] **Step 3: Edit `DataSources.tsx`**

Open `frontend/src/pages/DataSources.tsx`.

3a. Add imports near the top:

```tsx
import { Upload, FileSpreadsheet } from "lucide-react";
import { importedAccountsApi } from "../services/api";
import type { ImportedAccount } from "../types/importedAccount";
import { ImportFileButton } from "../components/dataSources/ImportFileButton";
import { ImportAccountWizard } from "../components/dataSources/ImportAccountWizard";
```

3b. Inside the component, alongside the existing `useQuery` for credentials accounts, add:

```tsx
  const { data: importedAccounts } = useQuery({
    queryKey: ["imported-accounts", isDemoMode],
    queryFn: () => importedAccountsApi.getAll().then((res) => res.data),
  });

  const deleteImportedMutation = useMutation({
    mutationFn: (id: number) => importedAccountsApi.delete(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] }),
  });

  const [editMappingFor, setEditMappingFor] = useState<ImportedAccount | null>(null);
  const [uploadingTo, setUploadingTo] = useState<ImportedAccount | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async ({ id, file }: { id: number; file: File }) => {
      const resp = await importedAccountsApi.upload(id, file);
      return resp.data;
    },
    onSuccess: (summary) => {
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] });
      notify.success(
        t("dataSources.import.importSummary", {
          inserted: summary.inserted,
          duplicates: summary.skipped_duplicates,
          invalid: summary.dropped_invalid,
        }),
      );
      setUploadingTo(null);
    },
    onError: () => notify.error(t("dataSources.import.importFailed")),
  });
```

3c. In the toolbar `<div>` at the top (where "Connect Account" lives), add the `ImportFileButton` immediately before the existing "Connect Account" button:

```tsx
          <ImportFileButton />
          <button
            onClick={() => setIsAddOpen(true)}
            // … existing classes …
          >
            <Plus size={18} /> {t("dataSources.connectAccount")}
          </button>
```

3d. In the section that currently groups accounts (`bankAccounts`, `creditCardAccounts`, etc.), merge imported accounts in by service. Locate the IIFE that returns the section JSX (search for `bankAccounts = accounts?.filter`). Replace it with:

```tsx
          (() => {
            type MergedAccount =
              | { origin: "scraped"; row: CredentialAccount }
              | { origin: "imported"; row: ImportedAccount };

            const scraped: MergedAccount[] = (accounts ?? []).map((row: CredentialAccount) => ({
              origin: "scraped",
              row,
            }));
            const imported: MergedAccount[] = (importedAccounts ?? []).map((row) => ({
              origin: "imported",
              row,
            }));
            const merged = [...scraped, ...imported];

            const bySvc = (svc: string) =>
              merged.filter((m) =>
                m.origin === "scraped" ? m.row.service === svc : m.row.service === svc,
              );

            const bankItems = bySvc("banks");
            const ccItems = bySvc("credit_cards");
            const insItems = bySvc("insurances");
            const cashItems = bySvc("cash");

            const renderItem = (item: MergedAccount, idx: number) =>
              item.origin === "scraped"
                ? renderAccountCard(item.row, idx)
                : renderImportedCard(item.row, idx);

            return (
              <div className="space-y-4">
                {bankItems.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mb-2">
                      {t("dataSources.bankAccounts")}
                    </h3>
                    {bankItems.map(renderItem)}
                  </>
                )}
                {ccItems.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-6 mb-2">
                      {t("dataSources.creditCards")}
                    </h3>
                    {ccItems.map(renderItem)}
                  </>
                )}
                {cashItems.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-6 mb-2">
                      {t("dataSources.cash")}
                    </h3>
                    {cashItems.map(renderItem)}
                  </>
                )}
                {insItems.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-6 mb-2">
                      {t("dataSources.insurance")}
                    </h3>
                    {insItems.map(renderItem)}
                  </>
                )}
              </div>
            );
          })()
```

3e. Add the new `renderImportedCard` helper next to the existing `renderAccountCard`:

```tsx
            const renderImportedCard = (acc: ImportedAccount, idx: number) => (
              <div
                key={`imp-${acc.id}-${idx}`}
                className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-3 md:p-5 hover:border-[var(--primary)]/30 hover:shadow-xl transition-all"
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-0">
                  <div className="flex items-center gap-3 md:gap-5">
                    <div className="p-3.5 rounded-2xl bg-amber-500/10 text-amber-400">
                      <FileSpreadsheet size={24} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 mb-0.5">
                        <h3 className="font-bold text-lg text-white capitalize">
                          {acc.account_name}
                        </h3>
                        <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-amber-500/20 text-amber-400">
                          {t("dataSources.import.importedBadge")}
                        </span>
                      </div>
                      <p className="text-sm text-[var(--text-muted)] font-medium">
                        {acc.provider}
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setUploadingTo(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all"
                      aria-label={t("dataSources.import.uploadButton")}
                      title={t("dataSources.import.uploadButton")}
                    >
                      <Upload size={20} />
                    </button>
                    <button
                      onClick={() => setEditMappingFor(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all"
                      aria-label={t("dataSources.import.editMappingButton")}
                      title={t("dataSources.import.editMappingButton")}
                    >
                      <Edit2 size={20} />
                    </button>
                    <button
                      onClick={async () => {
                        const ok = await confirm({
                          title: t("dataSources.import.deleteConfirmTitle"),
                          message: t("dataSources.import.deleteConfirmMessage", {
                            name: acc.account_name,
                          }),
                          confirmLabel: t("dataSources.disconnectAccount"),
                          isDestructive: true,
                        });
                        if (ok) deleteImportedMutation.mutate(acc.id);
                      }}
                      className="p-2.5 rounded-xl bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-all"
                      aria-label={t("dataSources.import.deleteConfirmTitle")}
                      title={t("dataSources.import.deleteConfirmTitle")}
                    >
                      <Trash2 size={20} />
                    </button>
                  </div>
                </div>
              </div>
            );
```

3f. At the bottom of the JSX (before the closing `</div>` of the main page wrapper), add modals for the upload-to-existing and edit-mapping flows:

```tsx
      {/* Upload to existing imported account */}
      {uploadingTo && (
        <Modal
          isOpen={!!uploadingTo}
          onClose={() => setUploadingTo(null)}
          title={t("dataSources.import.uploadButton")}
          maxWidth="lg"
        >
          <div className="p-4 md:p-6">
            <UploadFileDropzone
              onFile={(file) =>
                uploadMutation.mutate({ id: uploadingTo.id, file })
              }
            />
          </div>
        </Modal>
      )}

      {/* Edit mapping */}
      {editMappingFor && (
        <ImportAccountWizard
          mode="edit-mapping"
          isOpen={!!editMappingFor}
          onClose={() => setEditMappingFor(null)}
          account={editMappingFor}
        />
      )}
```

You'll also need to import `Modal` and `UploadFileDropzone` at the top:

```tsx
import { Modal } from "../components/common/Modal";
import { UploadFileDropzone } from "../components/dataSources/UploadFileDropzone";
```

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npm test -- --run DataSources`
Expected: all tests pass, including the new "renders imported accounts" assertion.

- [ ] **Step 5: Run lint + build to catch type errors**

Run: `cd frontend && npm run lint && npm run build`
Expected: both succeed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/DataSources.tsx frontend/src/pages/DataSources.test.tsx
git commit -m "feat(frontend): merge imported accounts into Data Sources page"
```

---

## Task 13: Playwright e2e — golden path

One spec drives the entire flow: open the wizard, create a bank-typed imported account, drop a CSV, map columns, save, then visit the Transactions page and confirm rows are visible with the right sign and category.

**Files:**
- Create: `frontend/e2e/import-file.spec.ts`
- Create: `frontend/e2e/fixtures/import-sample.csv`

- [ ] **Step 1: Create the fixture CSV**

Create `frontend/e2e/fixtures/import-sample.csv`:

```
date,description,amount
2026-03-01,Coffee shop,-12.50
2026-03-03,Salary,8500.00
2026-03-05,Refund,45.00
```

- [ ] **Step 2: Create the spec**

Create `frontend/e2e/import-file.spec.ts`:

```ts
import path from "node:path";
import { test, expect } from "@playwright/test";
import {
  enableDemoMode,
  disableDemoMode,
  navigateTo,
} from "./helpers";

const FIXTURE = path.join(__dirname, "fixtures", "import-sample.csv");

test.describe("Import from File", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test("creates an imported bank account, maps columns, and shows the rows in Transactions", async ({
    page,
  }) => {
    await navigateTo(page, "/data-sources");

    // 1. Click the new "Import from File" button.
    await page.getByRole("button", { name: /import from file/i }).click();

    // 2. Step 1: pick service = bank.
    await page.getByRole("button", { name: /bank account/i }).first().click();

    // 3. Step 2: provider + account name.
    await page
      .getByPlaceholder(/hapoalim manual/i)
      .fill("Hapoalim Manual");
    await page
      .getByPlaceholder(/checking/i)
      .fill("Imported Checking");
    await page.getByRole("button", { name: /next/i }).click();

    // 4. Step 3: upload fixture file.
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(FIXTURE);

    // 5. Mapping form: pick columns.
    await page.getByLabel(/date column/i).selectOption("date");
    await page.getByLabel(/description column/i).selectOption("description");
    await page.getByLabel(/^amount column/i).selectOption("amount");

    // 6. Save and import.
    await page.getByRole("button", { name: /save mapping & import/i }).click();

    // Expect the success toast.
    await expect(page.getByText(/imported 3 new transactions/i)).toBeVisible({
      timeout: 10000,
    });

    // 7. Go to Transactions and confirm the rows are visible.
    await navigateTo(page, "/transactions");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText("Coffee shop")).toBeVisible();
    await expect(page.getByText("Salary")).toBeVisible();
  });
});
```

- [ ] **Step 3: Run the new e2e spec headlessly**

Run: `cd frontend && npm run test:e2e -- import-file`
Expected: 1 PASS. If Playwright complains the browser isn't installed, run `npx playwright install --with-deps chromium` first.

If the test fails because the demo mode DB persists between runs and the account already exists, add a small "delete leftover" step at the start of the test (DELETE /api/imported-accounts/{id} for any account named "Imported Checking").

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/import-file.spec.ts frontend/e2e/fixtures/
git commit -m "test(e2e): golden-path Playwright spec for file import"
```

---

## Task 14: Manual smoke + cleanup

A short verification pass to confirm everything hangs together end-to-end, plus tidying anything the build flagged.

- [ ] **Step 1: Run the full backend suite**

Run: `poetry run pytest`
Expected: full suite green.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`
Expected: tests pass, lint clean, build succeeds.

- [ ] **Step 3: Manually smoke against a real export**

Start the dev servers:

```bash
poetry run uvicorn backend.main:app --reload &
cd frontend && npm run dev
```

In a browser:

1. Open `http://localhost:5173/data-sources`.
2. Enable Demo Mode (Settings → Demo Mode).
3. Click "Import from File".
4. Create a bank-typed account with a provider name like "Hapoalim Test".
5. Upload an actual Hapoalim CSV export (or, if unavailable, the
   `tests/backend/unit/services/fixtures/imports/hapoalim_style.csv` fixture).
6. Configure the mapping: skip rows = 2, date format = DD/MM/YYYY, split-amount mode with the Hebrew column names.
7. Confirm the live preview shows rows with negative amounts for debits.
8. Save & import. Confirm the toast count matches the file row count.
9. Visit Transactions; filter by the new account name; verify rows appear with correct signs and that auto-tagging applied where rules existed.
10. Re-upload the same file; confirm "Imported 0 new transactions, skipped N duplicates".
11. Try Edit Mapping with a different format; confirm mapping persists; confirm no extra rows imported during the edit.
12. Delete the imported account; confirm its transactions are gone.
13. Disable Demo Mode.

- [ ] **Step 4: Address any issues found**

If the smoke reveals UI bugs (focus, RTL, mobile layout) follow the existing rules in `.claude/rules/testing.md` → "Verifying UI patches with Playwright" and add a regression test for each fix.

- [ ] **Step 5: Final commit if any cleanup landed**

```bash
git add -A
git status
# If anything is staged, commit it:
git commit -m "fix: smoke-test cleanup for file import"
```

- [ ] **Step 6: Open the PR**

Per `.claude/rules/ci_and_release.md` PRs target `dev`, not `main`. Push the branch and open the PR:

```bash
git push -u origin claude/priceless-lamport-a6ce68
gh pr create --base dev --title "feat: import transactions from CSV/XLSX files" --body "$(cat <<'EOF'
## Summary
- New "Import from File" data source on the Data Sources page
- Persistent column mapping per imported account (map once, reupload silently)
- Supports single-signed and debit/credit-split amount layouts; multiple date formats; UTF-8 + Windows-1255 CSVs and .xlsx
- Content-hash dedup on (date, description, amount) so re-uploading overlapping statements doesn't double-count
- Auto-tagging rules run for rows without mapped category/tag

Spec: `docs/superpowers/specs/2026-05-16-file-import-design.md`
Plan: `docs/superpowers/plans/2026-05-16-file-import.md`

## Test plan
- [x] Backend pytest suite green
- [x] Frontend vitest + lint + build green
- [x] Playwright e2e (`import-file.spec.ts`) green
- [x] Manual smoke against a real Hapoalim CSV export

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** Every spec section maps to at least one task — data model (Task 2), repo (Task 3), parser w/ all amount modes + date formats (Tasks 4–5), service CRUD + import flow (Tasks 6–7), routes (Task 8), API client + types + i18n (Task 9), mapping wizard (Task 10), wizard shell + dropzone + docs (Task 11), Data Sources page integration (Task 12), e2e (Task 13), smoke + PR (Task 14).
- **Out-of-scope items from the spec** (preview-and-confirm diff, OFX/QFX, type-C unsigned-amount-with-sign-column, editing service after creation, file-imported bank balance UI) are deliberately absent.
- **Type consistency:** `ColumnMapping` shape matches between backend (`backend/services/file_import_parser.py`) and frontend (`frontend/src/types/importedAccount.ts`); `ImportSummary` keys match between `import_file` return and the frontend toast interpolation.
- **Failure modes:** parser-level errors raise `ValueError` → routes translate to 400; service-level "not found" → 404; uniqueness violations → 400. Mirrors the codebase's existing patterns.
