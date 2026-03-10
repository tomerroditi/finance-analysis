# Cash Prior Wealth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a dedicated cash balance system with multiple envelopes and automatic prior wealth calculation.

**Architecture:** Mirror the existing `bank_balances` pattern with a new `cash_balances` table. Create `CashBalanceService` to manage balances, integrate with `TransactionsService` to auto-update on transaction changes, and expose via REST API.

**Tech Stack:** SQLAlchemy ORM, FastAPI, pytest, Pydantic

---

## Task 1: Add Constants for Cash Balances Table

**Files:**
- Modify: `backend/constants/tables.py`

**Step 1: View the current Tables enum**

Run: `grep -A 20 "class Tables" /Users/tomer/Desktop/finance-analysis/backend/constants/tables.py`

Expected output shows existing table constants like `BANK_BALANCES`, `BANK`, etc.

**Step 2: Add CASH_BALANCES constant**

In `backend/constants/tables.py`, add this line to the `Tables` enum (after `BANK_BALANCES`):

```python
CASH_BALANCES = "cash_balances"
```

**Step 3: Verify the change**

Run: `grep CASH_BALANCES /Users/tomer/Desktop/finance-analysis/backend/constants/tables.py`

Expected: Line shows `CASH_BALANCES = "cash_balances"`

**Step 4: Commit**

```bash
git add backend/constants/tables.py
git commit -m "feat: add CASH_BALANCES table constant"
```

---

## Task 2: Create CashBalance ORM Model

**Files:**
- Create: `backend/models/cash_balance.py`

**Step 1: Write the ORM model file**

Create `/Users/tomer/Desktop/finance-analysis/backend/models/cash_balance.py` with this content:

```python
"""
Cash balance snapshot model.
"""

from sqlalchemy import Column, Float, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class CashBalance(Base, TimestampMixin):
    """ORM model for cash envelope balances and prior wealth."""

    __tablename__ = Tables.CASH_BALANCES.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String, nullable=False, unique=True)
    balance = Column(Float, nullable=False)
    prior_wealth_amount = Column(Float, nullable=False, default=0.0)
    last_manual_update = Column(String, nullable=True)
```

**Step 2: Update models __init__.py to export CashBalance**

Modify `backend/models/__init__.py`. Add this import:

```python
from backend.models.cash_balance import CashBalance
```

And add `CashBalance` to the `__all__` list if one exists.

**Step 3: Verify the model loads**

Run: `python -c "from backend.models import CashBalance; print('CashBalance imported successfully')"`

Expected: Output shows `CashBalance imported successfully`

**Step 4: Commit**

```bash
git add backend/models/cash_balance.py backend/models/__init__.py
git commit -m "feat: create CashBalance ORM model"
```

---

## Task 3: Create CashBalanceRepository

**Files:**
- Create: `backend/repositories/cash_balance_repository.py`

**Step 1: Write the repository class**

Create `/Users/tomer/Desktop/finance-analysis/backend/repositories/cash_balance_repository.py`:

