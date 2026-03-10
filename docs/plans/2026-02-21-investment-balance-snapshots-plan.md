# Investment Balance Snapshots Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add timestamped balance snapshots to investments, enabling accurate profit/loss, ROI, and CAGR calculations based on real market values rather than just deposits/withdrawals.

**Architecture:** New `investment_balance_snapshots` table with full backend stack (model → repo → service → routes). The existing `InvestmentsService` methods (`calculate_profit_loss`, `calculate_current_balance`, `calculate_balance_over_time`, `get_portfolio_overview`) are updated to prefer snapshot-based balances when available, falling back to the existing transaction-based calculation. Fixed-rate investments get auto-calculated snapshots via daily compounding. Frontend adds balance update UI and snapshot-aware charts.

**Tech Stack:** SQLAlchemy ORM model, pandas DataFrames in repository, FastAPI routes with Pydantic schemas, React + TanStack Query frontend.

**Design doc:** `docs/plans/2026-02-21-investment-balance-snapshots-design.md`

---

### Task 1: Add `INVESTMENT_BALANCE_SNAPSHOTS` to Tables enum

**Files:**
- Modify: `backend/constants/tables.py:50` (after `INVESTMENTS` entry)

**Step 1: Add enum entry**

In `backend/constants/tables.py`, add a new entry to the `Tables` enum after `INVESTMENTS`:

```python
INVESTMENT_BALANCE_SNAPSHOTS = "investment_balance_snapshots"
```

Also add a new field enum class at the bottom of the file:

```python
class InvestmentBalanceSnapshotsTableFields(Enum):
    """Field names for the investment_balance_snapshots table."""

    ID = "id"
    INVESTMENT_ID = "investment_id"
    DATE = "date"
    BALANCE = "balance"
    SOURCE = "source"
```

**Step 2: Commit**

```bash
git add backend/constants/tables.py
git commit -m "feat: add investment_balance_snapshots table constant"
```

---

### Task 2: Create the SQLAlchemy ORM model

**Files:**
- Create: `backend/models/investment_balance_snapshot.py`
- Modify: `backend/models/__init__.py` (if it exists and re-exports models)

**Step 1: Write the model**

Create `backend/models/investment_balance_snapshot.py`:

```python
"""
Investment balance snapshot model.
"""

from sqlalchemy import Column, Integer, Float, String, ForeignKey, UniqueConstraint
from backend.models.base import Base, TimestampMixin
from backend.constants.tables import Tables


class InvestmentBalanceSnapshot(Base, TimestampMixin):
    """ORM model for an investment balance snapshot.

    Records the market value of an investment on a specific date.
    One snapshot per investment per date (upsert semantics).

    Attributes
    ----------
    investment_id : int
        Foreign key referencing the investment record.
    date : str
        Snapshot date in ``YYYY-MM-DD`` format.
    balance : float
        Market value of the investment on this date.
    source : str
        How the snapshot was created: ``"manual"``, ``"scraped"``, or ``"calculated"``.
    """

    __tablename__ = Tables.INVESTMENT_BALANCE_SNAPSHOTS.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    investment_id = Column(
        Integer,
        ForeignKey(f"{Tables.INVESTMENTS.value}.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    source = Column(String, nullable=False, default="manual")

    __table_args__ = (
        UniqueConstraint("investment_id", "date", name="uq_snapshot_investment_date"),
    )
```

**Step 2: Verify model is auto-discovered**

Check if there's a models `__init__.py` that imports all models. The `conftest.py` uses `Base.metadata.create_all(engine)` which will pick up any model that imports `Base` — so as long as the model is imported somewhere before tests run, it will be discovered. The test file itself will import the model.

**Step 3: Commit**

```bash
git add backend/models/investment_balance_snapshot.py
git commit -m "feat: add InvestmentBalanceSnapshot ORM model"
```

---

### Task 3: Create the snapshots repository with tests (TDD)

**Files:**
- Create: `backend/repositories/investment_snapshots_repository.py`
- Create: `tests/backend/unit/repositories/test_investment_snapshots_repository.py`

**Step 1: Write the failing tests**

Create `tests/backend/unit/repositories/test_investment_snapshots_repository.py`:

