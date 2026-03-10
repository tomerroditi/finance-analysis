# Bank Balance & Prior Wealth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable users to enter bank account balances, auto-calculate prior wealth, recalculate on scrape, and display balances as dashboard KPI cards.

**Architecture:** New `bank_balances` table with dedicated repo/service/route. Prior wealth is a fixed anchor calculated when user enters balance. Balance recalculates on scrape. Sankey integration is virtual (no synthetic DB rows). Frontend adds inline balance input on Data Sources and KPI cards on Dashboard.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Pandas, React 19, TanStack Query, Tailwind CSS 4

---

### Task 1: Add Table Enum + ORM Model

**Files:**
- Modify: `backend/constants/tables.py:45` (add enum member after REFUND_LINKS)
- Create: `backend/models/bank_balance.py`
- Modify: `backend/models/__init__.py` (register new model)

**Step 1: Add BANK_BALANCES to Tables enum**

In `backend/constants/tables.py`, add after line 45 (`REFUND_LINKS = "refund_links"`):

```python
    BANK_BALANCES = "bank_balances"
```

Also add to the docstring (after `REFUND_LINKS` docstring entry):

```
    BANK_BALANCES : str
        Name of the table storing bank account balance snapshots.
```

**Step 2: Create ORM model**

Create `backend/models/bank_balance.py`:

```python
from sqlalchemy import Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class BankBalance(Base, TimestampMixin):
    """ORM model for bank account balance snapshots."""

    __tablename__ = Tables.BANK_BALANCES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, nullable=False)
    account_name = Column(String, nullable=False)
    balance = Column(Float, nullable=False)
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
    last_manual_update = Column(String, nullable=True)
    last_scrape_update = Column(String, nullable=True)
```

**Step 3: Register in models/__init__.py**

Add import:
```python
from backend.models.bank_balance import BankBalance
```

Add to `__all__`:
```python
    "BankBalance",
```

**Step 4: Write model test**

Create `tests/backend/unit/models/test_bank_balance_model.py`:

```python
"""
Unit tests for BankBalance ORM model.
"""

from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.models.bank_balance import BankBalance


class TestBankBalance:
    """Tests for BankBalance model."""

    def test_table_name(self):
        """Test that table name matches Tables enum."""
        assert BankBalance.__tablename__ == Tables.BANK_BALANCES.value

    def test_model_instantiation(self, db_session: Session):
        """Test model can be instantiated and persisted with all fields."""
        balance = BankBalance(
            provider="hapoalim",
            account_name="Main Account",
            balance=50000.0,
            prior_wealth_amount=20000.0,
            last_manual_update="2026-02-13",
            last_scrape_update="2026-02-13",
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.id is not None
        assert balance.provider == "hapoalim"
        assert balance.balance == 50000.0
        assert balance.prior_wealth_amount == 20000.0

    def test_default_prior_wealth(self, db_session: Session):
        """Test that prior_wealth_amount defaults to 0.0."""
        balance = BankBalance(
            provider="leumi",
            account_name="Savings",
            balance=10000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.prior_wealth_amount == 0.0

    def test_nullable_date_fields(self, db_session: Session):
        """Test that date fields can be None."""
        balance = BankBalance(
            provider="discount",
            account_name="Checking",
            balance=5000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.last_manual_update is None
        assert balance.last_scrape_update is None

    def test_timestamp_mixin(self, db_session: Session):
        """Test that created_at and updated_at are auto-populated."""
        balance = BankBalance(
            provider="mizrahi",
            account_name="Joint",
            balance=30000.0,
        )
        db_session.add(balance)
        db_session.commit()
        db_session.refresh(balance)
        assert balance.created_at is not None
        assert balance.updated_at is not None
```

**Step 5: Run tests**

```bash
poetry run pytest tests/backend/unit/models/test_bank_balance_model.py -v
```

Expected: All 5 tests PASS.

**Step 6: Commit**

```bash
git add backend/constants/tables.py backend/models/bank_balance.py backend/models/__init__.py tests/backend/unit/models/test_bank_balance_model.py
git commit -m "feat: add BankBalance ORM model and table enum"
```