```python
"""
Repository for cash balance operations.
"""

from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from backend.models.cash_balance import CashBalance


class CashBalanceRepository:
    """Repository for managing cash balance records."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """
        Get all cash balance records as a DataFrame.

        Returns
        -------
        pd.DataFrame
            All cash balance records.
        """
        records = self.db.query(CashBalance).all()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame([r.__dict__ for r in records])

    def get_by_account_name(self, account_name: str) -> Optional[CashBalance]:
        """
        Get a cash balance record by account name.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.

        Returns
        -------
        CashBalance or None
            The balance record if found.
        """
        return self.db.query(CashBalance).filter(
            CashBalance.account_name == account_name
        ).first()

    def upsert(
        self,
        account_name: str,
        balance: float,
        prior_wealth_amount: float = 0.0,
        last_manual_update: Optional[str] = None,
    ) -> CashBalance:
        """
        Create or update a cash balance record.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.
        balance : float
            Current balance amount.
        prior_wealth_amount : float, optional
            Prior wealth anchor point.
        last_manual_update : str, optional
            ISO date string of last manual update.

        Returns
        -------
        CashBalance
            The created or updated record.
        """
        existing = self.get_by_account_name(account_name)
        if existing:
            existing.balance = balance
            existing.prior_wealth_amount = prior_wealth_amount
            if last_manual_update:
                existing.last_manual_update = last_manual_update
        else:
            existing = CashBalance(
                account_name=account_name,
                balance=balance,
                prior_wealth_amount=prior_wealth_amount,
                last_manual_update=last_manual_update,
            )
            self.db.add(existing)
        self.db.commit()
        return existing

    def delete_by_account_name(self, account_name: str) -> None:
        """
        Delete a cash balance record by account name.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.
        """
        self.db.query(CashBalance).filter(
            CashBalance.account_name == account_name
        ).delete()
        self.db.commit()
```

**Step 2: Verify the repository imports correctly**

Run: `python -c "from backend.repositories.cash_balance_repository import CashBalanceRepository; print('CashBalanceRepository imported successfully')"`

Expected: Output shows `CashBalanceRepository imported successfully`

**Step 3: Commit**

```bash
git add backend/repositories/cash_balance_repository.py
git commit -m "feat: create CashBalanceRepository"
```

---

## Task 4: Create CashBalanceService with Unit Tests

**Files:**
- Create: `backend/services/cash_balance_service.py`
- Create: `tests/backend/unit/services/test_cash_balance_service.py`

**Step 1: Write unit tests first (TDD)**

Create `/Users/tomer/Desktop/finance-analysis/tests/backend/unit/services/test_cash_balance_service.py`:

```python
"""
Unit tests for CashBalanceService.
"""

from datetime import date

import pytest
from sqlalchemy.orm import Session

from backend.errors import ValidationException
from backend.services.cash_balance_service import CashBalanceService
from backend.services.transactions_service import TransactionsService


class TestCashBalanceService:
    """Tests for CashBalanceService."""

    @pytest.fixture
    def service(self, db: Session):
        """Create service with fresh database."""
        return CashBalanceService(db)

    @pytest.fixture
    def transactions_service(self, db: Session):
        """Create transactions service for setup."""
        return TransactionsService(db)

    def test_set_balance_with_no_transactions(self, service):
        """
        When account has no transactions, prior_wealth equals balance.
        """
        result = service.set_balance("Wallet", 500.0)

        assert result["account_name"] == "Wallet"
        assert result["balance"] == 500.0
        assert result["prior_wealth_amount"] == 500.0

    def test_set_balance_with_existing_transactions(self, service, transactions_service, db):
        """
        Prior wealth is calculated as: balance - sum(transactions).
        """
        # Create two cash transactions: -50 and -30 (total -80)
        transactions_service.create_transaction(
            service="cash",
            date="2026-02-01",
            provider="manual",
            account_name="Wallet",
            description="Coffee",
            amount=-50.0,
        )
        transactions_service.create_transaction(
            service="cash",
            date="2026-02-02",
            provider="manual",
            account_name="Wallet",
            description="Lunch",
            amount=-30.0,
        )

        # User enters balance of 420
        result = service.set_balance("Wallet", 420.0)

        # prior_wealth = 420 - (-80) = 500
        assert result["balance"] == 420.0
        assert result["prior_wealth_amount"] == 500.0

    def test_set_balance_rejects_negative_balance(self, service):
        """
        Negative balance raises ValidationException.
        """
        with pytest.raises(ValidationException):
            service.set_balance("Wallet", -100.0)

    def test_recalculate_current_balance_updates_balance_keeps_prior_wealth(
        self, service, transactions_service
    ):
        """
        When a new transaction is added, recalculate updates balance but keeps prior_wealth fixed.
        """
        # Set initial balance with no transactions: prior_wealth=500, balance=500
        service.set_balance("Wallet", 500.0)

        # Add a new transaction: -50
        transactions_service.create_transaction(
            service="cash",
            date="2026-02-03",
            provider="manual",
            account_name="Wallet",
            description="Snack",
            amount=-50.0,
        )

        # Recalculate
        service.recalculate_current_balance("Wallet")

        # Fetch updated record
        record = service.get_by_account_name("Wallet")

        # prior_wealth should stay 500 (unchanged)
        # balance should be: 500 + (-50) = 450
        assert record["prior_wealth_amount"] == 500.0
        assert record["balance"] == 450.0

    def test_get_all_balances(self, service):
        """
        Returns all cash balance records.
        """
        service.set_balance("Wallet", 500.0)
        service.set_balance("Home Safe", 1000.0)

        balances = service.get_all_balances()

        assert len(balances) == 2
        account_names = [b["account_name"] for b in balances]
        assert "Wallet" in account_names
        assert "Home Safe" in account_names

    def test_get_by_account_name(self, service):
        """
        Retrieve a single balance record by account name.
        """
        service.set_balance("Wallet", 500.0)

        record = service.get_by_account_name("Wallet")

        assert record["account_name"] == "Wallet"
        assert record["balance"] == 500.0

    def test_get_total_prior_wealth(self, service):
        """
        Sum prior wealth across all accounts.
        """
        service.set_balance("Wallet", 500.0)
        service.set_balance("Home Safe", 1000.0)

        total = service.get_total_prior_wealth()

        # prior_wealth for each = balance (no transactions)
        assert total == 1500.0

    def test_delete_for_account(self, service):
        """
        Delete a cash balance record.
        """
        service.set_balance("Wallet", 500.0)

        service.delete_for_account("Wallet")

        record = service.get_by_account_name("Wallet")
        assert record is None
```