```python
"""
Unit tests for InvestmentSnapshotsRepository CRUD operations.
"""

import pytest
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.repositories.investment_snapshots_repository import (
    InvestmentSnapshotsRepository,
)


def _create_investment(db_session: Session, tag: str = "Test Fund") -> int:
    """Helper to create an investment and return its ID."""
    inv = Investment(
        category="Investments",
        tag=tag,
        type="etf",
        name="Test",
        created_date="2024-01-01",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv.id


class TestInvestmentSnapshotsRepository:
    """Tests for snapshot CRUD operations."""

    def test_upsert_creates_new_snapshot(self, db_session: Session):
        """Verify upserting a snapshot creates a new row when none exists."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-15", 50000.0, "manual")

        snapshots = repo.get_snapshots_for_investment(inv_id)
        assert len(snapshots) == 1
        assert snapshots.iloc[0]["balance"] == 50000.0
        assert snapshots.iloc[0]["source"] == "manual"

    def test_upsert_updates_existing_snapshot(self, db_session: Session):
        """Verify upserting overwrites the balance for an existing date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-15", 50000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-01-15", 52000.0, "manual")

        snapshots = repo.get_snapshots_for_investment(inv_id)
        assert len(snapshots) == 1
        assert snapshots.iloc[0]["balance"] == 52000.0

    def test_get_snapshots_for_investment_ordered_by_date(self, db_session: Session):
        """Verify snapshots are returned ordered by date ascending."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-03-01", 60000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-01-01", 50000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-02-01", 55000.0, "manual")

        snapshots = repo.get_snapshots_for_investment(inv_id)
        assert len(snapshots) == 3
        dates = snapshots["date"].tolist()
        assert dates == ["2025-01-01", "2025-02-01", "2025-03-01"]

    def test_get_latest_snapshot_on_or_before(self, db_session: Session):
        """Verify fetching the latest snapshot on or before a target date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-01", 50000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-02-01", 55000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-03-01", 60000.0, "manual")

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2025-02-15")
        assert result is not None
        assert result["date"] == "2025-02-01"
        assert result["balance"] == 55000.0

    def test_get_latest_snapshot_on_or_before_exact_match(self, db_session: Session):
        """Verify exact date match works for latest snapshot."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-02-01", 55000.0, "manual")

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2025-02-01")
        assert result is not None
        assert result["balance"] == 55000.0

    def test_get_latest_snapshot_on_or_before_none_before_date(self, db_session: Session):
        """Verify None is returned when no snapshots exist before the target date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-03-01", 60000.0, "manual")

        result = repo.get_latest_snapshot_on_or_before(inv_id, "2025-02-15")
        assert result is None

    def test_delete_snapshot(self, db_session: Session):
        """Verify deleting a snapshot by ID."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-15", 50000.0, "manual")
        snapshots = repo.get_snapshots_for_investment(inv_id)
        snapshot_id = int(snapshots.iloc[0]["id"])

        repo.delete_snapshot(snapshot_id)

        result = repo.get_snapshots_for_investment(inv_id)
        assert result.empty

    def test_delete_snapshot_not_found(self, db_session: Session):
        """Verify EntityNotFoundException for non-existent snapshot."""
        repo = InvestmentSnapshotsRepository(db_session)
        with pytest.raises(EntityNotFoundException):
            repo.delete_snapshot(999)

    def test_update_snapshot(self, db_session: Session):
        """Verify updating a snapshot's balance and date."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-15", 50000.0, "manual")
        snapshots = repo.get_snapshots_for_investment(inv_id)
        snapshot_id = int(snapshots.iloc[0]["id"])

        repo.update_snapshot(snapshot_id, balance=52000.0)

        updated = repo.get_snapshots_for_investment(inv_id)
        assert updated.iloc[0]["balance"] == 52000.0

    def test_delete_snapshots_for_investment(self, db_session: Session):
        """Verify bulk deletion of all snapshots for an investment."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-01", 50000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-02-01", 55000.0, "manual")

        repo.delete_snapshots_for_investment(inv_id)

        result = repo.get_snapshots_for_investment(inv_id)
        assert result.empty

    def test_delete_calculated_snapshots_for_investment(self, db_session: Session):
        """Verify only calculated snapshots are deleted, manual ones preserved."""
        inv_id = _create_investment(db_session)
        repo = InvestmentSnapshotsRepository(db_session)

        repo.upsert_snapshot(inv_id, "2025-01-01", 50000.0, "manual")
        repo.upsert_snapshot(inv_id, "2025-02-01", 55000.0, "calculated")

        repo.delete_snapshots_for_investment(inv_id, source="calculated")

        result = repo.get_snapshots_for_investment(inv_id)
        assert len(result) == 1
        assert result.iloc[0]["source"] == "manual"
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/repositories/test_investment_snapshots_repository.py -v
```