---

### Task 2: Bank Balance Repository

**Files:**
- Create: `backend/repositories/bank_balance_repository.py`
- Test: `tests/backend/unit/repositories/test_bank_balance_repository.py`

**Step 1: Create repository**

Create `backend/repositories/bank_balance_repository.py`:

```python
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.bank_balance import BankBalance


class BankBalanceRepository:
    """Repository for bank account balance snapshots."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all bank balance records."""
        stmt = select(BankBalance)
        return pd.read_sql(stmt, self.db.bind)

    def get_by_account(self, provider: str, account_name: str) -> BankBalance | None:
        """Get balance record for a specific account."""
        stmt = select(BankBalance).where(
            BankBalance.provider == provider,
            BankBalance.account_name == account_name,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert(
        self,
        provider: str,
        account_name: str,
        balance: float,
        prior_wealth_amount: float,
        last_manual_update: str | None = None,
        last_scrape_update: str | None = None,
    ) -> BankBalance:
        """Create or update a balance record for an account."""
        existing = self.get_by_account(provider, account_name)
        if existing:
            existing.balance = balance
            existing.prior_wealth_amount = prior_wealth_amount
            if last_manual_update is not None:
                existing.last_manual_update = last_manual_update
            if last_scrape_update is not None:
                existing.last_scrape_update = last_scrape_update
            self.db.commit()
            return existing
        else:
            record = BankBalance(
                provider=provider,
                account_name=account_name,
                balance=balance,
                prior_wealth_amount=prior_wealth_amount,
                last_manual_update=last_manual_update,
                last_scrape_update=last_scrape_update,
            )
            self.db.add(record)
            self.db.commit()
            return record

    def delete_by_account(self, provider: str, account_name: str) -> bool:
        """Delete balance record for an account. Returns True if deleted."""
        existing = self.get_by_account(provider, account_name)
        if existing:
            self.db.delete(existing)
            self.db.commit()
            return True
        return False
```

**Step 2: Write repository test**

Create `tests/backend/unit/repositories/test_bank_balance_repository.py`:

```python
"""
Unit tests for BankBalanceRepository.
"""

from sqlalchemy.orm import Session

from backend.repositories.bank_balance_repository import BankBalanceRepository


class TestBankBalanceRepository:
    """Tests for BankBalanceRepository."""

    def test_get_all_empty(self, db_session: Session):
        """Get all returns empty DataFrame when no records exist."""
        repo = BankBalanceRepository(db_session)
        result = repo.get_all()
        assert result.empty

    def test_upsert_creates_new_record(self, db_session: Session):
        """Upsert creates a new record when none exists."""
        repo = BankBalanceRepository(db_session)
        record = repo.upsert(
            provider="hapoalim",
            account_name="Main",
            balance=50000.0,
            prior_wealth_amount=20000.0,
            last_manual_update="2026-02-13",
        )
        assert record.id is not None
        assert record.balance == 50000.0
        assert record.prior_wealth_amount == 20000.0

    def test_upsert_updates_existing_record(self, db_session: Session):
        """Upsert updates an existing record for the same account."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0, last_manual_update="2026-02-13")
        repo.upsert("hapoalim", "Main", 55000.0, 20000.0, last_scrape_update="2026-02-14")
        record = repo.get_by_account("hapoalim", "Main")
        assert record.balance == 55000.0
        assert record.last_manual_update == "2026-02-13"
        assert record.last_scrape_update == "2026-02-14"

    def test_get_by_account_not_found(self, db_session: Session):
        """Get by account returns None when not found."""
        repo = BankBalanceRepository(db_session)
        result = repo.get_by_account("nonexistent", "nope")
        assert result is None

    def test_get_all_returns_dataframe(self, db_session: Session):
        """Get all returns a DataFrame with all records."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0)
        repo.upsert("leumi", "Savings", 30000.0, 10000.0)
        result = repo.get_all()
        assert len(result) == 2
        assert "provider" in result.columns
        assert "balance" in result.columns

    def test_delete_by_account(self, db_session: Session):
        """Delete removes the record and returns True."""
        repo = BankBalanceRepository(db_session)
        repo.upsert("hapoalim", "Main", 50000.0, 20000.0)
        deleted = repo.delete_by_account("hapoalim", "Main")
        assert deleted is True
        assert repo.get_by_account("hapoalim", "Main") is None

    def test_delete_by_account_not_found(self, db_session: Session):
        """Delete returns False when record does not exist."""
        repo = BankBalanceRepository(db_session)
        deleted = repo.delete_by_account("nonexistent", "nope")
        assert deleted is False
```