**Step 2: Write the service implementation**

Create `/Users/tomer/Desktop/finance-analysis/backend/services/cash_balance_service.py`:

```python
"""
Service for managing cash envelope balances and prior wealth calculations.
"""

from datetime import date

from sqlalchemy.orm import Session

from backend.constants.providers import Services
from backend.errors import ValidationException
from backend.repositories.cash_balance_repository import CashBalanceRepository
from backend.repositories.transactions_repository import TransactionsRepository


class CashBalanceService:
    """Service for managing cash envelope balances and prior wealth calculations."""

    def __init__(self, db: Session):
        self.db = db
        self.balance_repo = CashBalanceRepository(db)
        self.transactions_repo = TransactionsRepository(db)

    def get_all_balances(self) -> list[dict]:
        """
        Get all cash balance records.

        Returns
        -------
        list[dict]
            List of balance records with all fields.
        """
        df = self.balance_repo.get_all()
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def set_balance(self, account_name: str, balance: float) -> dict:
        """
        Set the current balance for a cash envelope.

        Calculates prior_wealth as: balance - sum(all cash txns for this account).

        Parameters
        ----------
        account_name : str
            Cash envelope account name (e.g., "Wallet", "Home Safe").
        balance : float
            The current balance entered by the user.

        Returns
        -------
        dict
            The created/updated balance record.

        Raises
        ------
        ValidationException
            If balance is negative.
        """
        if balance < 0:
            raise ValidationException("Balance cannot be negative.")

        txn_sum = self._get_account_transaction_sum(account_name)
        prior_wealth = balance - txn_sum

        record = self.balance_repo.upsert(
            account_name=account_name,
            balance=balance,
            prior_wealth_amount=prior_wealth,
            last_manual_update=date.today().isoformat(),
        )

        return {
            "id": record.id,
            "account_name": record.account_name,
            "balance": record.balance,
            "prior_wealth_amount": record.prior_wealth_amount,
            "last_manual_update": record.last_manual_update,
        }

    def recalculate_current_balance(self, account_name: str) -> None:
        """
        Recalculate balance after a transaction change.

        balance = prior_wealth (fixed) + sum(all cash txns).
        Only acts if a balance record exists for this account.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.
        """
        existing = self.balance_repo.get_by_account_name(account_name)
        if not existing:
            return

        txn_sum = self._get_account_transaction_sum(account_name)
        new_balance = existing.prior_wealth_amount + txn_sum

        self.balance_repo.upsert(
            account_name=account_name,
            balance=new_balance,
            prior_wealth_amount=existing.prior_wealth_amount,
        )

    def get_by_account_name(self, account_name: str) -> dict:
        """
        Get a single cash balance record by account name.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.

        Returns
        -------
        dict or None
            The balance record if found.
        """
        existing = self.balance_repo.get_by_account_name(account_name)
        if not existing:
            return None
        return {
            "id": existing.id,
            "account_name": existing.account_name,
            "balance": existing.balance,
            "prior_wealth_amount": existing.prior_wealth_amount,
            "last_manual_update": existing.last_manual_update,
        }

    def delete_for_account(self, account_name: str) -> None:
        """
        Delete balance record when account is closed.

        Parameters
        ----------
        account_name : str
            Cash envelope account name.
        """
        self.balance_repo.delete_by_account_name(account_name)

    def get_total_prior_wealth(self) -> float:
        """
        Get total prior wealth from all cash envelopes.

        Returns
        -------
        float
            Sum of prior_wealth_amount across all accounts.
        """
        df = self.balance_repo.get_all()
        if df.empty:
            return 0.0
        return float(df["prior_wealth_amount"].sum())

    def _get_account_transaction_sum(self, account_name: str) -> float:
        """Get the sum of all cash transactions for a specific account."""
        df = self.transactions_repo.get_table(service=Services.CASH.value)
        if df.empty:
            return 0.0
        mask = df["account_name"] == account_name
        return float(df.loc[mask, "amount"].sum())
```