Expected: ImportError (module doesn't exist yet).

**Step 3: Write the repository**

Create `backend/repositories/investment_snapshots_repository.py`:

```python
"""
Investment balance snapshots repository.
"""

from typing import Optional

import pandas as pd
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot


class InvestmentSnapshotsRepository:
    """Repository for investment balance snapshot CRUD operations."""

    def __init__(self, db: Session):
        """
        Parameters
        ----------
        db : Session
            SQLAlchemy database session.
        """
        self.db = db

    def upsert_snapshot(
        self,
        investment_id: int,
        date: str,
        balance: float,
        source: str = "manual",
    ) -> None:
        """Create or update a balance snapshot for a given investment and date.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        date : str
            Snapshot date in ``YYYY-MM-DD`` format.
        balance : float
            Market value on this date.
        source : str
            Origin of the snapshot: ``"manual"``, ``"scraped"``, or ``"calculated"``.
        """
        existing = (
            self.db.query(InvestmentBalanceSnapshot)
            .filter_by(investment_id=investment_id, date=date)
            .first()
        )
        if existing:
            existing.balance = balance
            existing.source = source
        else:
            snapshot = InvestmentBalanceSnapshot(
                investment_id=investment_id,
                date=date,
                balance=balance,
                source=source,
            )
            self.db.add(snapshot)
        self.db.commit()

    def get_snapshots_for_investment(self, investment_id: int) -> pd.DataFrame:
        """Get all snapshots for an investment, ordered by date ascending.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        pd.DataFrame
            Snapshot records ordered by date.
        """
        stmt = (
            select(InvestmentBalanceSnapshot)
            .where(InvestmentBalanceSnapshot.investment_id == investment_id)
            .order_by(InvestmentBalanceSnapshot.date.asc())
        )
        return pd.read_sql(stmt, self.db.bind)

    def get_latest_snapshot_on_or_before(
        self, investment_id: int, target_date: str
    ) -> Optional[dict]:
        """Get the most recent snapshot on or before a target date.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        target_date : str
            Date in ``YYYY-MM-DD`` format.

        Returns
        -------
        dict or None
            Snapshot as a dict, or ``None`` if no snapshot exists on or before the date.
        """
        stmt = (
            select(InvestmentBalanceSnapshot)
            .where(
                InvestmentBalanceSnapshot.investment_id == investment_id,
                InvestmentBalanceSnapshot.date <= target_date,
            )
            .order_by(InvestmentBalanceSnapshot.date.desc())
            .limit(1)
        )
        df = pd.read_sql(stmt, self.db.bind)
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def update_snapshot(self, snapshot_id: int, **fields) -> None:
        """Update a snapshot by ID.

        Parameters
        ----------
        snapshot_id : int
            Primary key of the snapshot.
        **fields
            Column names and new values.

        Raises
        ------
        EntityNotFoundException
            If no snapshot with the given ID exists.
        """
        if not fields:
            return
        stmt = (
            update(InvestmentBalanceSnapshot)
            .where(InvestmentBalanceSnapshot.id == snapshot_id)
            .values(**fields)
        )
        result = self.db.execute(stmt)
        self.db.commit()
        if result.rowcount == 0:
            raise EntityNotFoundException(f"No snapshot found with ID {snapshot_id}")

    def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a snapshot by ID.

        Parameters
        ----------
        snapshot_id : int
            Primary key of the snapshot to delete.

        Raises
        ------
        EntityNotFoundException
            If no snapshot with the given ID exists.
        """
        stmt = delete(InvestmentBalanceSnapshot).where(
            InvestmentBalanceSnapshot.id == snapshot_id
        )
        result = self.db.execute(stmt)
        self.db.commit()
        if result.rowcount == 0:
            raise EntityNotFoundException(f"No snapshot found with ID {snapshot_id}")

    def delete_snapshots_for_investment(
        self, investment_id: int, source: Optional[str] = None
    ) -> None:
        """Delete all snapshots for an investment, optionally filtered by source.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        source : str, optional
            If provided, only delete snapshots with this source value.
        """
        stmt = delete(InvestmentBalanceSnapshot).where(
            InvestmentBalanceSnapshot.investment_id == investment_id
        )
        if source:
            stmt = stmt.where(InvestmentBalanceSnapshot.source == source)
        self.db.execute(stmt)
        self.db.commit()
```

**Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/repositories/test_investment_snapshots_repository.py -v
```

Expected: All 11 tests PASS.

**Step 5: Commit**

```bash
git add backend/repositories/investment_snapshots_repository.py tests/backend/unit/repositories/test_investment_snapshots_repository.py
git commit -m "feat: add InvestmentSnapshotsRepository with full test coverage"
```

---

### Task 4: Add snapshot service methods with tests (TDD)

**Files:**
- Modify: `backend/services/investments_service.py`
- Create: `tests/backend/unit/services/test_investments_snapshot_service.py`

**Step 1: Write the failing tests**

Create `tests/backend/unit/services/test_investments_snapshot_service.py`:

```python
"""
Unit tests for InvestmentsService snapshot-related methods.
"""

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from backend.models.investment import Investment
from backend.models.investment_balance_snapshot import InvestmentBalanceSnapshot
from backend.services.investments_service import InvestmentsService


def _create_investment(db_session: Session, tag: str = "Test Fund", **kwargs) -> int:
    """Helper to create an investment and return its ID."""
    inv = Investment(
        category="Investments",
        tag=tag,
        type="etf",
        name=kwargs.get("name", "Test"),
        interest_rate=kwargs.get("interest_rate"),
        interest_rate_type=kwargs.get("interest_rate_type", "fixed"),
        created_date="2024-01-01",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)
    return inv.id


class TestSnapshotCRUD:
    """Tests for snapshot create/read/delete via the service layer."""

    @patch("backend.services.investments_service.TransactionsService")
    def test_create_snapshot(self, mock_txn_cls, db_session: Session):
        """Verify creating a balance snapshot via the service."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-15", 50000.0)

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 50000.0
        assert snapshots[0]["source"] == "manual"

    @patch("backend.services.investments_service.TransactionsService")
    def test_get_balance_snapshots_returns_list_of_dicts(self, mock_txn_cls, db_session: Session):
        """Verify snapshots are returned as list of JSON-safe dicts."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-01", 50000.0)
        service.create_balance_snapshot(inv_id, "2025-02-01", 55000.0)

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 2
        assert all(isinstance(s, dict) for s in snapshots)

    @patch("backend.services.investments_service.TransactionsService")
    def test_delete_snapshot(self, mock_txn_cls, db_session: Session):
        """Verify deleting a snapshot by ID."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        service.create_balance_snapshot(inv_id, "2025-01-15", 50000.0)
        snapshots = service.get_balance_snapshots(inv_id)
        snapshot_id = snapshots[0]["id"]

        service.delete_balance_snapshot(snapshot_id)

        remaining = service.get_balance_snapshots(inv_id)
        assert len(remaining) == 0


class TestSnapshotAwareBalance:
    """Tests for snapshot-aware balance resolution."""

    @patch("backend.services.investments_service.TransactionsService")
    def test_current_balance_uses_latest_snapshot(self, mock_txn_cls, db_session: Session):
        """Verify current balance returns latest snapshot value when available."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        service.create_balance_snapshot(inv_id, "2025-06-01", 75000.0)

        balance = service.calculate_current_balance(inv_id)
        assert balance == 75000.0

    @patch("backend.services.investments_service.TransactionsService")
    def test_current_balance_falls_back_to_transactions(self, mock_txn_cls, db_session: Session):
        """Verify current balance falls back to transaction-based when no snapshots."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        # Mock transactions: deposit of -10000
        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -10000, "description": "Deposit"}]
        )

        balance = service.calculate_current_balance(inv_id)
        assert balance == 10000.0  # -(sum of -10000) = 10000


class TestFixedRateCalculation:
    """Tests for fixed-rate auto-calculation of snapshots."""

    @patch("backend.services.investments_service.TransactionsService")
    def test_calculate_fixed_rate_snapshots(self, mock_txn_cls, db_session: Session):
        """Verify fixed-rate calculation generates correct daily-compounded snapshots."""
        inv_id = _create_investment(
            db_session,
            tag="Savings",
            interest_rate=10.0,  # 10% annual
            interest_rate_type="fixed",
        )
        service = InvestmentsService(db_session)

        # Mock: single deposit of -100000 on 2025-01-01
        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -100000, "description": "Deposit"}]
        )

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) > 0
        # After 1 year at 10%, balance should be approximately 110000
        last_snapshot = snapshots[-1]
        assert abs(last_snapshot["balance"] - 110000) < 500  # Allow small rounding

    @patch("backend.services.investments_service.TransactionsService")
    def test_calculate_fixed_rate_handles_withdrawal(self, mock_txn_cls, db_session: Session):
        """Verify fixed-rate calculation correctly handles partial withdrawal."""
        inv_id = _create_investment(
            db_session,
            tag="Savings2",
            interest_rate=10.0,
            interest_rate_type="fixed",
        )
        service = InvestmentsService(db_session)

        # Deposit 100k on Jan 1, withdraw 50k on Jul 1
        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame([
            {"date": "2025-01-01", "amount": -100000, "description": "Deposit"},
            {"date": "2025-07-01", "amount": 50000, "description": "Withdrawal"},
        ])

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        snapshots = service.get_balance_snapshots(inv_id)
        last_snapshot = snapshots[-1]
        # After withdrawal, only ~50k+interest continues compounding
        # Balance should be significantly less than 110k
        assert last_snapshot["balance"] < 80000

    @patch("backend.services.investments_service.TransactionsService")
    def test_manual_snapshots_not_overwritten_by_calculation(self, mock_txn_cls, db_session: Session):
        """Verify manual snapshots are preserved when calculating fixed-rate snapshots."""
        inv_id = _create_investment(
            db_session,
            tag="Savings3",
            interest_rate=10.0,
            interest_rate_type="fixed",
        )
        service = InvestmentsService(db_session)

        # Add a manual snapshot first
        service.create_balance_snapshot(inv_id, "2025-06-01", 99999.0)

        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame(
            [{"date": "2025-01-01", "amount": -100000, "description": "Deposit"}]
        )

        service.calculate_fixed_rate_snapshots(inv_id, end_date="2026-01-01")

        # The manual snapshot should still be there
        snapshots = service.get_balance_snapshots(inv_id)
        manual_snapshots = [s for s in snapshots if s["source"] == "manual"]
        assert len(manual_snapshots) == 1
        assert manual_snapshots[0]["balance"] == 99999.0
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/services/test_investments_snapshot_service.py -v
```

Expected: AttributeError (methods don't exist yet).

**Step 3: Add service methods to `InvestmentsService`**

Modify `backend/services/investments_service.py`:

1. Add import at the top (after existing imports):
```python
from backend.repositories.investment_snapshots_repository import InvestmentSnapshotsRepository
```

2. Add to `__init__` (after `self.transactions_repo = TransactionsRepository(db)` on line 43):
```python
self.snapshots_repo = InvestmentSnapshotsRepository(db)
```

3. Add the following methods after `delete_investment()` (after line 181):

```python
    # ── Balance Snapshot Methods ──────────────────────────────────────

    def create_balance_snapshot(
        self,
        investment_id: int,
        date: str,
        balance: float,
        source: str = "manual",
    ) -> None:
        """Create or update a balance snapshot for an investment.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        date : str
            Snapshot date in ``YYYY-MM-DD`` format.
        balance : float
            Market value on this date.
        source : str
            Origin: ``"manual"``, ``"scraped"``, or ``"calculated"``.
        """
        self.snapshots_repo.upsert_snapshot(investment_id, date, balance, source)

    def get_balance_snapshots(self, investment_id: int) -> List[Dict[str, Any]]:
        """Get all balance snapshots for an investment.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        list[dict]
            Snapshot records ordered by date, with ``NaN`` replaced by ``None``.
        """
        df = self.snapshots_repo.get_snapshots_for_investment(investment_id)
        if df.empty:
            return []
        df = df.replace({np.nan: None})
        return df.to_dict(orient="records")

    def update_balance_snapshot(self, snapshot_id: int, **fields) -> None:
        """Update a balance snapshot.

        Parameters
        ----------
        snapshot_id : int
            ID of the snapshot to update.
        **fields
            Column names and new values.
        """
        self.snapshots_repo.update_snapshot(snapshot_id, **fields)

    def delete_balance_snapshot(self, snapshot_id: int) -> None:
        """Delete a balance snapshot by ID.

        Parameters
        ----------
        snapshot_id : int
            ID of the snapshot to delete.
        """
        self.snapshots_repo.delete_snapshot(snapshot_id)

    def calculate_fixed_rate_snapshots(
        self,
        investment_id: int,
        end_date: Optional[str] = None,
    ) -> None:
        """Generate calculated balance snapshots for a fixed-rate investment.

        Replays the transaction timeline with daily compounding to produce
        monthly snapshots. Existing ``"calculated"`` snapshots are cleared first;
        manual/scraped snapshots are preserved.

        Parameters
        ----------
        investment_id : int
            ID of the investment (must have ``interest_rate_type == "fixed"``
            and a non-null ``interest_rate``).
        end_date : str, optional
            End date for calculation in ``YYYY-MM-DD`` format.
            Defaults to today.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        inv = investment.iloc[0]

        if not inv.get("interest_rate") or inv.get("interest_rate_type") != "fixed":
            return

        annual_rate = float(inv["interest_rate"]) / 100.0
        daily_rate = (1 + annual_rate) ** (1 / 365) - 1

        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )
        if transactions_df.empty:
            return

        transactions_df = transactions_df.copy()
        transactions_df["date"] = pd.to_datetime(transactions_df["date"])
        transactions_df["amount"] = pd.to_numeric(
            transactions_df["amount"], errors="coerce"
        ).fillna(0.0)
        transactions_df = transactions_df.sort_values("date")

        start = transactions_df["date"].min().date()
        end = (
            datetime.strptime(end_date, "%Y-%m-%d").date()
            if end_date
            else date.today()
        )

        # Build a dict of date -> total transaction amount for that day
        txn_by_date = {}
        for _, row in transactions_df.iterrows():
            d = row["date"].date()
            txn_by_date[d] = txn_by_date.get(d, 0.0) + row["amount"]

        # Clear previous calculated snapshots
        self.snapshots_repo.delete_snapshots_for_investment(
            investment_id, source="calculated"
        )

        # Simulate daily compounding
        balance = 0.0
        current = start
        one_day = pd.Timedelta(days=1)

        while current <= end:
            # Apply transactions for this day (negative = deposit adds to balance)
            if current in txn_by_date:
                balance -= txn_by_date[current]  # negate: deposit(-1000) -> +1000

            # Apply daily interest
            if balance > 0:
                balance *= (1 + daily_rate)

            # Store monthly snapshots (first of month or end date)
            if current.day == 1 or current == end:
                self.snapshots_repo.upsert_snapshot(
                    investment_id,
                    current.strftime("%Y-%m-%d"),
                    round(balance, 2),
                    "calculated",
                )

            current += one_day