**Step 3: Run tests**

```bash
poetry run pytest tests/backend/unit/repositories/test_bank_balance_repository.py -v
```

Expected: All 7 tests PASS.

**Step 4: Commit**

```bash
git add backend/repositories/bank_balance_repository.py tests/backend/unit/repositories/test_bank_balance_repository.py
git commit -m "feat: add BankBalanceRepository with CRUD operations"
```

---

### Task 3: Bank Balance Service

**Files:**
- Create: `backend/services/bank_balance_service.py`
- Test: `tests/backend/unit/services/test_bank_balance_service.py`

**Step 1: Create service**

Create `backend/services/bank_balance_service.py`:

```python
from datetime import date

from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.errors import ValidationException
from backend.repositories.bank_balance_repository import BankBalanceRepository
from backend.repositories.scraping_history_repository import ScrapingHistoryRepository
from backend.repositories.transactions_repository import TransactionsRepository


class BankBalanceService:
    """Service for managing bank account balances and prior wealth calculations."""

    def __init__(self, db: Session):
        self.db = db
        self.balance_repo = BankBalanceRepository(db)
        self.transactions_repo = TransactionsRepository(db)
        self.scraping_history_repo = ScrapingHistoryRepository(db)

    def get_all_balances(self) -> list[dict]:
        """
        Get all bank balance records.

        Returns
        -------
        list[dict]
            List of balance records with all fields.
        """
        df = self.balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(self, provider: str, account_name: str, balance: float) -> dict:
        """
        Set the current balance for a bank account.

        Calculates prior_wealth as: balance - sum(all scraped bank txns for this account).
        Validates that the last successful scrape for this account is today.

        Parameters
        ----------
        provider : str
            Bank provider name (e.g. "hapoalim").
        account_name : str
            User's display name for the account.
        balance : float
            The current balance entered by the user.

        Returns
        -------
        dict
            The created/updated balance record.

        Raises
        ------
        ValidationException
            If the last successful scrape is not today.
        """
        self._validate_scrape_is_today(provider, account_name)

        txn_sum = self._get_account_transaction_sum(provider, account_name)
        prior_wealth = balance - txn_sum

        record = self.balance_repo.upsert(
            provider=provider,
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=prior_wealth,
            last_manual_update=date.today().isoformat(),
        )

        return {
            "id": record.id,
            "provider": record.provider,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
            "last_scrape_update": record.last_scrape_update,
        }

    def recalculate_for_account(self, provider: str, account_name: str) -> None:
        """
        Recalculate balance after a scrape.

        balance = prior_wealth (fixed) + sum(all scraped bank txns).
        Only acts if a balance record exists for this account.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            User's display name for the account.
        """
        existing = self.balance_repo.get_by_account(provider, account_name)
        if not existing:
            return

        txn_sum = self._get_account_transaction_sum(provider, account_name)
        new_balance = existing.prior_wealth_amount + txn_sum

        self.balance_repo.upsert(
            provider=provider,
            account_name=account_name,
            balance=new_balance,
            prior_wealth_amount=existing.prior_wealth_amount,
            last_scrape_update=date.today().isoformat(),
        )

    def delete_for_account(self, provider: str, account_name: str) -> None:
        """
        Delete balance record when account is disconnected.

        Parameters
        ----------
        provider : str
            Bank provider name.
        account_name : str
            User's display name for the account.
        """
        self.balance_repo.delete_by_account(provider, account_name)

    def _validate_scrape_is_today(self, provider: str, account_name: str) -> None:
        """Validate that last successful scrape for this account is today."""
        last_scrape = self.scraping_history_repo.get_last_successful_scrape_date(
            service_name="banks",
            provider_name=provider,
            account_name=account_name,
        )
        if not last_scrape:
            raise ValidationException(
                "No successful scrape found for this account. Scrape today first."
            )

        scrape_date = last_scrape[:10]  # Extract YYYY-MM-DD from ISO timestamp
        if scrape_date != date.today().isoformat():
            raise ValidationException(
                "Last scrape is not from today. Scrape today first to set balance."
            )

    def _get_account_transaction_sum(self, provider: str, account_name: str) -> float:
        """Get the sum of all bank transactions for a specific account."""
        df = self.transactions_repo.get_table(service=Services.BANK.value)
        if df.empty:
            return 0.0
        mask = (df["provider"] == provider) & (df["account_name"] == account_name)
        return float(df.loc[mask, "amount"].sum())
```