**Step 3: Run the tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_cash_balance_service.py -v`

Expected: All tests pass (7 passed)

**Step 4: Commit**

```bash
git add tests/backend/unit/services/test_cash_balance_service.py backend/services/cash_balance_service.py
git commit -m "feat: add CashBalanceService with unit tests"
```

---

## Task 5: Create Cash Balances API Routes

**Files:**
- Create: `backend/routes/cash_balances.py`

**Step 1: Write the routes file**

Create `/Users/tomer/Desktop/finance-analysis/backend/routes/cash_balances.py`:

```python
"""
Cash Balance API routes.

Provides endpoints for managing cash envelope balances and prior wealth.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.cash_balance_service import CashBalanceService

router = APIRouter()


class SetBalanceRequest(BaseModel):
    """Request body for setting cash balance."""

    account_name: str
    balance: float


@router.get("/")
async def get_cash_balances(
    db: Session = Depends(get_database),
) -> list[dict]:
    """Get all cash balance records."""
    service = CashBalanceService(db)
    return service.get_all_balances()


@router.post("/")
async def set_cash_balance(
    request: SetBalanceRequest,
    db: Session = Depends(get_database),
) -> dict:
    """Set current balance for a cash envelope."""
    service = CashBalanceService(db)
    return service.set_balance(
        account_name=request.account_name,
        balance=request.balance,
    )
```

**Step 2: Register the route in main.py**

Modify `backend/main.py`. Find the section where other routers are included (look for `app.include_router`). Add this line:

```python
from backend.routes import cash_balances

# Then in the router registration section, add:
app.include_router(cash_balances.router, prefix="/api/cash-balances", tags=["cash-balances"])
```

**Step 3: Verify routes are registered**

Run: `grep -n "cash_balances" /Users/tomer/Desktop/finance-analysis/backend/main.py`

Expected: Shows the import and include_router lines

**Step 4: Test the endpoints manually**

Start the server: `poetry run uvicorn backend.main:app --reload`

In another terminal, test:

```bash
# Test GET (should return empty list initially)
curl http://localhost:8000/api/cash-balances

# Test POST
curl -X POST http://localhost:8000/api/cash-balances \
  -H "Content-Type: application/json" \
  -d '{"account_name": "Wallet", "balance": 500}'

# Test GET again
curl http://localhost:8000/api/cash-balances
```

Expected: POST returns the created record, GET returns list with one item

**Step 5: Stop the server and commit**

```bash
git add backend/routes/cash_balances.py backend/main.py
git commit -m "feat: add cash balances API routes"
```

---

## Task 6: Integrate with TransactionsService (Auto-Update on Changes)

**Files:**
- Modify: `backend/services/transactions_service.py`

**Step 1: View the current create_transaction method**

Run: `grep -n "def create_transaction" /Users/tomer/Desktop/finance-analysis/backend/services/transactions_service.py`

Note the line number where the method is defined.

**Step 2: Add cash balance recalculation to create_transaction**

In the `create_transaction` method, at the end (just before the `return` statement), add:

```python
        # Recalculate cash balance if this is a cash transaction
        if service == Services.CASH.value:
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(account_name)
```

**Step 3: View and update delete_transaction method**

Run: `grep -n "def delete_transaction" /Users/tomer/Desktop/finance-analysis/backend/services/transactions_service.py`

In the `delete_transaction` method, at the end, add:

```python
        # Recalculate cash balance if this was a cash transaction
        if source == "cash_transactions":
            from backend.services.cash_balance_service import CashBalanceService
            CashBalanceService(self.db).recalculate_current_balance(account_name)
```

**Step 4: View and update update_transaction method (if it exists)**

Run: `grep -n "def update_transaction" /Users/tomer/Desktop/finance-analysis/backend/services/transactions_service.py`

If found, add the same recalculation logic at the end.

**Step 5: Run tests to ensure nothing broke**

Run: `poetry run pytest tests/backend/unit/services/test_transactions_service.py -v`

Expected: All tests pass

**Step 6: Commit**

```bash
git add backend/services/transactions_service.py
git commit -m "feat: integrate cash balance recalculation in TransactionsService"
```

---

## Task 7: Update AnalysisService to Include Cash Prior Wealth in Overview

**Files:**
- Modify: `backend/services/analysis_service.py`

**Step 1: Find the get_overview method**

Run: `grep -n "def get_overview" /Users/tomer/Desktop/finance-analysis/backend/services/analysis_service.py`

Note the line number.

**Step 2: Locate where total_income is calculated**

Look for the section where `get_income_and_expenses()` is called. Add this code after that call:

```python
        # Add cash prior wealth to total income (same as bank/investment prior wealth)
        from backend.services.cash_balance_service import CashBalanceService
        cash_service = CashBalanceService(self.db)
        cash_prior_wealth = cash_service.get_total_prior_wealth()
        total_income += cash_prior_wealth
```

**Step 3: Run analysis tests**

Run: `poetry run pytest tests/backend/unit/services/test_analysis_service.py -v`

Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/services/analysis_service.py
git commit -m "feat: include cash prior wealth in overview KPIs"
```

---

## Task 8: Add Integration Tests for Cash Balance with Transactions

**Files:**
- Create: `tests/backend/integration/test_cash_balance_integration.py`

**Step 1: Write integration test file**

Create `/Users/tomer/Desktop/finance-analysis/tests/backend/integration/test_cash_balance_integration.py`:

```python
"""
Integration tests for cash balance with transaction lifecycle.
"""

import pytest
from sqlalchemy.orm import Session

from backend.services.cash_balance_service import CashBalanceService
from backend.services.transactions_service import TransactionsService


class TestCashBalanceIntegration:
    """Integration tests for cash balance and transactions together."""

    @pytest.fixture
    def cash_service(self, db: Session):
        """Create cash service."""
        return CashBalanceService(db)

    @pytest.fixture
    def txn_service(self, db: Session):
        """Create transactions service."""
        return TransactionsService(db)

    def test_cash_transaction_updates_balance_automatically(
        self, cash_service, txn_service
    ):
        """
        When user sets balance and then adds transactions,
        balance auto-updates but prior_wealth stays fixed.
        """
        # Set initial balance: no transactions yet
        cash_service.set_balance("Wallet", 500.0)

        # Verify initial state
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 500.0
        assert record["prior_wealth_amount"] == 500.0

        # Add a -50 transaction
        txn_service.create_transaction(
            service="cash",
            date="2026-02-01",
            provider="manual",
            account_name="Wallet",
            description="Coffee",
            amount=-50.0,
        )

        # Verify balance updated, prior_wealth unchanged
        record = cash_service.get_by_account_name("Wallet")
        assert record["balance"] == 450.0  # 500 + (-50)
        assert record["prior_wealth_amount"] == 500.0

    def test_deleting_cash_transaction_updates_balance(
        self, cash_service, txn_service, db
    ):
        """
        When a cash transaction is deleted, balance auto-recalculates.
        """
        # Set balance and add transactions
        cash_service.set_balance("Wallet", 450.0)

        # Add a -50 transaction
        response = txn_service.create_transaction(
            service="cash",
            date="2026-02-01",
            provider="manual",
            account_name="Wallet",
            description="Coffee",
            amount=-50.0,
        )
        txn_id = response["unique_id"]

        # Delete the transaction
        txn_service.delete_transaction(txn_id)

        # Balance should recalculate
        record = cash_service.get_by_account_name("Wallet")
        # prior_wealth=500, txns sum=0 now, balance should be 500
        assert record["balance"] == 500.0
        assert record["prior_wealth_amount"] == 500.0
```

**Step 2: Run integration tests**

Run: `poetry run pytest tests/backend/integration/test_cash_balance_integration.py -v`

Expected: All tests pass (2 passed)

**Step 3: Commit**

```bash
git add tests/backend/integration/test_cash_balance_integration.py
git commit -m "test: add integration tests for cash balance with transactions"
```

---

## Task 9: Create Migration and Update Database Schema

**Files:**
- Create: `backend/alembic/versions/<timestamp>_add_cash_balances_table.py`

**Step 1: Generate migration**

Run: `cd /Users/tomer/Desktop/finance-analysis && poetry run alembic revision --autogenerate -m "Add cash_balances table"`

Expected: New migration file created in `backend/alembic/versions/`

**Step 2: Verify migration file**

Run: `ls -lah backend/alembic/versions/ | tail -3`

Expected: Shows the newly created migration file

**Step 3: Apply migration**

Run: `poetry run alembic upgrade head`

Expected: Migration succeeds

**Step 4: Verify table exists**

Run: `sqlite3 ~/.finance-analysis/data.db ".tables" | grep cash`

Expected: Shows `cash_balances` table

**Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "database: add cash_balances table via migration"
```

---

## Task 10: Update KPI Documentation

**Files:**
- Modify: `.claude/rules/kpi_calculations.md`

**Step 1: View the current "Prior Wealth" section**

Run: `grep -A 30 "## Prior Wealth" /Users/tomer/Desktop/finance-analysis/.claude/rules/kpi_calculations.md | head -40`

**Step 2: Update the Cash Prior Wealth entry in the table**

Find this section:

```markdown
| **Cash prior wealth** | Cash transactions tagged `"Prior Wealth"` under `"Other Income"` | Manually created by user in cash transactions only |
```

Replace it with:

```markdown
| **Cash prior wealth** | `cash_balances.prior_wealth_amount` | Calculated when user enters current balance via API (`POST /api/cash-balances`). Auto-recalculates after transaction changes via service integration. |
```

**Step 3: Add a new subsection "Cash Balance Calculation"**

After the "Prior Wealth in Overview & Sankey" section, add:

```markdown
### Cash Prior Wealth Calculation

Cash balance tracking uses a dedicated `cash_balances` table with per-envelope balance and prior wealth records:

**Formula:**
```
prior_wealth = user_entered_balance - sum(all cash transactions for account_name)
current_balance = prior_wealth + sum(all cash transactions for account_name to date)
```

**Triggers:**
- **Prior wealth recalculates ONLY when:** User manually calls `POST /api/cash-balances` to enter new balance
- **Current balance auto-updates WHEN:** Cash transaction is created, updated, or deleted

**Envelopes:**
- Multiple cash envelopes supported, identified by `account_name` field
- Each envelope has independent prior wealth and balance
- Total cash prior wealth sums across all envelopes
```

**Step 4: Verify the changes**

Run: `grep -A 10 "Cash Prior Wealth Calculation" /Users/tomer/Desktop/finance-analysis/.claude/rules/kpi_calculations.md`

Expected: Shows the new section

**Step 5: Commit**

```bash
git add .claude/rules/kpi_calculations.md
git commit -m "docs: update KPI documentation for cash prior wealth system"
```

---

## Task 11: Add Route Tests (Endpoint Tests)

**Files:**
- Create: `tests/backend/routes/test_cash_balances_routes.py`

**Step 1: Write route tests**

Create `/Users/tomer/Desktop/finance-analysis/tests/backend/routes/test_cash_balances_routes.py`:

```python
"""
Route tests for cash balance endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.transactions_service import TransactionsService