```

Note: The `one_day` addition needs to use `datetime.timedelta`. Update the import at the top of the file — change:
```python
from datetime import date, datetime
```
to:
```python
from datetime import date, datetime, timedelta
```

And change the loop to use `timedelta(days=1)` instead of `pd.Timedelta`:
```python
current += timedelta(days=1)
```

**Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/services/test_investments_snapshot_service.py -v
```

Expected: All tests PASS.

**Step 5: Run all existing tests to verify no regressions**

```bash
poetry run pytest tests/backend/unit/ -v
```

Expected: All tests PASS (including existing investment tests).

**Step 6: Commit**

```bash
git add backend/services/investments_service.py tests/backend/unit/services/test_investments_snapshot_service.py
git commit -m "feat: add snapshot CRUD and fixed-rate calculation to InvestmentsService"
```

---

### Task 5: Update existing KPI methods to be snapshot-aware

**Files:**
- Modify: `backend/services/investments_service.py` (methods: `calculate_current_balance`, `calculate_profit_loss`, `calculate_balance_over_time`, `get_portfolio_overview`)

**Step 1: Write failing tests for snapshot-aware profit/loss**

Add to `tests/backend/unit/services/test_investments_snapshot_service.py`:

```python
class TestSnapshotAwareProfitLoss:
    """Tests for profit/loss calculations using snapshot data."""

    @patch("backend.services.investments_service.TransactionsService")
    def test_profit_loss_uses_snapshot_balance(self, mock_txn_cls, db_session: Session):
        """Verify profit/loss uses snapshot balance instead of transaction-based."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        # Mock: deposited 100k
        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame(
            [{"date": "2024-01-01", "amount": -100000, "description": "Deposit"}]
        )

        # Snapshot says investment is now worth 120k (20k profit)
        service.create_balance_snapshot(inv_id, "2025-06-01", 120000.0)

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["current_balance"] == 120000.0
        assert metrics["absolute_profit_loss"] == 20000.0
        assert metrics["total_deposits"] == 100000.0

    @patch("backend.services.investments_service.TransactionsService")
    def test_profit_loss_without_snapshots_uses_transactions(self, mock_txn_cls, db_session: Session):
        """Verify profit/loss falls back to transaction-based when no snapshots."""
        inv_id = _create_investment(db_session)
        service = InvestmentsService(db_session)

        mock_txn_service = mock_txn_cls.return_value
        mock_txn_service.get_transactions_by_tag.return_value = pd.DataFrame(
            [{"date": "2024-01-01", "amount": -100000, "description": "Deposit"}]
        )

        metrics = service.calculate_profit_loss(inv_id)
        assert metrics["current_balance"] == 100000.0  # Transaction-based: -(-100000)
        assert metrics["absolute_profit_loss"] == 0.0
```

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/services/test_investments_snapshot_service.py::TestSnapshotAwareProfitLoss -v
```

Expected: `test_profit_loss_uses_snapshot_balance` FAILS (current code ignores snapshots).

**Step 3: Update `calculate_current_balance`**

In `backend/services/investments_service.py`, replace the `calculate_current_balance` method (lines 310-338):

```python
    def calculate_current_balance(self, investment_id: int) -> float:
        """Calculate the current balance for an investment.

        Uses the latest balance snapshot if available, otherwise falls back
        to the transaction-based calculation ``-(sum of amounts)``.
        Returns ``0.0`` for closed investments.

        Parameters
        ----------
        investment_id : int
            ID of the investment.

        Returns
        -------
        float
            Current balance.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return 0.0

        inv = investment.iloc[0]

        if inv["is_closed"]:
            return 0.0

        # Try snapshot first
        latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
            investment_id, date.today().strftime("%Y-%m-%d")
        )
        if latest is not None:
            return float(latest["balance"])

        # Fall back to transaction-based
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )
        return self._calculate_balance_from_transactions(transactions_df)
```

**Step 4: Update `calculate_profit_loss`**

In the `calculate_profit_loss` method (lines 398-501), replace the block that calculates `current_balance` for open investments (lines 459-464):

Replace:
```python
        if inv["is_closed"]:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - total_deposits
        else:
            current_balance = self._calculate_balance_from_transactions(transactions_df)
            absolute_profit_loss = current_balance - net_invested
```

With:
```python
        if inv["is_closed"]:
            current_balance = 0.0
            absolute_profit_loss = total_withdrawals - total_deposits
        else:
            # Try snapshot first, fall back to transaction-based
            latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                investment_id, date.today().strftime("%Y-%m-%d")
            )
            if latest is not None:
                current_balance = float(latest["balance"])
            else:
                current_balance = self._calculate_balance_from_transactions(transactions_df)
            absolute_profit_loss = current_balance - net_invested
```

**Step 5: Update `calculate_balance_over_time`**

Replace the `calculate_balance_over_time` method (lines 340-396) to interpolate between snapshots when available:

```python
    def calculate_balance_over_time(
        self, investment_id: int, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """Calculate balance at daily intervals between two dates for charting.

        When balance snapshots exist, interpolates linearly between snapshot
        points. Falls back to the transaction-based approach for dates before
        the first snapshot or when no snapshots exist.

        Parameters
        ----------
        investment_id : int
            ID of the investment.
        start_date : str
            Start of the date range in ``YYYY-MM-DD`` format.
        end_date : str
            End of the date range in ``YYYY-MM-DD`` format.

        Returns
        -------
        list[dict]
            List of ``{"date": str, "balance": float}`` dicts, one per day.
        """
        investment = self.investments_repo.get_by_id(investment_id)
        if investment.empty:
            return []

        inv = investment.iloc[0]
        transactions_df = self._get_all_transactions_for_investment(
            inv["category"], inv["tag"]
        )

        if transactions_df.empty:
            return []

        # For closed investments, stop at closed_date
        actual_end_date = end_date
        if inv["is_closed"] and inv["closed_date"]:
            closed_date = datetime.strptime(inv["closed_date"], "%Y-%m-%d").date()
            requested_end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            actual_end_date = min(closed_date, requested_end_date).strftime("%Y-%m-%d")

        snapshots_df = self.snapshots_repo.get_snapshots_for_investment(investment_id)

        if snapshots_df.empty:
            # No snapshots — use transaction-based approach
            dates = pd.date_range(start=start_date, end=actual_end_date, freq="D")
            balances = []
            for d in dates:
                balance = self._calculate_balance_from_transactions(
                    transactions_df, as_of_date=d.strftime("%Y-%m-%d")
                )
                balances.append({"date": d.strftime("%Y-%m-%d"), "balance": balance})
        else:
            # Snapshot-aware: interpolate between snapshots
            snapshots_df = snapshots_df.copy()
            snapshots_df["date"] = pd.to_datetime(snapshots_df["date"])
            snapshots_df = snapshots_df.sort_values("date")

            dates = pd.date_range(start=start_date, end=actual_end_date, freq="D")
            balances = []

            for d in dates:
                d_str = d.strftime("%Y-%m-%d")
                # Find surrounding snapshots
                before = snapshots_df[snapshots_df["date"] <= d]
                after = snapshots_df[snapshots_df["date"] >= d]

                if not before.empty and not after.empty:
                    prev = before.iloc[-1]
                    nxt = after.iloc[0]

                    if prev["date"] == nxt["date"]:
                        # Exact match
                        balance = float(prev["balance"])
                    else:
                        # Linear interpolation
                        total_days = (nxt["date"] - prev["date"]).days
                        elapsed_days = (d - prev["date"]).days
                        frac = elapsed_days / total_days if total_days > 0 else 0
                        balance = float(prev["balance"]) + frac * (
                            float(nxt["balance"]) - float(prev["balance"])
                        )
                elif not before.empty:
                    # After last snapshot — hold last known value
                    balance = float(before.iloc[-1]["balance"])
                else:
                    # Before first snapshot — use transaction-based
                    balance = self._calculate_balance_from_transactions(
                        transactions_df, as_of_date=d_str
                    )

                balances.append({"date": d_str, "balance": balance})

        if inv["is_closed"] and inv["closed_date"]:
            balances.append({"date": inv["closed_date"], "balance": 0.0})

        return balances
```

**Step 6: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/services/test_investments_snapshot_service.py -v
```

Expected: All tests PASS.

**Step 7: Run ALL existing tests**

```bash
poetry run pytest tests/backend/unit/ -v
```

Expected: All tests PASS (no regressions).

**Step 8: Commit**

```bash
git add backend/services/investments_service.py tests/backend/unit/services/test_investments_snapshot_service.py
git commit -m "feat: make KPI calculations snapshot-aware with transaction fallback"
```

---

### Task 6: Add API routes for balance snapshots

**Files:**
- Modify: `backend/routes/investments.py`

**Step 1: Add Pydantic schemas and routes**

Add to `backend/routes/investments.py`:

After the `InvestmentUpdate` schema (line 38), add:

```python
class BalanceSnapshotCreate(BaseModel):
    date: str
    balance: float


class BalanceSnapshotUpdate(BaseModel):
    date: Optional[str] = None
    balance: Optional[float] = None
```

After the `delete_investment` route (line 168), add:

```python
# ── Balance Snapshot Routes ───────────────────────────────────────


@router.get("/{investment_id}/balances")
async def get_balance_snapshots(
    investment_id: int, db: Session = Depends(get_database)
) -> list[dict[str, Any]]:
    """Get all balance snapshots for an investment."""
    service = InvestmentsService(db)
    return service.get_balance_snapshots(investment_id)


@router.post("/{investment_id}/balances")
async def create_balance_snapshot(
    investment_id: int,
    snapshot: BalanceSnapshotCreate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Create or update a balance snapshot for a specific date."""
    service = InvestmentsService(db)
    service.create_balance_snapshot(investment_id, snapshot.date, snapshot.balance)
    return {"status": "success"}