**Step 2: Write service test**

Create `tests/backend/unit/services/test_bank_balance_service.py`:

```python
"""
Tests for BankBalanceService.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.constants.tables import Tables
from backend.errors import ValidationException
from backend.services.bank_balance_service import BankBalanceService


class TestBankBalanceService:
    """Tests for BankBalanceService functionality."""

    @pytest.fixture
    def service(self, db_session: Session):
        """Create a BankBalanceService instance."""
        return BankBalanceService(db_session)

    @pytest.fixture
    def setup_bank_transactions(self, db_session: Session):
        """Insert sample bank transactions."""
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.BANK.value}
            (id, date, amount, description, account_name, provider, source)
            VALUES
            ('txn1', '2026-02-01', -500.0, 'Rent', 'Main', 'hapoalim', 'bank_transactions'),
            ('txn2', '2026-02-05', 10000.0, 'Salary', 'Main', 'hapoalim', 'bank_transactions'),
            ('txn3', '2026-02-10', -200.0, 'Groceries', 'Main', 'hapoalim', 'bank_transactions'),
            ('txn4', '2026-02-10', -100.0, 'Other', 'Savings', 'leumi', 'bank_transactions')
            """)
        )
        db_session.commit()

    @pytest.fixture
    def setup_scrape_today(self, db_session: Session):
        """Insert a successful scrape record for today."""
        today = date.today().isoformat()
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.SCRAPING_HISTORY.value}
            (service_name, provider_name, account_name, date, status)
            VALUES
            ('banks', 'hapoalim', 'Main', '{today}T10:00:00', 'success')
            """)
        )
        db_session.commit()

    def test_get_all_balances_empty(self, service: BankBalanceService):
        """Get all balances returns empty list when no records exist."""
        result = service.get_all_balances()
        assert result == []

    def test_set_balance_calculates_prior_wealth(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
    ):
        """Set balance correctly calculates prior wealth from transaction sum."""
        # Txn sum for hapoalim/Main: -500 + 10000 + -200 = 9300
        # Prior wealth = 50000 - 9300 = 40700
        result = service.set_balance("hapoalim", "Main", 50000.0)
        assert result["balance"] == 50000.0
        assert result["prior_wealth_amount"] == 40700.0
        assert result["last_manual_update"] == date.today().isoformat()

    def test_set_balance_rejects_without_today_scrape(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
    ):
        """Set balance raises ValidationException when no scrape today."""
        with pytest.raises(ValidationException):
            service.set_balance("hapoalim", "Main", 50000.0)

    def test_set_balance_rejects_old_scrape(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        db_session: Session,
    ):
        """Set balance raises ValidationException when last scrape is not today."""
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.SCRAPING_HISTORY.value}
            (service_name, provider_name, account_name, date, status)
            VALUES
            ('banks', 'hapoalim', 'Main', '2026-02-01T10:00:00', 'success')
            """)
        )
        db_session.commit()
        with pytest.raises(ValidationException):
            service.set_balance("hapoalim", "Main", 50000.0)

    def test_recalculate_updates_balance(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
        db_session: Session,
    ):
        """Recalculate updates balance using fixed prior wealth + new txn sum."""
        service.set_balance("hapoalim", "Main", 50000.0)

        # Add a new transaction (simulating a new scrape)
        db_session.execute(
            text(f"""
            INSERT INTO {Tables.BANK.value}
            (id, date, amount, description, account_name, provider, source)
            VALUES
            ('txn_new', '2026-02-13', -1000.0, 'New expense', 'Main', 'hapoalim', 'bank_transactions')
            """)
        )
        db_session.commit()

        service.recalculate_for_account("hapoalim", "Main")

        balances = service.get_all_balances()
        assert len(balances) == 1
        # New txn sum: 9300 + (-1000) = 8300
        # New balance: 40700 (prior wealth) + 8300 = 49000
        assert balances[0]["balance"] == 49000.0
        assert balances[0]["prior_wealth_amount"] == 40700.0

    def test_recalculate_noop_without_balance_record(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
    ):
        """Recalculate does nothing when no balance record exists."""
        service.recalculate_for_account("hapoalim", "Main")
        assert service.get_all_balances() == []

    def test_delete_for_account(
        self,
        service: BankBalanceService,
        setup_bank_transactions,
        setup_scrape_today,
    ):
        """Delete removes balance record for the account."""
        service.set_balance("hapoalim", "Main", 50000.0)
        service.delete_for_account("hapoalim", "Main")
        assert service.get_all_balances() == []

    def test_set_balance_no_transactions(
        self,
        service: BankBalanceService,
        setup_scrape_today,
    ):
        """Set balance when account has no transactions: prior wealth = entered balance."""
        result = service.set_balance("hapoalim", "Main", 50000.0)
        assert result["prior_wealth_amount"] == 50000.0
        assert result["balance"] == 50000.0
```

