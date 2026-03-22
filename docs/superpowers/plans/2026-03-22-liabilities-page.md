# Liabilities Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Liabilities page for tracking loans/debts with amortization schedules and actual vs expected payment comparison.

**Architecture:** Metadata layer on existing transactions. A `Liability` model stores loan parameters (principal, rate, term). Transactions are matched by `category="Liabilities"` + `tag`. Service calculates amortization schedules and compares against actual payments. Frontend uses card grid layout modeled after Investments page.

**Tech Stack:** SQLAlchemy ORM, FastAPI, Pandas, React 19, TanStack Query, Tailwind CSS 4, i18next

**Spec:** `docs/superpowers/specs/2026-03-22-liabilities-page-design.md`

---

## File Structure

### Backend (create)
- `backend/models/liability.py` — SQLAlchemy ORM model
- `backend/repositories/liabilities_repository.py` — CRUD + transaction fetching
- `backend/services/liabilities_service.py` — business logic, amortization calculation
- `backend/routes/liabilities.py` — API endpoints

### Backend (modify)
- `backend/constants/tables.py` — add `LIABILITIES` to `Tables` enum + `LiabilitiesTableFields`
- `backend/models/__init__.py` — import `Liability` so `Base.metadata.create_all()` picks it up
- `backend/main.py` — register liabilities router

### Frontend (create)
- `frontend/src/pages/Liabilities.tsx` — main page component

### Frontend (modify)
- `frontend/src/services/api.ts` — add `liabilitiesApi`
- `frontend/src/pages/index.ts` — export `Liabilities`
- `frontend/src/App.tsx` — add route
- `frontend/src/components/layout/Sidebar.tsx` — add nav item
- `frontend/src/locales/en.json` — add `liabilities.*` keys
- `frontend/src/locales/he.json` — add `liabilities.*` keys

### Tests (create)
- `tests/backend/unit/models/test_liability_model.py`
- `tests/backend/unit/repositories/test_liabilities_repository.py`
- `tests/backend/unit/services/test_liabilities_service.py`
- `tests/backend/routes/test_liabilities_routes.py`

### Tests (modify)
- `tests/backend/conftest.py` — add `seed_liabilities` fixture

---

## Task 1: Constants and Model

**Files:**
- Modify: `backend/constants/tables.py`
- Create: `backend/models/liability.py`
- Modify: `backend/models/__init__.py`
- Create: `tests/backend/unit/models/test_liability_model.py`

- [ ] **Step 1: Add `LIABILITIES` to `Tables` enum and create `LiabilitiesTableFields`**

In `backend/constants/tables.py`, add to the `Tables` enum (after `INSURANCE_ACCOUNTS`):

```python
LIABILITIES = "liabilities"
```

Add a new enum class after `InvestmentBalanceSnapshotsTableFields`:

```python
class LiabilitiesTableFields(Enum):
    """Field names for the liabilities table."""

    ID = "id"
    NAME = "name"
    LENDER = "lender"
    CATEGORY = "category"
    TAG = "tag"
    PRINCIPAL_AMOUNT = "principal_amount"
    INTEREST_RATE = "interest_rate"
    TERM_MONTHS = "term_months"
    START_DATE = "start_date"
    IS_PAID_OFF = "is_paid_off"
    PAID_OFF_DATE = "paid_off_date"
    NOTES = "notes"
    CREATED_DATE = "created_date"
```

- [ ] **Step 2: Create `Liability` model**

Create `backend/models/liability.py`:

```python
"""
Liability tracking model.
"""

from sqlalchemy import Column, Integer, String, Float, Text

from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class Liability(Base, TimestampMixin):
    """ORM model for a tracked liability (loan/debt).

    Each liability is identified by its ``category`` + ``tag`` pair, which
    corresponds to the category/tag used on existing transactions tagged
    under the Liabilities category.

    Attributes
    ----------
    name : str
        Human-readable name of the liability.
    lender : str, optional
        Name of the lending institution.
    category : str
        Always "Liabilities".
    tag : str
        Tag identifying this specific liability.
    principal_amount : float
        Original loan amount.
    interest_rate : float
        Annual interest rate as percentage (e.g. 4.5 for 4.5%).
    term_months : int
        Loan duration in months.
    start_date : str
        Date the loan was taken (YYYY-MM-DD).
    is_paid_off : int
        1 if the liability has been paid off, 0 otherwise.
    paid_off_date : str, optional
        Date the liability was paid off (YYYY-MM-DD).
    notes : str, optional
        Free-text notes.
    created_date : str
        Date the record was created (YYYY-MM-DD).
    """

    __tablename__ = Tables.LIABILITIES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    lender = Column(String, nullable=True)
    category = Column(String, nullable=False)
    tag = Column(String, nullable=False)

    principal_amount = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    term_months = Column(Integer, nullable=False)

    start_date = Column(String, nullable=False)
    is_paid_off = Column(Integer, default=0)
    paid_off_date = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_date = Column(String, nullable=False)
```

- [ ] **Step 3: Register model in `backend/models/__init__.py`**

Add `from backend.models.liability import Liability` to the imports so `Base.metadata.create_all()` creates the table on startup.

- [ ] **Step 4: Write model test**

Create `tests/backend/unit/models/test_liability_model.py`:

```python
"""
Unit tests for the Liability model.
"""

from sqlalchemy.orm import Session

from backend.models.liability import Liability


class TestLiabilityModel:
    """Tests for Liability ORM model."""

    def test_create_liability(self, db_session: Session):
        """Verify creating a liability record with all fields."""
        liability = Liability(
            name="Car Loan",
            lender="Bank Leumi",
            category="Liabilities",
            tag="Car Loan",
            principal_amount=50000.0,
            interest_rate=4.5,
            term_months=48,
            start_date="2024-01-15",
            created_date="2024-01-15",
        )
        db_session.add(liability)
        db_session.commit()

        result = db_session.query(Liability).first()
        assert result.name == "Car Loan"
        assert result.lender == "Bank Leumi"
        assert result.principal_amount == 50000.0
        assert result.interest_rate == 4.5
        assert result.term_months == 48
        assert result.is_paid_off == 0

    def test_create_liability_minimal_fields(self, db_session: Session):
        """Verify creating a liability with only required fields."""
        liability = Liability(
            name="Personal Loan",
            category="Liabilities",
            tag="Personal",
            principal_amount=10000.0,
            interest_rate=5.0,
            term_months=24,
            start_date="2024-06-01",
            created_date="2024-06-01",
        )
        db_session.add(liability)
        db_session.commit()

        result = db_session.query(Liability).first()
        assert result.lender is None
        assert result.notes is None
        assert result.paid_off_date is None
```