@router.put("/{investment_id}/balances/{snapshot_id}")
async def update_balance_snapshot(
    investment_id: int,
    snapshot_id: int,
    snapshot: BalanceSnapshotUpdate,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Update an existing balance snapshot."""
    service = InvestmentsService(db)
    updates = {k: v for k, v in snapshot.dict().items() if v is not None}
    service.update_balance_snapshot(snapshot_id, **updates)
    return {"status": "success"}


@router.delete("/{investment_id}/balances/{snapshot_id}")
async def delete_balance_snapshot(
    investment_id: int,
    snapshot_id: int,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a balance snapshot."""
    service = InvestmentsService(db)
    service.delete_balance_snapshot(snapshot_id)
    return {"status": "success"}


@router.post("/{investment_id}/balances/calculate")
async def calculate_fixed_rate_snapshots(
    investment_id: int,
    end_date: Optional[str] = None,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Trigger fixed-rate auto-calculation of balance snapshots."""
    service = InvestmentsService(db)
    service.calculate_fixed_rate_snapshots(investment_id, end_date=end_date)
    return {"status": "success"}
```

**Step 2: Verify routes load correctly**

```bash
poetry run python -c "from backend.routes.investments import router; print('Routes OK')"
```

**Step 3: Commit**

```bash
git add backend/routes/investments.py
git commit -m "feat: add balance snapshot API endpoints"
```

---

### Task 7: Add frontend API methods

**Files:**
- Modify: `frontend/src/services/api.ts` (lines 212-231, the `investmentsApi` object)

**Step 1: Add snapshot API methods**

Add the following methods to the `investmentsApi` object in `frontend/src/services/api.ts` (after the `getInvestmentAnalysis` entry):

```typescript
  // Balance snapshots
  getBalanceSnapshots: (id: number) =>
    api.get(`/investments/${id}/balances`),
  createBalanceSnapshot: (id: number, data: { date: string; balance: number }) =>
    api.post(`/investments/${id}/balances`, data),
  updateBalanceSnapshot: (investmentId: number, snapshotId: number, data: { date?: string; balance?: number }) =>
    api.put(`/investments/${investmentId}/balances/${snapshotId}`, data),
  deleteBalanceSnapshot: (investmentId: number, snapshotId: number) =>
    api.delete(`/investments/${investmentId}/balances/${snapshotId}`),
  calculateFixedRateSnapshots: (id: number, endDate?: string) =>
    api.post(`/investments/${id}/balances/calculate`, null, {
      params: endDate ? { end_date: endDate } : {},
    }),
```

**Step 2: Verify frontend compiles**

```bash
cd frontend && npm run build
```

**Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add balance snapshot methods to frontend API client"
```

---

### Task 8: Add "Update Balance" button to InvestmentCard

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

**Step 1: Add state and mutation for balance updates**

In the `Investments` component (after existing mutations around line 244), add:

```typescript
  const [balanceForm, setBalanceForm] = useState<{
    investmentId: number | null;
    date: string;
    balance: string;
  }>({ investmentId: null, date: new Date().toISOString().split("T")[0], balance: "" });

  const balanceSnapshotMutation = useMutation({
    mutationFn: (data: { investmentId: number; date: string; balance: number }) =>
      investmentsApi.createBalanceSnapshot(data.investmentId, {
        date: data.date,
        balance: data.balance,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      setBalanceForm({ investmentId: null, date: new Date().toISOString().split("T")[0], balance: "" });
    },
  });
```

**Step 2: Add "Update Balance" button to InvestmentCard**

Pass `onUpdateBalance` to `InvestmentCard`. Add to the component's props and render a button next to "View Analysis":

In the `InvestmentCard` component, add `onUpdateBalance` to the props and add a button before the "View Analysis" button:

```typescript
function InvestmentCard({
  inv,
  onViewAnalysis,
  onClose,
  onReopen,
  onDelete,
  onUpdateBalance,
}: any) {
```

Add this button before the existing "View Analysis" button (before line 103):

```tsx
      {!inv.is_closed && (
        <button
          onClick={() => onUpdateBalance(inv.id)}
          className="w-full py-2.5 mb-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 font-bold transition-all flex items-center justify-center gap-2 text-sm"
        >
          <DollarSign size={14} /> Update Balance
        </button>
      )}
```

**Step 3: Add balance update modal**

After the Analysis Modal section (after line 594), add a small modal for balance entry:

```tsx
      {/* Update Balance Modal */}
      {balanceForm.investmentId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">Update Balance</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Date
                </label>
                <input
                  type="date"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={balanceForm.date}
                  onChange={(e) =>
                    setBalanceForm({ ...balanceForm, date: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Current Market Value
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="e.g. 125000"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={balanceForm.balance}
                  onChange={(e) =>
                    setBalanceForm({ ...balanceForm, balance: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  setBalanceForm({
                    investmentId: null,
                    date: new Date().toISOString().split("T")[0],
                    balance: "",
                  })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!balanceForm.balance || balanceSnapshotMutation.isPending}
                onClick={() =>
                  balanceSnapshotMutation.mutate({
                    investmentId: balanceForm.investmentId!,
                    date: balanceForm.date,
                    balance: parseFloat(balanceForm.balance),
                  })
                }
                className="flex-[2] py-3 bg-blue-500 rounded-xl text-white font-bold hover:bg-blue-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {balanceSnapshotMutation.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
```

**Step 4: Wire up `onUpdateBalance` in InvestmentCard usage**

Update all `<InvestmentCard>` usages to pass `onUpdateBalance`:

```tsx
<InvestmentCard
  key={inv.id}
  inv={inv}
  onViewAnalysis={setSelectedAnalysisId}
  onClose={closeMutation.mutate}
  onReopen={reopenMutation.mutate}
  onDelete={deleteMutation.mutate}
  onUpdateBalance={(id: number) =>
    setBalanceForm({
      investmentId: id,
      date: new Date().toISOString().split("T")[0],
      balance: "",
    })
  }
/>
```

**Step 5: Verify frontend compiles**

```bash
cd frontend && npm run build
```

**Step 6: Commit**

```bash
git add frontend/src/pages/Investments.tsx
git commit -m "feat: add Update Balance button and modal to investment cards"
```

---

### Task 9: Add snapshots table and fixed-rate calculate button to analysis modal

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

**Step 1: Fetch snapshots in analysis modal**

Add a query for snapshots when the analysis modal is open:

```typescript
  const { data: selectedSnapshots } = useQuery({
    queryKey: ["investment-snapshots", selectedAnalysisId],
    queryFn: () =>
      selectedAnalysisId
        ? investmentsApi
            .getBalanceSnapshots(selectedAnalysisId)
            .then((res) => res.data)
        : null,
    enabled: !!selectedAnalysisId,
  });
```

Add delete snapshot mutation:

```typescript
  const deleteSnapshotMutation = useMutation({
    mutationFn: ({ investmentId, snapshotId }: { investmentId: number; snapshotId: number }) =>
      investmentsApi.deleteBalanceSnapshot(investmentId, snapshotId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const calculateMutation = useMutation({
    mutationFn: (investmentId: number) =>
      investmentsApi.calculateFixedRateSnapshots(investmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });
```

**Step 2: Add snapshots table inside analysis modal**

After the summary grid section (after the 3-column grid around line 584), add:

```tsx
                  {/* Balance Snapshots */}
                  {selectedSnapshots && selectedSnapshots.length > 0 && (
                    <div className="bg-[var(--surface-base)] rounded-2xl p-6 border border-[var(--surface-light)]">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-bold">Balance Snapshots</h3>
                        <span className="text-xs text-[var(--text-muted)]">
                          {selectedSnapshots.length} entries
                        </span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                              <th className="text-left py-2 font-bold">Date</th>
                              <th className="text-right py-2 font-bold">Balance</th>
                              <th className="text-center py-2 font-bold">Source</th>
                              <th className="text-right py-2 font-bold"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedSnapshots.map((snap: any) => (
                              <tr
                                key={snap.id}
                                className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30"
                              >
                                <td className="py-2 text-white font-medium">
                                  {snap.date}
                                </td>
                                <td className="py-2 text-right text-white font-bold">
                                  {formatCurrency(snap.balance)}
                                </td>
                                <td className="py-2 text-center">
                                  <span
                                    className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                                      snap.source === "manual"
                                        ? "bg-blue-500/20 text-blue-400"
                                        : snap.source === "calculated"
                                          ? "bg-purple-500/20 text-purple-400"
                                          : "bg-emerald-500/20 text-emerald-400"
                                    }`}
                                  >
                                    {snap.source}
                                  </span>
                                </td>
                                <td className="py-2 text-right">
                                  <button
                                    onClick={() =>
                                      deleteSnapshotMutation.mutate({
                                        investmentId: selectedAnalysisId!,
                                        snapshotId: snap.id,
                                      })
                                    }
                                    className="p-1 rounded hover:bg-red-500/20 text-[var(--text-muted)] hover:text-red-400 transition-all"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
```

**Step 3: Add fixed-rate calculate button**

In the analysis modal header area, add a calculate button for fixed-rate investments:

```tsx
                  {/* Fixed-Rate Calculation */}
                  {investments?.find((i: any) => i.id === selectedAnalysisId)
                    ?.interest_rate_type === "fixed" &&
                    investments?.find((i: any) => i.id === selectedAnalysisId)
                      ?.interest_rate && (
                    <button
                      onClick={() => calculateMutation.mutate(selectedAnalysisId!)}
                      disabled={calculateMutation.isPending}
                      className="px-4 py-2 bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
                    >
                      {calculateMutation.isPending
                        ? "Calculating..."
                        : "Calculate Fixed Rate"}
                    </button>
                  )}
```

**Step 4: Add staleness indicator to InvestmentCard**

This can be deferred to a follow-up. For now the snapshots table in the modal shows dates clearly enough.

**Step 5: Verify frontend compiles**

```bash
cd frontend && npm run build
```

**Step 6: Commit**

```bash
git add frontend/src/pages/Investments.tsx
git commit -m "feat: add snapshots table and fixed-rate calculate button to analysis modal"
```

---

### Task 10: End-to-end manual test

**Files:** None (testing only)

**Step 1: Start both servers**

```bash
python .claude/scripts/with_server.py -- sleep 300
```

Or separately:
```bash
poetry run uvicorn backend.main:app --reload
cd frontend && npm run dev
```

**Step 2: Verify the following manually**

1. Open Investments page
2. Create an investment (if none exist)
3. Click "Update Balance" on an investment card — enter a balance for today
4. Click "View Analysis" — verify the KPIs reflect the snapshot balance
5. Check the Snapshots table at the bottom of the analysis modal
6. Delete a snapshot from the table
7. For a fixed-rate investment: click "Calculate Fixed Rate" and verify calculated snapshots appear
8. Verify portfolio overview cards update based on snapshot data

**Step 3: Run full test suite**

```bash
poetry run pytest -v
```

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues found during manual testing"
```

---

### Task 11: Add staleness indicator to investment cards

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

**Step 1: Fetch latest snapshot date per investment**

This requires either a new lightweight API endpoint or enriching the `get_all_investments` response. The simplest approach: add a `latest_snapshot_date` field to each investment in the service layer.

Modify `InvestmentsService.get_all_investments()` to enrich each record:

```python
    def get_all_investments(self, include_closed: bool = False) -> List[Dict[str, Any]]:
        df = self.investments_repo.get_all_investments(include_closed=include_closed)
        df = df.replace({np.nan: None})
        records = df.to_dict(orient="records")

        # Enrich with latest snapshot date
        for record in records:
            latest = self.snapshots_repo.get_latest_snapshot_on_or_before(
                record["id"], date.today().strftime("%Y-%m-%d")
            )
            record["latest_snapshot_date"] = latest["date"] if latest else None

        return records
```

**Step 2: Display staleness in InvestmentCard**

In the `InvestmentCard` component, after the Created date section, add:

```tsx
        {inv.latest_snapshot_date && (
          <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)] col-span-2">
            <p className="text-[10px] uppercase font-bold text-[var(--text-muted)] mb-1">
              Last Balance Update
            </p>
            <p className={`text-xs font-bold mt-1.5 ${
              (() => {
                const days = Math.floor(
                  (Date.now() - new Date(inv.latest_snapshot_date).getTime()) /
                    (1000 * 60 * 60 * 24)
                );
                return days > 30 ? "text-amber-400" : "text-white";
              })()
            }`}>
              {inv.latest_snapshot_date}
              {(() => {
                const days = Math.floor(
                  (Date.now() - new Date(inv.latest_snapshot_date).getTime()) /
                    (1000 * 60 * 60 * 24)
                );
                return days > 30 ? ` (${days}d ago)` : "";
              })()}
            </p>
          </div>
        )}
```

**Step 3: Verify frontend compiles**

```bash
cd frontend && npm run build
```

**Step 4: Commit**

```bash
git add backend/services/investments_service.py frontend/src/pages/Investments.tsx
git commit -m "feat: add staleness indicator showing last balance update date"
```

---

### Task 12: Run full test suite and fix any regressions

**Files:** Various (depending on failures)

**Step 1: Run all backend tests**

```bash
poetry run pytest -v
```

**Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

**Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

**Step 4: Fix any issues found**

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: fix test regressions and lint issues"
```