**Step 3: Run tests**

```bash
poetry run pytest tests/backend/unit/services/test_bank_balance_service.py -v
```

Expected: All 8 tests PASS.

**Step 4: Commit**

```bash
git add backend/services/bank_balance_service.py tests/backend/unit/services/test_bank_balance_service.py
git commit -m "feat: add BankBalanceService with prior wealth calculation"
```

---

### Task 4: API Routes

**Files:**
- Create: `backend/routes/bank_balances.py`
- Modify: `backend/main.py` (register router)

**Step 1: Create route file**

Create `backend/routes/bank_balances.py`:

```python
"""
Bank Balance API routes.

Provides endpoints for managing bank account balances and prior wealth.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.bank_balance_service import BankBalanceService

router = APIRouter()


class SetBalanceRequest(BaseModel):
    provider: str
    account_name: str
    balance: float


@router.get("/")
async def get_bank_balances(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all bank balance records."""
    service = BankBalanceService(db)
    return service.get_all_balances()


@router.post("/")
async def set_bank_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict:
    """Set current balance for a bank account."""
    service = BankBalanceService(db)
    return service.set_balance(
        provider=request.provider,
        account_name=request.account_name,
        balance=request.balance,
    )
```

**Step 2: Register in main.py**

In `backend/main.py`, add to imports (after line 21, alongside other route imports):

```python
    bank_balances,
```

Add router registration (after line 82, the tagging_rules router):

```python
app.include_router(
    bank_balances.router, prefix="/api/bank-balances", tags=["Bank Balances"]
)
```

**Step 3: Run existing tests to verify no breakage**

```bash
poetry run pytest -v
```

Expected: All existing tests still PASS.

**Step 4: Commit**

```bash
git add backend/routes/bank_balances.py backend/main.py
git commit -m "feat: add bank balance API routes (GET and POST)"
```

---

### Task 5: Scraper Integration — Recalculate Balance After Scrape

**Files:**
- Modify: `backend/scraper/scrapers.py:297` (add hook after `_apply_auto_tagging()`)