class TestCashBalancesRoutes:
    """Tests for cash balances API routes."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_get_cash_balances_empty(self, client):
        """
        GET /api/cash-balances returns empty list initially.
        """
        response = client.get("/api/cash-balances")

        assert response.status_code == 200
        assert response.json() == []

    def test_post_cash_balance_creates_record(self, client):
        """
        POST /api/cash-balances creates a new balance record.
        """
        payload = {"account_name": "Wallet", "balance": 500.0}
        response = client.post("/api/cash-balances", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["account_name"] == "Wallet"
        assert data["balance"] == 500.0
        assert data["prior_wealth_amount"] == 500.0

    def test_post_cash_balance_negative_rejected(self, client):
        """
        POST with negative balance returns 400 error.
        """
        payload = {"account_name": "Wallet", "balance": -100.0}
        response = client.post("/api/cash-balances", json=payload)

        assert response.status_code == 400

    def test_get_cash_balances_after_create(self, client):
        """
        GET after creating returns the record.
        """
        # Create
        payload = {"account_name": "Wallet", "balance": 500.0}
        client.post("/api/cash-balances", json=payload)

        # Get
        response = client.get("/api/cash-balances")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["account_name"] == "Wallet"
```

**Step 2: Run route tests**

Run: `poetry run pytest tests/backend/routes/test_cash_balances_routes.py -v`

Expected: All tests pass (4 passed)

**Step 3: Commit**

```bash
git add tests/backend/routes/test_cash_balances_routes.py
git commit -m "test: add route tests for cash balances endpoints"
```

---

## Task 12: Verify Full Test Suite Passes

**Files:** (No new files, verification only)

**Step 1: Run all backend tests**

Run: `poetry run pytest tests/backend/ -v --tb=short`

Expected: All tests pass (no failures)

**Step 2: Check for any import errors or warnings**

Run: `poetry run pytest tests/backend/ --collect-only`

Expected: All tests collect successfully with no errors

**Step 3: Commit final state**

```bash
git status
# Should be clean
```

Expected: No uncommitted changes

---

## Execution Complete

All tasks are defined above. The implementation follows TDD with frequent commits. Ready for execution using either:

1. **Subagent-driven** (this session) - Fresh subagent per task
2. **Parallel session** (separate worktree) - Batch execution with checkpoints

Which execution approach would you prefer?