- [ ] **Step 5: Run model tests**

Run: `poetry run pytest tests/backend/unit/models/test_liability_model.py -v`
Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/constants/tables.py backend/models/liability.py backend/models/__init__.py tests/backend/unit/models/test_liability_model.py
git commit -m "feat(liabilities): add Liability model and Tables enum entry"
```

---

## Task 2: Repository

**Files:**
- Create: `backend/repositories/liabilities_repository.py`
- Modify: `tests/backend/conftest.py` (add `seed_liabilities` fixture)
- Create: `tests/backend/unit/repositories/test_liabilities_repository.py`

- [ ] **Step 1: Create `LiabilitiesRepository`**

Create `backend/repositories/liabilities_repository.py`:

```python
"""
Liabilities repository with SQLAlchemy ORM.
"""

from datetime import datetime

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.liability import Liability
from backend.constants.categories import LIABILITIES_CATEGORY
from backend.constants.tables import LiabilitiesTableFields, Tables


class LiabilitiesRepository:
    """Repository for managing liability tracking records."""

    table = Tables.LIABILITIES.value

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def create_liability(
        self,
        name: str,
        tag: str,
        principal_amount: float,
        interest_rate: float,
        term_months: int,
        start_date: str,
        lender: str = None,
        notes: str = None,
    ) -> None:
        """Create a new liability record.

        Parameters
        ----------
        name : str
            Human-readable display name for the liability.
        tag : str
            Tag identifying this liability under the Liabilities category.
        principal_amount : float
            Original loan amount.
        interest_rate : float
            Annual interest rate as percentage (e.g. 4.5 for 4.5%).
        term_months : int
            Loan duration in months.
        start_date : str
            Date the loan was taken, in YYYY-MM-DD format.
        lender : str, optional
            Name of the lending institution.
        notes : str, optional
            Free-text notes.
        """
        new_liability = Liability(
            name=name,
            lender=lender,
            category=LIABILITIES_CATEGORY,
            tag=tag,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            start_date=start_date,
            created_date=datetime.today().strftime("%Y-%m-%d"),
            notes=notes,
        )
        self.db.add(new_liability)
        self.db.commit()

    def get_all_liabilities(self, include_paid_off: bool = False) -> pd.DataFrame:
        """Get all liabilities, optionally including paid-off ones.

        Parameters
        ----------
        include_paid_off : bool
            When True, paid-off liabilities are included. Defaults to False.

        Returns
        -------
        pd.DataFrame
            All matching liability records.
        """
        stmt = select(Liability)
        if not include_paid_off:
            stmt = stmt.where(Liability.is_paid_off == 0)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_id(self, liability_id: int) -> pd.DataFrame:
        """Get a liability by its ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to retrieve.

        Returns
        -------
        pd.DataFrame
            Single-row DataFrame containing the liability record.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        stmt = select(Liability).where(Liability.id == liability_id)
        df = pd.read_sql(stmt, self.db.bind)
        if df.empty:
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )
        return df

    def update_liability(self, liability_id: int, **fields) -> None:
        """Update a liability by ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to update.
        **fields
            Keyword arguments mapping column names to new values.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        if not fields:
            return
        stmt = update(Liability).where(Liability.id == liability_id).values(**fields)
        result = self.db.execute(stmt)
        self.db.commit()
        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )

    def mark_paid_off(self, liability_id: int, paid_off_date: str) -> None:
        """Mark a liability as paid off.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability.
        paid_off_date : str
            Date the liability was paid off (YYYY-MM-DD).
        """
        stmt = (
            update(Liability)
            .where(Liability.id == liability_id)
            .values(is_paid_off=1, paid_off_date=paid_off_date)
        )
        self.db.execute(stmt)
        self.db.commit()

    def reopen(self, liability_id: int) -> None:
        """Reopen a paid-off liability.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to reopen.
        """
        stmt = (
            update(Liability)
            .where(Liability.id == liability_id)
            .values(is_paid_off=0, paid_off_date=None)
        )
        self.db.execute(stmt)
        self.db.commit()

    def delete_liability(self, liability_id: int) -> None:
        """Delete a liability by ID.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to delete.

        Raises
        ------
        EntityNotFoundException
            If no liability with the given ID exists.
        """
        stmt = delete(Liability).where(Liability.id == liability_id)
        result = self.db.execute(stmt)
        self.db.commit()
        if result.rowcount == 0:
            raise EntityNotFoundException(
                f"No liability found with ID {liability_id}"
            )
```

- [ ] **Step 2: Add `seed_liabilities` fixture to `tests/backend/conftest.py`**

Add at the end of the file, after the existing fixtures:

```python
from backend.models.liability import Liability