**Step 1: Add recalculate method to Scraper class**

In `backend/scraper/scrapers.py`, add a new import at the top (after line 36):

```python
from backend.services.bank_balance_service import BankBalanceService
```

Add a new method to the `Scraper` class (after `_apply_auto_tagging()`, around line 704):

```python
    def _recalculate_bank_balances(self):
        """
        Recalculate bank balance after a successful scrape.
        Only runs for bank scrapers (service_name == 'banks').
        """
        if self.service_name != "banks":
            return
        try:
            with get_db_context() as db:
                balance_service = BankBalanceService(db)
                balance_service.recalculate_for_account(
                    self.provider_name, self.account_name
                )
        except Exception as e:
            print(
                f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{self.provider_name}: {self.account_name}: "
                f"Error recalculating bank balance: {str(e)}",
                flush=True,
            )
```

**Step 2: Call the method in pull_data_to_db()**

In `pull_data_to_db()`, after line 297 (`self._apply_auto_tagging()`), add:

```python
                self._recalculate_bank_balances()
```

So lines 296-298 become:

```python
                self._save_scraped_transactions()
                self._apply_auto_tagging()
                self._recalculate_bank_balances()
```

**Step 3: Run existing tests**

```bash
poetry run pytest -v
```

Expected: All tests still PASS.

**Step 4: Commit**

```bash
git add backend/scraper/scrapers.py
git commit -m "feat: recalculate bank balance after successful scrape"
```

---

### Task 6: Credentials Cleanup — Delete Balance on Account Disconnect

**Files:**
- Modify: `backend/routes/credentials.py:78-88` (add DB cleanup to delete endpoint)

**Step 1: Modify the delete endpoint**

In `backend/routes/credentials.py`, add imports:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.dependencies import get_database
from backend.services.bank_balance_service import BankBalanceService
```

Modify the `delete_credential` function (lines 78-88) to accept `db` and clean up balance:

```python
@router.delete("/{service}/{provider}/{account_name}")
async def delete_credential(
    service: str,
    provider: str,
    account_name: str,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete a credential and clean up associated data."""
    creds_service = CredentialsService()
    try:
        creds_service.delete_credential(service, provider, account_name)
        if service == "banks":
            balance_service = BankBalanceService(db)
            balance_service.delete_for_account(provider, account_name)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

Note: `Depends` import already exists, add `get_database` and `Session` imports.

**Step 2: Run tests**

```bash
poetry run pytest -v
```

Expected: All tests PASS.

**Step 3: Commit**

```bash
git add backend/routes/credentials.py
git commit -m "feat: clean up bank balance on credential disconnect"
```

---

### Task 7: Analysis Service — Inject Bank Prior Wealth into Sankey

**Files:**
- Modify: `backend/services/analysis_service.py:154-258` (update `get_sankey_data()`)

**Step 1: Add BankBalanceRepository import**

In `backend/services/analysis_service.py`, add import (after line 12):

```python
from backend.repositories.bank_balance_repository import BankBalanceRepository
```

**Step 2: Initialize repo in __init__**

Modify `__init__` (line 16-18) to add the balance repo:

```python
    def __init__(self, db: Session):
        self.db = db
        self.repo = TransactionsRepository(db)
        self.balance_repo = BankBalanceRepository(db)
```

**Step 3: Update get_sankey_data()**

In `get_sankey_data()`, after the Prior Wealth line from transactions (line 190-192), add bank prior wealth:

Replace lines 190-192:

```python
        sources[PRIOR_WEALTH_TAG] = other_income_df[
            other_income_df["tag"] == PRIOR_WEALTH_TAG
        ]["amount"].sum()
```

With:

```python
        txn_prior_wealth = other_income_df[
            other_income_df["tag"] == PRIOR_WEALTH_TAG
        ]["amount"].sum()
        bank_prior_wealth = self._get_bank_prior_wealth_total()
        sources[PRIOR_WEALTH_TAG] = txn_prior_wealth + bank_prior_wealth
```

**Step 4: Add helper method**

Add to the class (after `_get_income_mask`):

```python
    def _get_bank_prior_wealth_total(self) -> float:
        """Get total prior wealth from all bank balance records."""
        df = self.balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())
```

**Step 5: Run tests**

```bash
poetry run pytest -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add backend/services/analysis_service.py
git commit -m "feat: inject bank prior wealth into Sankey diagram"
```

---

### Task 8: Frontend API — Add bankBalancesApi

**Files:**
- Modify: `frontend/src/services/api.ts` (add new API group)

**Step 1: Add bankBalancesApi**

In `frontend/src/services/api.ts`, add after `analyticsApi` (after line 258):

```typescript
// Bank Balances API
export interface BankBalance {
  id: number;
  provider: string;
  account_name: string;
  balance: number;
  prior_wealth_amount: number;
  last_manual_update: string | null;
  last_scrape_update: string | null;
}

export const bankBalancesApi = {
  getAll: () => api.get<BankBalance[]>("/bank-balances/"),
  setBalance: (data: { provider: string; account_name: string; balance: number }) =>
    api.post<BankBalance>("/bank-balances/", data),
};
```

**Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add bankBalancesApi to frontend API service"
```

---

### Task 9: Frontend — Data Sources Page Inline Balance

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx`

**Step 1: Add imports and state**

Add to imports at top of file:

```tsx
import { DollarSign, Check, X } from "lucide-react";
import { bankBalancesApi, BankBalance } from "../services/api";
```

(The `DollarSign`, `Check`, `X` icons from lucide-react. Verify which icons are already imported.)

**Step 2: Add queries and state**

Add inside the component, alongside existing queries:

```tsx
// Bank Balances
const { data: bankBalances } = useQuery({
  queryKey: ["bank-balances", isTestMode],
  queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
});

const { data: lastScrapes } = useQuery({
  queryKey: ["last-scrapes", isTestMode],
  queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
});

const setBalanceMutation = useMutation({
  mutationFn: bankBalancesApi.setBalance,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
    setEditingBalance(null);
    setBalanceInput("");
  },
});

const [editingBalance, setEditingBalance] = useState<string | null>(null); // "provider|account_name"
const [balanceInput, setBalanceInput] = useState("");
```

Also add import for `scrapingApi` if not already imported.

**Step 3: Add helper functions**

```tsx
const getAccountBalance = (provider: string, accountName: string): BankBalance | undefined => {
  return bankBalances?.find(
    (b) => b.provider === provider && b.account_name === accountName
  );
};

const isScrapedToday = (provider: string, accountName: string): boolean => {
  const scrape = lastScrapes?.find(
    (s) => s.provider === provider && s.account_name === accountName
  );
  if (!scrape?.last_scrape_date) return false;
  const scrapeDate = new Date(scrape.last_scrape_date);
  const today = new Date();
  return (
    scrapeDate.getFullYear() === today.getFullYear() &&
    scrapeDate.getMonth() === today.getMonth() &&
    scrapeDate.getDate() === today.getDate()
  );
};

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" }).format(val);
```

**Step 4: Add inline balance UI to bank account rows**

Inside each account row (between the "Secure Connection" badge and the action buttons), add a balance section. Only show for bank accounts (`acc.service === "banks"`):

```tsx
{acc.service === "banks" && (() => {
  const bal = getAccountBalance(acc.provider, acc.account_name);
  const key = `${acc.provider}|${acc.account_name}`;
  const isEditing = editingBalance === key;
  const canSetBalance = isScrapedToday(acc.provider, acc.account_name);

  if (isEditing) {
    return (
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={balanceInput}
          onChange={(e) => setBalanceInput(e.target.value)}
          placeholder="Enter balance..."
          className="w-36 px-3 py-1.5 rounded-lg bg-[var(--bg)] border border-[var(--surface-light)] text-white text-sm focus:outline-none focus:border-[var(--primary)]"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Enter" && balanceInput) {
              setBalanceMutation.mutate({
                provider: acc.provider,
                account_name: acc.account_name,
                balance: parseFloat(balanceInput),
              });
            }
            if (e.key === "Escape") {
              setEditingBalance(null);
              setBalanceInput("");
            }
          }}
        />
        <button
          onClick={() => {
            if (balanceInput) {
              setBalanceMutation.mutate({
                provider: acc.provider,
                account_name: acc.account_name,
                balance: parseFloat(balanceInput),
              });
            }
          }}
          className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-all"
        >
          <Check size={16} />
        </button>
        <button
          onClick={() => { setEditingBalance(null); setBalanceInput(""); }}
          className="p-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all"
        >
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {bal ? (
        <span className="text-sm font-semibold text-amber-400">
          {formatCurrency(bal.balance)}
        </span>
      ) : (
        <span className="text-xs text-[var(--text-muted)] italic">No balance set</span>
      )}
      <button
        onClick={() => {
          if (canSetBalance) {
            setEditingBalance(key);
            setBalanceInput(bal ? String(bal.balance) : "");
          }
        }}
        disabled={!canSetBalance}
        className={`p-1.5 rounded-lg transition-all ${
          canSetBalance
            ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
            : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
        }`}
        title={canSetBalance ? "Set Balance" : "Scrape today first to set balance"}
      >
        <DollarSign size={16} />
      </button>
    </div>
  );
})()}
```

This block should be placed within the bank account row, between the left info section and the right action buttons section.

**Step 5: Manually test in browser**

Start both servers and verify:
- Bank account rows show "No balance set" or the current balance
- The DollarSign button is disabled when last scrape isn't today
- Clicking the button opens inline input
- Enter/Escape/Check/X work correctly

**Step 6: Commit**

```bash
git add frontend/src/pages/DataSources.tsx
git commit -m "feat: add inline balance input to Data Sources bank rows"
```

---

### Task 10: Frontend — Dashboard Bank Balances KPI Section

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add imports**

Add to imports:

```tsx
import { Landmark } from "lucide-react";
import { bankBalancesApi, BankBalance } from "../services/api";
```

**Step 2: Add query**

Add alongside existing queries:

```tsx
const { data: bankBalances } = useQuery({
  queryKey: ["bank-balances", isTestMode],
  queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
});
```

**Step 3: Add Bank Balances section in JSX**

After the existing 4-column KPI grid (`</div>` closing the `grid-cols-4` div), add:

```tsx
{bankBalances && bankBalances.length > 0 && (
  <div>
    <h2 className="text-lg font-semibold text-[var(--text-muted)] mb-4">Bank Balances</h2>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <StatCard
        title="Total Bank Balance"
        value={formatCurrency(bankBalances.reduce((sum, b) => sum + b.balance, 0))}
        icon={Landmark}
        color="bg-amber-500/20 text-amber-400"
      />
      {bankBalances.map((b) => (
        <StatCard
          key={`${b.provider}-${b.account_name}`}
          title={b.account_name}
          value={formatCurrency(b.balance)}
          icon={Landmark}
          color="bg-amber-500/20 text-amber-300"
        />
      ))}
    </div>
  </div>
)}
```

**Step 4: Manually test in browser**

Verify:
- When no balances exist, section is hidden
- When balances exist, shows "Total Bank Balance" + individual cards
- Amber/gold color scheme differentiates from main KPIs

**Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: add bank balances KPI section to Dashboard"
```

---

### Task 11: Run Full Test Suite + Manual Verification

**Step 1: Run all backend tests**

```bash
poetry run pytest -v
```

Expected: All tests PASS.

**Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors.

**Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```

Expected: No lint errors.

**Step 4: Manual end-to-end verification**

Start both servers:

```bash
python .claude/scripts/with_server.py -- echo "servers running"
```

Then manually verify:
1. Data Sources page: bank accounts show balance UI
2. Set a balance for an account (requires today's scrape)
3. Dashboard shows bank balance KPI cards
4. Sankey diagram includes bank prior wealth

**Step 5: Final commit (if any fixes needed)**

```bash
git add -A && git commit -m "fix: address issues from manual testing"
```