@pytest.fixture
def seed_liabilities(db_session: Session, seed_base_transactions) -> dict:
    """Insert liability records and related Liabilities-tagged transactions.

    Returns a dict with keys ``liabilities`` and ``transactions``.
    """
    car_loan = Liability(
        name="Car Loan",
        lender="Bank Leumi",
        category="Liabilities",
        tag="Car Loan",
        principal_amount=50000.0,
        interest_rate=4.5,
        term_months=48,
        start_date="2023-06-01",
        created_date="2023-06-01",
        is_paid_off=0,
    )
    student_loan = Liability(
        name="Student Loan",
        lender="Bank Hapoalim",
        category="Liabilities",
        tag="Student Loan",
        principal_amount=20000.0,
        interest_rate=3.8,
        term_months=36,
        start_date="2022-01-01",
        created_date="2022-01-01",
        is_paid_off=1,
        paid_off_date="2025-01-01",
    )

    db_session.add_all([car_loan, student_loan])
    db_session.flush()

    # Add bank transactions tagged as Liabilities
    liability_txns = [
        BankTransaction(
            id="liab_txn_1",
            date="2023-06-01",
            provider="bank_leumi",
            account_name="Main Account",
            description="Car Loan Disbursement",
            amount=50000.0,
            category="Liabilities",
            tag="Car Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="liab_txn_2",
            date="2023-07-01",
            provider="bank_leumi",
            account_name="Main Account",
            description="Car Loan Payment Jul",
            amount=-1150.0,
            category="Liabilities",
            tag="Car Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="liab_txn_3",
            date="2023-08-01",
            provider="bank_leumi",
            account_name="Main Account",
            description="Car Loan Payment Aug",
            amount=-1150.0,
            category="Liabilities",
            tag="Car Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
        BankTransaction(
            id="liab_txn_4",
            date="2023-09-01",
            provider="bank_leumi",
            account_name="Main Account",
            description="Car Loan Payment Sep",
            amount=-1150.0,
            category="Liabilities",
            tag="Car Loan",
            source="bank_transactions",
            type="normal",
            status="completed",
        ),
    ]
    db_session.add_all(liability_txns)
    db_session.commit()

    return {
        "liabilities": [car_loan, student_loan],
        "transactions": liability_txns,
    }
```

- [ ] **Step 3: Write repository tests**

Create `tests/backend/unit/repositories/test_liabilities_repository.py`:

```python
"""
Unit tests for LiabilitiesRepository CRUD operations.
"""

from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.repositories.liabilities_repository import LiabilitiesRepository
import pytest


class TestLiabilitiesRepository:
    """Tests for LiabilitiesRepository operations."""

    def test_create_liability(self, db_session: Session):
        """Verify creating a liability with all fields."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Car Loan",
            tag="Car Loan",
            principal_amount=50000.0,
            interest_rate=4.5,
            term_months=48,
            start_date="2024-01-15",
            lender="Bank Leumi",
            notes="48 month car loan",
        )

        result = repo.get_all_liabilities(include_paid_off=True)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["name"] == "Car Loan"
        assert row["category"] == "Liabilities"
        assert row["principal_amount"] == 50000.0
        assert row["interest_rate"] == 4.5
        assert row["term_months"] == 48

    def test_get_all_excludes_paid_off(self, db_session: Session):
        """Verify get_all_liabilities excludes paid-off by default."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Active Loan", tag="Active", principal_amount=10000.0,
            interest_rate=5.0, term_months=24, start_date="2024-01-01",
        )
        repo.create_liability(
            name="Paid Loan", tag="Paid", principal_amount=5000.0,
            interest_rate=3.0, term_months=12, start_date="2023-01-01",
        )

        all_liab = repo.get_all_liabilities(include_paid_off=True)
        paid_id = int(all_liab[all_liab["name"] == "Paid Loan"].iloc[0]["id"])
        repo.mark_paid_off(paid_id, "2024-01-01")

        result = repo.get_all_liabilities(include_paid_off=False)
        assert len(result) == 1
        assert result.iloc[0]["name"] == "Active Loan"

    def test_get_by_id(self, db_session: Session):
        """Verify retrieving liability by ID."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Test Loan", tag="Test", principal_amount=10000.0,
            interest_rate=5.0, term_months=24, start_date="2024-01-01",
        )

        all_liab = repo.get_all_liabilities(include_paid_off=True)
        liab_id = int(all_liab.iloc[0]["id"])
        result = repo.get_by_id(liab_id)
        assert result.iloc[0]["name"] == "Test Loan"

    def test_get_by_id_not_found(self, db_session: Session):
        """Verify EntityNotFoundException for missing ID."""
        repo = LiabilitiesRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.get_by_id(999)

    def test_update_liability(self, db_session: Session):
        """Verify updating liability fields."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Old Name", tag="Test", principal_amount=10000.0,
            interest_rate=5.0, term_months=24, start_date="2024-01-01",
        )

        all_liab = repo.get_all_liabilities(include_paid_off=True)
        liab_id = int(all_liab.iloc[0]["id"])
        repo.update_liability(liab_id, name="New Name", notes="Updated")

        result = repo.get_by_id(liab_id)
        assert result.iloc[0]["name"] == "New Name"
        assert result.iloc[0]["notes"] == "Updated"

    def test_mark_paid_off_and_reopen(self, db_session: Session):
        """Verify paying off and reopening a liability."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Test Loan", tag="Test", principal_amount=10000.0,
            interest_rate=5.0, term_months=24, start_date="2024-01-01",
        )

        all_liab = repo.get_all_liabilities(include_paid_off=True)
        liab_id = int(all_liab.iloc[0]["id"])

        repo.mark_paid_off(liab_id, "2025-12-01")
        result = repo.get_by_id(liab_id)
        assert result.iloc[0]["is_paid_off"] == 1
        assert result.iloc[0]["paid_off_date"] == "2025-12-01"

        repo.reopen(liab_id)
        result = repo.get_by_id(liab_id)
        assert result.iloc[0]["is_paid_off"] == 0
        assert result.iloc[0]["paid_off_date"] is None

    def test_delete_liability(self, db_session: Session):
        """Verify deleting a liability."""
        repo = LiabilitiesRepository(db_session)
        repo.create_liability(
            name="Delete Me", tag="Del", principal_amount=10000.0,
            interest_rate=5.0, term_months=24, start_date="2024-01-01",
        )

        all_liab = repo.get_all_liabilities(include_paid_off=True)
        liab_id = int(all_liab.iloc[0]["id"])
        repo.delete_liability(liab_id)

        with pytest.raises(EntityNotFoundException):
            repo.get_by_id(liab_id)

    def test_delete_not_found(self, db_session: Session):
        """Verify EntityNotFoundException when deleting missing ID."""
        repo = LiabilitiesRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.delete_liability(999)
```

- [ ] **Step 4: Run repository tests**

Run: `poetry run pytest tests/backend/unit/repositories/test_liabilities_repository.py -v`
Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/liabilities_repository.py tests/backend/unit/repositories/test_liabilities_repository.py tests/backend/conftest.py
git commit -m "feat(liabilities): add LiabilitiesRepository with CRUD operations"
```

---

## Task 3: Service

**Files:**
- Create: `backend/services/liabilities_service.py`
- Create: `tests/backend/unit/services/test_liabilities_service.py`

- [ ] **Step 1: Create `LiabilitiesService`**

Create `backend/services/liabilities_service.py`:

```python
"""
Liabilities service for loan tracking and amortization calculations.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from backend.constants.categories import LIABILITIES_CATEGORY
from backend.repositories.liabilities_repository import LiabilitiesRepository
from backend.repositories.transactions_repository import TransactionsRepository


class LiabilitiesService:
    """Service for managing liabilities with amortization calculations."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy session for database operations.
        """
        self.db = db
        self.liabilities_repo = LiabilitiesRepository(db)
        self.transactions_repo = TransactionsRepository(db)

    def get_all_liabilities(
        self, include_paid_off: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all liabilities with calculated metrics.

        Parameters
        ----------
        include_paid_off : bool
            When True, include paid-off liabilities. Default is False.

        Returns
        -------
        list[dict]
            Liability records enriched with calculated fields:
            monthly_payment, total_interest, remaining_balance,
            total_paid, percent_paid.
        """
        df = self.liabilities_repo.get_all_liabilities(include_paid_off=include_paid_off)
        df = df.replace({np.nan: None})
        records = df.to_dict(orient="records")

        for record in records:
            self._enrich_with_calculations(record)

        return records

    def get_liability(self, liability_id: int) -> Dict[str, Any]:
        """Get a single liability with full calculated details.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability.

        Returns
        -------
        dict
            Liability record with calculated fields.
        """
        df = self.liabilities_repo.get_by_id(liability_id)
        df = df.replace({np.nan: None})
        record = df.to_dict(orient="records")[0]
        self._enrich_with_calculations(record)
        return record

    def create_liability(
        self,
        name: str,
        tag: str,
        principal_amount: float,
        interest_rate: float,
        term_months: int,
        start_date: str,
        lender: str = None,
        notes: str = None,
    ) -> None:
        """Create a new liability and auto-create tag if needed.

        Parameters
        ----------
        name : str
            Human-readable name.
        tag : str
            Tag under the Liabilities category.
        principal_amount : float
            Original loan amount.
        interest_rate : float
            Annual interest rate as percentage.
        term_months : int
            Loan duration in months.
        start_date : str
            Date loan was taken (YYYY-MM-DD).
        lender : str, optional
            Lending institution name.
        notes : str, optional
            Free-text notes.
        """
        # Auto-create tag if it doesn't exist
        from backend.services.categories_tags_service import CategoriesTagsService
        cat_service = CategoriesTagsService(self.db)
        cat_service.add_tag(LIABILITIES_CATEGORY, tag)

        self.liabilities_repo.create_liability(
            name=name,
            tag=tag,
            principal_amount=principal_amount,
            interest_rate=interest_rate,
            term_months=term_months,
            start_date=start_date,
            lender=lender,
            notes=notes,
        )

    def update_liability(self, liability_id: int, **fields) -> None:
        """Update a liability's mutable fields.

        Parameters
        ----------
        liability_id : int
            Primary key of the liability to update.
        **fields
            name, lender, interest_rate, notes, paid_off_date.
        """
        self.liabilities_repo.update_liability(liability_id, **fields)

    def mark_paid_off(self, liability_id: int, paid_off_date: str) -> None:
        """Mark a liability as paid off.

        Parameters
        ----------
        liability_id : int
            Primary key.
        paid_off_date : str
            Date paid off (YYYY-MM-DD).
        """
        self.liabilities_repo.mark_paid_off(liability_id, paid_off_date)

    def reopen(self, liability_id: int) -> None:
        """Reopen a paid-off liability.

        Parameters
        ----------
        liability_id : int
            Primary key.
        """
        self.liabilities_repo.reopen(liability_id)

    def delete_liability(self, liability_id: int) -> None:
        """Delete a liability.

        Parameters
        ----------
        liability_id : int
            Primary key.
        """
        self.liabilities_repo.delete_liability(liability_id)

    def get_liability_analysis(self, liability_id: int) -> Dict[str, Any]:
        """Get full analysis: amortization schedule + actual vs expected.

        Parameters
        ----------
        liability_id : int
            Primary key.

        Returns
        -------
        dict
            Keys: schedule (amortization), transactions (matched),
            summary (totals), actual_vs_expected (monthly comparison).
        """
        liability = self.get_liability(liability_id)
        schedule = self.calculate_amortization_schedule(
            principal=liability["principal_amount"],
            annual_rate=liability["interest_rate"],
            term_months=liability["term_months"],
            start_date=liability["start_date"],
        )
        transactions = self.get_liability_transactions(liability_id)

        actual_vs_expected = self._compare_actual_vs_expected(
            schedule, transactions
        )

        # Calculate summary from actual transactions
        total_receipts = sum(
            t["amount"] for t in transactions if t["amount"] > 0
        )
        total_payments = abs(sum(
            t["amount"] for t in transactions if t["amount"] < 0
        ))

        return {
            "schedule": schedule,
            "transactions": transactions,
            "actual_vs_expected": actual_vs_expected,
            "summary": {
                "total_receipts": total_receipts,
                "total_payments": total_payments,
                "total_interest_cost": liability["total_interest"],
                "monthly_payment": liability["monthly_payment"],
                "remaining_balance": liability["remaining_balance"],
                "percent_paid": liability["percent_paid"],
            },
        }

    def get_liability_transactions(self, liability_id: int) -> List[Dict[str, Any]]:
        """Get matched transactions for a liability.

        Parameters
        ----------
        liability_id : int
            Primary key.

        Returns
        -------
        list[dict]
            Transactions matching this liability's category+tag.
        """
        liability_df = self.liabilities_repo.get_by_id(liability_id)
        tag = liability_df.iloc[0]["tag"]

        all_txns = self.transactions_repo.get_table()
        matched = all_txns[
            (all_txns["category"] == LIABILITIES_CATEGORY) &
            (all_txns["tag"] == tag)
        ]
        matched = matched.sort_values("date")
        matched = matched.replace({np.nan: None})
        return matched.to_dict(orient="records")

    @staticmethod
    def calculate_amortization_schedule(
        principal: float,
        annual_rate: float,
        term_months: int,
        start_date: str,
    ) -> List[Dict[str, Any]]:
        """Calculate a fixed-rate amortization schedule.

        Parameters
        ----------
        principal : float
            Original loan amount.
        annual_rate : float
            Annual interest rate as percentage (e.g. 4.5).
        term_months : int
            Number of monthly payments.
        start_date : str
            First payment month reference (YYYY-MM-DD).

        Returns
        -------
        list[dict]
            Each entry: payment_number, date, payment, principal_portion,
            interest_portion, remaining_balance.
        """
        monthly_rate = (annual_rate / 100.0) / 12.0
        start = datetime.strptime(start_date, "%Y-%m-%d").date()

        if monthly_rate == 0:
            monthly_payment = principal / term_months
        else:
            monthly_payment = (
                principal
                * monthly_rate
                * (1 + monthly_rate) ** term_months
                / ((1 + monthly_rate) ** term_months - 1)
            )

        schedule = []
        remaining = principal

        for i in range(1, term_months + 1):
            interest_portion = remaining * monthly_rate
            principal_portion = monthly_payment - interest_portion
            remaining -= principal_portion

            # Calculate payment date (start_date + i months)
            month = (start.month + i - 1) % 12 + 1
            year = start.year + (start.month + i - 1) // 12
            day = min(start.day, 28)  # Safe day for all months
            payment_date = date(year, month, day)

            schedule.append({
                "payment_number": i,
                "date": payment_date.strftime("%Y-%m-%d"),
                "payment": round(monthly_payment, 2),
                "principal_portion": round(principal_portion, 2),
                "interest_portion": round(interest_portion, 2),
                "remaining_balance": round(max(remaining, 0), 2),
            })

        return schedule

    def _enrich_with_calculations(self, record: Dict[str, Any]) -> None:
        """Add calculated fields to a liability record in-place.

        Parameters
        ----------
        record : dict
            Liability record to enrich.
        """
        principal = record["principal_amount"]
        annual_rate = record["interest_rate"]
        term_months = record["term_months"]
        monthly_rate = (annual_rate / 100.0) / 12.0

        if monthly_rate == 0:
            monthly_payment = principal / term_months
        else:
            monthly_payment = (
                principal
                * monthly_rate
                * (1 + monthly_rate) ** term_months
                / ((1 + monthly_rate) ** term_months - 1)
            )

        total_interest = monthly_payment * term_months - principal

        # Get actual payments from transactions
        tag = record["tag"]
        all_txns = self.transactions_repo.get_table()
        matched = all_txns[
            (all_txns["category"] == LIABILITIES_CATEGORY) &
            (all_txns["tag"] == tag)
        ]
        total_paid = abs(matched[matched["amount"] < 0]["amount"].sum())

        # Remaining balance from amortization schedule position
        schedule = self.calculate_amortization_schedule(
            principal, annual_rate, term_months, record["start_date"]
        )
        # Find current position: how many payments have been made
        payments_made = len(matched[matched["amount"] < 0])
        if payments_made >= term_months:
            remaining_balance = 0.0
        elif payments_made > 0:
            remaining_balance = schedule[payments_made - 1]["remaining_balance"]
        else:
            remaining_balance = principal

        percent_paid = (
            round((1 - remaining_balance / principal) * 100, 1)
            if principal > 0 else 100.0
        )

        record["monthly_payment"] = round(monthly_payment, 2)
        record["total_interest"] = round(total_interest, 2)
        record["remaining_balance"] = round(remaining_balance, 2)
        record["total_paid"] = round(total_paid, 2)
        record["percent_paid"] = percent_paid

    @staticmethod
    def _compare_actual_vs_expected(
        schedule: List[Dict[str, Any]],
        transactions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Compare actual payments to amortization schedule by month.

        Parameters
        ----------
        schedule : list[dict]
            Amortization schedule entries.
        transactions : list[dict]
            Matched transactions.

        Returns
        -------
        list[dict]
            Each entry: date, expected_payment, actual_payment, difference.
        """
        # Group actual payments by YYYY-MM
        payment_txns = [t for t in transactions if t["amount"] < 0]
        actual_by_month = {}
        for txn in payment_txns:
            month_key = txn["date"][:7]  # YYYY-MM
            actual_by_month[month_key] = (
                actual_by_month.get(month_key, 0) + abs(txn["amount"])
            )

        comparison = []
        for entry in schedule:
            month_key = entry["date"][:7]
            actual = actual_by_month.get(month_key, 0)
            comparison.append({
                "date": entry["date"],
                "expected_payment": entry["payment"],
                "actual_payment": round(actual, 2),
                "difference": round(actual - entry["payment"], 2),
            })

        return comparison
```

- [ ] **Step 2: Write service tests**

Create `tests/backend/unit/services/test_liabilities_service.py`:

```python
"""
Unit tests for LiabilitiesService.
"""

from sqlalchemy.orm import Session

from backend.services.liabilities_service import LiabilitiesService


class TestLiabilitiesService:
    """Tests for LiabilitiesService operations."""

    def test_calculate_amortization_schedule(self):
        """Verify amortization schedule calculation for a fixed-rate loan."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=6.0,
            term_months=12,
            start_date="2024-01-15",
        )

        assert len(schedule) == 12
        assert schedule[0]["payment_number"] == 1
        assert schedule[-1]["remaining_balance"] == 0.0
        # Monthly payment for 12000 at 6% for 12 months ≈ 1032.07
        assert abs(schedule[0]["payment"] - 1032.07) < 1.0
        # First month interest: 12000 * 0.005 = 60
        assert abs(schedule[0]["interest_portion"] - 60.0) < 0.01
        # Total paid should be close to principal + total interest
        total_paid = sum(e["payment"] for e in schedule)
        assert total_paid > 12000.0

    def test_calculate_amortization_zero_rate(self):
        """Verify schedule for a zero-interest loan."""
        schedule = LiabilitiesService.calculate_amortization_schedule(
            principal=12000.0,
            annual_rate=0.0,
            term_months=12,
            start_date="2024-01-15",
        )

        assert len(schedule) == 12
        assert schedule[0]["payment"] == 1000.0
        assert schedule[0]["interest_portion"] == 0.0
        assert schedule[-1]["remaining_balance"] == 0.0

    def test_get_all_liabilities_with_metrics(self, db_session: Session, seed_liabilities):
        """Verify get_all returns enriched records with calculated fields."""
        service = LiabilitiesService(db_session)
        result = service.get_all_liabilities(include_paid_off=False)

        assert len(result) == 1  # Only active (car loan)
        car_loan = result[0]
        assert car_loan["name"] == "Car Loan"
        assert "monthly_payment" in car_loan
        assert "total_interest" in car_loan
        assert "remaining_balance" in car_loan
        assert "total_paid" in car_loan
        assert "percent_paid" in car_loan
        assert car_loan["monthly_payment"] > 0
        assert car_loan["total_paid"] > 0

    def test_get_liability_analysis(self, db_session: Session, seed_liabilities):
        """Verify analysis returns schedule, transactions, and comparison."""
        service = LiabilitiesService(db_session)
        liabilities = service.get_all_liabilities(include_paid_off=False)
        car_loan_id = liabilities[0]["id"]

        analysis = service.get_liability_analysis(car_loan_id)

        assert "schedule" in analysis
        assert "transactions" in analysis
        assert "actual_vs_expected" in analysis
        assert "summary" in analysis
        assert len(analysis["schedule"]) == 48  # 48 month term
        assert len(analysis["transactions"]) == 4  # 1 receipt + 3 payments
        assert analysis["summary"]["total_receipts"] == 50000.0
        assert analysis["summary"]["total_payments"] == 3450.0  # 3 * 1150

    def test_get_liability_transactions(self, db_session: Session, seed_liabilities):
        """Verify transaction matching by category+tag."""
        service = LiabilitiesService(db_session)
        liabilities = service.get_all_liabilities(include_paid_off=False)
        car_loan_id = liabilities[0]["id"]

        txns = service.get_liability_transactions(car_loan_id)
        assert len(txns) == 4
        # First should be the disbursement (positive)
        assert txns[0]["amount"] == 50000.0
        # Rest are payments (negative)
        assert all(t["amount"] < 0 for t in txns[1:])
```

- [ ] **Step 3: Run service tests**

Run: `poetry run pytest tests/backend/unit/services/test_liabilities_service.py -v`
Expected: 5 tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/liabilities_service.py tests/backend/unit/services/test_liabilities_service.py
git commit -m "feat(liabilities): add LiabilitiesService with amortization calculation"
```

---

## Task 4: Routes

**Files:**
- Create: `backend/routes/liabilities.py`
- Modify: `backend/main.py`
- Create: `tests/backend/routes/test_liabilities_routes.py`

- [ ] **Step 1: Create routes**

Create `backend/routes/liabilities.py`:

```python
"""
Liabilities API routes.

Provides endpoints for liability tracking and analysis.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.liabilities_service import LiabilitiesService

router = APIRouter()


class LiabilityCreate(BaseModel):
    name: str
    tag: str
    principal_amount: float
    interest_rate: float
    term_months: int
    start_date: str
    lender: Optional[str] = None
    notes: Optional[str] = None


class LiabilityUpdate(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    interest_rate: Optional[float] = None
    paid_off_date: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def get_liabilities(
    include_paid_off: bool = False, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return all liability records."""
    service = LiabilitiesService(db)
    return service.get_all_liabilities(include_paid_off=include_paid_off)


@router.get("/{liability_id}")
async def get_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Get a specific liability by ID."""
    service = LiabilitiesService(db)
    return service.get_liability(liability_id)


@router.get("/{liability_id}/analysis")
async def get_liability_analysis(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, Any]:
    """Return amortization schedule and actual vs expected analysis."""
    service = LiabilitiesService(db)
    return service.get_liability_analysis(liability_id)


@router.get("/{liability_id}/transactions")
async def get_liability_transactions(
    liability_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Return matched transactions for a liability."""
    service = LiabilitiesService(db)
    return service.get_liability_transactions(liability_id)


@router.post("/")
async def create_liability(
    liability: LiabilityCreate, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Create a new liability."""
    service = LiabilitiesService(db)
    service.create_liability(
        name=liability.name,
        tag=liability.tag,
        principal_amount=liability.principal_amount,
        interest_rate=liability.interest_rate,
        term_months=liability.term_months,
        start_date=liability.start_date,
        lender=liability.lender,
        notes=liability.notes,
    )
    return {"status": "success"}


@router.put("/{liability_id}")
async def update_liability(
    liability_id: int,
    liability: LiabilityUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update a liability."""
    service = LiabilitiesService(db)
    updates = {k: v for k, v in liability.model_dump().items() if v is not None}
    service.update_liability(liability_id, **updates)
    return {"status": "success"}


@router.post("/{liability_id}/pay-off")
async def pay_off_liability(
    liability_id: int, paid_off_date: str, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Mark a liability as paid off."""
    service = LiabilitiesService(db)
    service.mark_paid_off(liability_id, paid_off_date)
    return {"status": "success"}


@router.post("/{liability_id}/reopen")
async def reopen_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Reopen a paid-off liability."""
    service = LiabilitiesService(db)
    service.reopen(liability_id)
    return {"status": "success"}


@router.delete("/{liability_id}")
async def delete_liability(
    liability_id: int, db: Session = Depends(get_database)
) -> dict[str, str]:
    """Delete a liability."""
    service = LiabilitiesService(db)
    service.delete_liability(liability_id)
    return {"status": "success"}
```

- [ ] **Step 2: Register router in `backend/main.py`**

Add import (after the existing route imports around line 38):

```python
from backend.routes import liabilities
```

Add router registration (after the investments router registration, find the block where `app.include_router` calls are):

```python
app.include_router(liabilities.router, prefix="/api/liabilities", tags=["liabilities"])
```

- [ ] **Step 3: Write route tests**

Create `tests/backend/routes/test_liabilities_routes.py`:

```python
"""Tests for the /api/liabilities API endpoints."""


class TestLiabilitiesRoutes:
    """Tests for liability API endpoints."""

    def test_get_liabilities(self, test_client, seed_liabilities):
        """GET /api/liabilities/ returns liability list."""
        response = test_client.get("/api/liabilities/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        names = [l["name"] for l in data]
        assert "Car Loan" in names

    def test_get_liabilities_include_paid_off(self, test_client, seed_liabilities):
        """GET /api/liabilities/?include_paid_off=true returns all."""
        response = test_client.get("/api/liabilities/?include_paid_off=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        names = [l["name"] for l in data]
        assert "Student Loan" in names

    def test_create_liability(self, test_client):
        """POST /api/liabilities/ creates a new liability."""
        payload = {
            "name": "Test Loan",
            "tag": "Test",
            "principal_amount": 10000.0,
            "interest_rate": 5.0,
            "term_months": 24,
            "start_date": "2024-01-01",
        }
        response = test_client.post("/api/liabilities/", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        list_resp = test_client.get("/api/liabilities/")
        assert any(l["name"] == "Test Loan" for l in list_resp.json())

    def test_get_liability_by_id(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id} returns single liability."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liab_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == liab_id
        assert "monthly_payment" in data

    def test_update_liability(self, test_client, seed_liabilities):
        """PUT /api/liabilities/{id} updates liability."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.put(
            f"/api/liabilities/{liab_id}",
            json={"name": "Updated Loan"},
        )
        assert response.status_code == 200

        get_resp = test_client.get(f"/api/liabilities/{liab_id}")
        assert get_resp.json()["name"] == "Updated Loan"

    def test_pay_off_and_reopen(self, test_client, seed_liabilities):
        """POST pay-off and reopen lifecycle."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.post(
            f"/api/liabilities/{liab_id}/pay-off",
            params={"paid_off_date": "2025-12-01"},
        )
        assert response.status_code == 200

        # Should not appear in default list
        list_resp = test_client.get("/api/liabilities/")
        assert not any(l["id"] == liab_id for l in list_resp.json())

        # Reopen
        response = test_client.post(f"/api/liabilities/{liab_id}/reopen")
        assert response.status_code == 200

        list_resp = test_client.get("/api/liabilities/")
        assert any(l["id"] == liab_id for l in list_resp.json())

    def test_delete_liability(self, test_client, seed_liabilities):
        """DELETE /api/liabilities/{id} removes liability."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.delete(f"/api/liabilities/{liab_id}")
        assert response.status_code == 200

        get_resp = test_client.get(f"/api/liabilities/{liab_id}")
        assert get_resp.status_code == 404

    def test_get_analysis(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id}/analysis returns amortization data."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liab_id}/analysis")
        assert response.status_code == 200
        data = response.json()
        assert "schedule" in data
        assert "transactions" in data
        assert "actual_vs_expected" in data
        assert "summary" in data

    def test_get_transactions(self, test_client, seed_liabilities):
        """GET /api/liabilities/{id}/transactions returns matched txns."""
        list_resp = test_client.get("/api/liabilities/")
        liab_id = list_resp.json()[0]["id"]

        response = test_client.get(f"/api/liabilities/{liab_id}/transactions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
```

- [ ] **Step 4: Run route tests**

Run: `poetry run pytest tests/backend/routes/test_liabilities_routes.py -v`
Expected: 9 tests PASS

- [ ] **Step 5: Run all existing tests to check for regressions**

Run: `poetry run pytest --tb=short -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/liabilities.py backend/main.py tests/backend/routes/test_liabilities_routes.py
git commit -m "feat(liabilities): add API routes and register in main app"
```

---

## Task 5: Frontend API Service + i18n + Navigation

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/index.ts`

- [ ] **Step 1: Add `liabilitiesApi` to `frontend/src/services/api.ts`**

Add after the `investmentsApi` section:

```typescript
// Liabilities API
export const liabilitiesApi = {
  getAll: (includePaidOff = false) =>
    api.get("/liabilities/", { params: { include_paid_off: includePaidOff } }),
  getById: (id: number) => api.get(`/liabilities/${id}`),
  create: (liability: object) => api.post("/liabilities/", liability),
  update: (id: number, liability: object) =>
    api.put(`/liabilities/${id}`, liability),
  payOff: (id: number, paidOffDate: string) =>
    api.post(`/liabilities/${id}/pay-off`, null, {
      params: { paid_off_date: paidOffDate },
    }),
  reopen: (id: number) => api.post(`/liabilities/${id}/reopen`),
  delete: (id: number) => api.delete(`/liabilities/${id}`),
  getAnalysis: (id: number) => api.get(`/liabilities/${id}/analysis`),
  getTransactions: (id: number) => api.get(`/liabilities/${id}/transactions`),
};
```

- [ ] **Step 2: Add i18n keys to `en.json`**

Add `liabilities` section alongside other page sections:

```json
"liabilities": {
  "title": "Liabilities",
  "subtitle": "Track your loans and debts",
  "addLiability": "Add Liability",
  "totalDebt": "Total Outstanding Debt",
  "monthlyPayments": "Total Monthly Payments",
  "totalInterest": "Total Interest Cost",
  "name": "Name",
  "lender": "Lender",
  "tag": "Tag",
  "principalAmount": "Principal Amount",
  "interestRate": "Interest Rate",
  "termMonths": "Term (Months)",
  "startDate": "Start Date",
  "notes": "Notes",
  "monthlyPayment": "Monthly Payment",
  "remainingBalance": "Remaining Balance",
  "totalPaid": "Total Paid",
  "percentPaid": "Paid Off",
  "active": "Active",
  "paidOff": "Paid Off",
  "payOff": "Mark Paid Off",
  "reopen": "Reopen",
  "analysis": "Analysis",
  "amortizationSchedule": "Amortization Schedule",
  "actualVsExpected": "Actual vs Expected",
  "paymentNumber": "Payment #",
  "payment": "Payment",
  "principalPortion": "Principal",
  "interestPortion": "Interest",
  "expectedPayment": "Expected",
  "actualPayment": "Actual",
  "difference": "Difference",
  "totalReceipts": "Total Received",
  "totalPaymentsMade": "Total Payments Made",
  "interestRemaining": "Interest Remaining",
  "noLiabilities": "No liabilities tracked yet",
  "confirmDelete": "Are you sure you want to delete this liability?",
  "paidOffDate": "Paid Off Date",
  "editLiability": "Edit Liability",
  "transactions": "Transactions"
}
```

Add to sidebar section: `"liabilities": "Liabilities"`

- [ ] **Step 3: Add i18n keys to `he.json`**

Add matching `liabilities` section:

```json
"liabilities": {
  "title": "התחייבויות",
  "subtitle": "מעקב אחר הלוואות וחובות",
  "addLiability": "הוסף התחייבות",
  "totalDebt": "סך חוב שוטף",
  "monthlyPayments": "סך תשלומים חודשיים",
  "totalInterest": "סך עלות ריבית",
  "name": "שם",
  "lender": "מלווה",
  "tag": "תגית",
  "principalAmount": "סכום קרן",
  "interestRate": "שיעור ריבית",
  "termMonths": "תקופה (חודשים)",
  "startDate": "תאריך התחלה",
  "notes": "הערות",
  "monthlyPayment": "תשלום חודשי",
  "remainingBalance": "יתרה לתשלום",
  "totalPaid": "סך שולם",
  "percentPaid": "שולם",
  "active": "פעיל",
  "paidOff": "שולם במלואו",
  "payOff": "סמן כשולם",
  "reopen": "פתח מחדש",
  "analysis": "ניתוח",
  "amortizationSchedule": "לוח סילוקין",
  "actualVsExpected": "בפועל מול צפוי",
  "paymentNumber": "תשלום מס׳",
  "payment": "תשלום",
  "principalPortion": "קרן",
  "interestPortion": "ריבית",
  "expectedPayment": "צפוי",
  "actualPayment": "בפועל",
  "difference": "הפרש",
  "totalReceipts": "סך התקבל",
  "totalPaymentsMade": "סך תשלומים",
  "interestRemaining": "ריבית שנותרה",
  "noLiabilities": "אין התחייבויות במעקב",
  "confirmDelete": "האם אתה בטוח שברצונך למחוק התחייבות זו?",
  "paidOffDate": "תאריך סילוק",
  "editLiability": "ערוך התחייבות",
  "transactions": "תנועות"
}
```

Add to sidebar section: `"liabilities": "התחייבויות"`

- [ ] **Step 4: Add sidebar nav item**

In `frontend/src/components/layout/Sidebar.tsx`, add to the `navItems` array (between investments and insurances):

```typescript
{ path: "/liabilities", icon: Landmark, key: "liabilities" },
```

Import `Landmark` from `lucide-react` (add to existing import).

- [ ] **Step 5: Add route and page export**

In `frontend/src/pages/index.ts`, add:
```typescript
export { Liabilities } from "./Liabilities";
```

In `frontend/src/App.tsx`, add import and route:
```typescript
import { Liabilities } from "./pages";
// ... in Routes:
<Route path="liabilities" element={<Liabilities />} />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/locales/en.json frontend/src/locales/he.json frontend/src/components/layout/Sidebar.tsx frontend/src/App.tsx frontend/src/pages/index.ts
git commit -m "feat(liabilities): add frontend API service, i18n, and navigation"
```

---

## Task 6: Liabilities Page Component

**Files:**
- Create: `frontend/src/pages/Liabilities.tsx`

This is the largest task. Build the page following the Investments.tsx pattern: card grid with summary stats, create/edit modals, and analysis modal.

- [ ] **Step 1: Create the Liabilities page**

Create `frontend/src/pages/Liabilities.tsx`. The page should follow the Investments.tsx pattern with these sections:

1. **Imports:** React, TanStack Query (`useQuery`, `useMutation`, `useQueryClient`), lucide-react icons (`Plus`, `Landmark`, `Pencil`, `Trash2`, `BarChart2`, `Power`, `RotateCcw`), `useTranslation`, `liabilitiesApi`, Plotly for charts.

2. **Query hooks:**
   - `useQuery({ queryKey: ["liabilities"], queryFn: () => liabilitiesApi.getAll(showPaidOff) })`
   - Mutations for create, update, delete, payOff, reopen — each invalidates `["liabilities"]`

3. **State:**
   - `showPaidOff` toggle (boolean)
   - `createModalOpen` / `editModalOpen` / `analysisModalOpen` (booleans)
   - `selectedLiability` (for edit/analysis)
   - Form fields for create/edit modal

4. **Summary stat cards (3):**
   - Total Outstanding Debt — sum of `remaining_balance` for active liabilities (red/rose styling)
   - Total Monthly Payments — sum of `monthly_payment` for active liabilities
   - Total Interest Cost — sum of `total_interest` for all liabilities (amber styling)

5. **Liability cards grid** (`grid grid-cols-1 md:grid-cols-2 gap-4`):
   Each card shows:
   - Header: name + lender + status badge
   - Metadata: `{rate}% · {term} months · Started {date}`
   - Progress bar with percent label
   - Stats row: remaining balance, monthly payment
   - Action buttons: analysis, edit, pay-off/reopen, delete

6. **Create/Edit modal:**
   - Form fields: name, lender (optional), tag, principal_amount, interest_rate, term_months, start_date, notes
   - Submit calls create or update mutation
   - Use `t()` for all labels

7. **Analysis modal:**
   - Tabs or sections: Amortization Schedule, Actual vs Expected, Transactions
   - Amortization table: scrollable, columns from schedule data
   - Actual vs Expected: highlight differences (green = overpaid, red = underpaid)
   - Use `liabilitiesApi.getAnalysis(id)` query

8. **Empty state:** Show message when no liabilities exist

9. **i18n:** All strings via `t("liabilities.key")`

10. **RTL:** Use logical Tailwind properties (`ps-*`, `pe-*`, `ms-*`, `me-*`, `text-start`)

11. **SQLite boolean gotcha:** Use `!!liability.is_paid_off &&` not `liability.is_paid_off &&` in JSX conditionals

Reference `frontend/src/pages/Investments.tsx` for exact patterns on modal structure, card layout, mutation handling, loading states, and skeleton loaders.

- [ ] **Step 2: Verify the build compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Verify lint passes**

Run: `cd frontend && npm run lint`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Liabilities.tsx
git commit -m "feat(liabilities): add Liabilities page with cards, modals, and analysis"
```

---

## Task 7: Integration Testing and Polish

- [ ] **Step 1: Run full backend test suite**

Run: `poetry run pytest --tb=short -q`
Expected: All tests PASS (including new liabilities tests)

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Smoke test with both servers**

Start both servers and verify:
- `/api/liabilities/` returns empty list (or sample data)
- Liabilities page renders in browser
- Create a liability, verify it appears
- View analysis modal
- Enable Demo Mode and verify page works with demo data

Run: `python .claude/scripts/with_server.py -- echo "Servers started successfully"`

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(liabilities): integration fixes from smoke testing"
```
