# Investment Prior Wealth Refactor — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give each `Investment` record its own `prior_wealth_amount` column, mirroring how `BankBalance.prior_wealth_amount` works, replacing the portfolio-level `sync_prior_wealth_offset` approach for `manual_investments`.

**Architecture:** Add `prior_wealth_amount` to the `Investment` model. `InvestmentsService` recalculates it whenever a `ManualInvestmentTransaction` is created or deleted. `TransactionsService` injects synthetic prior-wealth rows for investments (like it already does for banks) and removes the old `manual_investments` offset logic. A startup migration seeds existing data.

**Tech Stack:** FastAPI, SQLAlchemy ORM, SQLite, Pandas, pytest

---

## Task 1: Add `prior_wealth_amount` to the `Investment` model

**Files:**
- Modify: `backend/models/investment.py`

**Step 1: Add the column**

In `backend/models/investment.py`, add this line after `notes`:

```python
prior_wealth_amount = Column(Float, nullable=False, default=0.0)
```

**Step 2: Verify the model builds**

```bash
poetry run python -c "from backend.models.investment import Investment; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add backend/models/investment.py
git commit -m "feat: add prior_wealth_amount column to Investment model"
```

---

## Task 2: Add `update_prior_wealth()` to `InvestmentsRepository`

**Files:**
- Modify: `backend/repositories/investments_repository.py`
- Test: `tests/backend/unit/repositories/test_investments_repository.py` (create if needed)

**Step 1: Write the failing test**

Find or create `tests/backend/unit/repositories/test_investments_repository.py`. Add:

```python
"""Tests for InvestmentsRepository."""

import pytest
from backend.repositories.investments_repository import InvestmentsRepository
from backend.models.investment import Investment


class TestInvestmentsRepositoryPriorWealth:
    """Tests for prior_wealth_amount persistence."""

    def test_update_prior_wealth_persists_value(self, db_session):
        """Verify update_prior_wealth writes the value to the DB."""
        inv = Investment(
            category="Investments",
            tag="Test Fund",
            type="etf",
            name="Test",
            created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        repo = InvestmentsRepository(db_session)
        repo.update_prior_wealth(inv.id, 15000.0)

        db_session.refresh(inv)
        assert inv.prior_wealth_amount == 15000.0

    def test_update_prior_wealth_handles_zero(self, db_session):
        """Verify prior_wealth_amount can be set to zero."""
        inv = Investment(
            category="Investments",
            tag="Zero Fund",
            type="etf",
            name="Zero",
            created_date="2024-01-01",
            prior_wealth_amount=5000.0,
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        repo = InvestmentsRepository(db_session)
        repo.update_prior_wealth(inv.id, 0.0)

        db_session.refresh(inv)
        assert inv.prior_wealth_amount == 0.0
```

**Step 2: Run to verify failure**

```bash
poetry run pytest tests/backend/unit/repositories/test_investments_repository.py -v
```

Expected: `FAIL` — `update_prior_wealth` not defined.

**Step 3: Implement the method**

In `backend/repositories/investments_repository.py`, add after `update_investment`:

```python
def update_prior_wealth(self, investment_id: int, amount: float) -> None:
    """Update the stored prior_wealth_amount for an investment."""
    stmt = (
        update(Investment)
        .where(Investment.id == investment_id)
        .values(prior_wealth_amount=amount)
    )
    self.db.execute(stmt)
    self.db.commit()
```

**Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/repositories/test_investments_repository.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/repositories/investments_repository.py tests/backend/unit/repositories/test_investments_repository.py
git commit -m "feat: add update_prior_wealth to InvestmentsRepository"
```

---

## Task 3: Add `recalculate_prior_wealth` and `get_total_prior_wealth` to `InvestmentsService`

**Files:**
- Modify: `backend/services/investments_service.py`
- Test: `tests/backend/unit/services/test_investments_service.py`

**Step 1: Write the failing tests**

Add to `tests/backend/unit/services/test_investments_service.py`:

```python
class TestInvestmentsServicePriorWealth:
    """Tests for prior wealth calculation and storage."""

    def test_recalculate_prior_wealth_sums_transactions(self, db_session, seed_investments):
        """Verify recalculate_prior_wealth stores -(sum of all txns) on Investment."""
        service = InvestmentsService(db_session)
        stock_fund = seed_investments["investments"][0]

        # stock_fund txns: -10000, -2000 → prior_wealth = -(-12000) = 12000
        service.recalculate_prior_wealth(stock_fund.id)

        db_session.refresh(stock_fund)
        assert stock_fund.prior_wealth_amount == pytest.approx(12000.0)

    def test_recalculate_prior_wealth_handles_no_transactions(self, db_session):
        """Verify prior_wealth_amount is 0 when investment has no transactions."""
        from backend.models.investment import Investment as InvestmentModel
        inv = InvestmentModel(
            category="Investments",
            tag="Empty Fund",
            type="etf",
            name="Empty",
            created_date="2024-01-01",
        )
        db_session.add(inv)
        db_session.commit()
        db_session.refresh(inv)

        service = InvestmentsService(db_session)
        service.recalculate_prior_wealth(inv.id)

        db_session.refresh(inv)
        assert inv.prior_wealth_amount == 0.0

    def test_get_total_prior_wealth_sums_open_investments(self, db_session, seed_investments):
        """Verify get_total_prior_wealth sums prior_wealth_amount for non-closed investments only."""
        # Manually set prior_wealth_amount on the seeded investments
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0   # open
        bond_fund.prior_wealth_amount = -160.0     # closed — should be excluded
        db_session.commit()

        service = InvestmentsService(db_session)
        total = service.get_total_prior_wealth()

        assert total == pytest.approx(12000.0)

    def test_get_total_prior_wealth_returns_zero_when_empty(self, db_session):
        """Verify get_total_prior_wealth returns 0.0 when no open investments exist."""
        service = InvestmentsService(db_session)
        assert service.get_total_prior_wealth() == 0.0
```

**Step 2: Run to verify failure**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py::TestInvestmentsServicePriorWealth -v
```

Expected: FAIL

**Step 3: Implement the methods**

In `backend/services/investments_service.py`, add after `delete_investment`:

```python
def recalculate_prior_wealth(self, investment_id: int) -> None:
    """
    Calculate and store prior_wealth_amount for an investment.

    Reads all ManualInvestmentTransactions for the investment and stores
    -(sum of amounts) as prior_wealth_amount. Equivalent to
    BankBalanceService.recalculate_for_account for bank accounts.

    Parameters
    ----------
    investment_id : int
        ID of the investment to recalculate.
    """
    investment = self.investments_repo.get_by_id(investment_id)
    inv = investment.iloc[0]
    transactions_df = self._get_all_transactions_for_investment(
        inv["category"], inv["tag"]
    )
    if transactions_df.empty:
        prior_wealth = 0.0
    else:
        if "amount" in transactions_df.columns:
            transactions_df["amount"] = pd.to_numeric(
                transactions_df["amount"], errors="coerce"
            ).fillna(0.0)
        prior_wealth = -float(transactions_df["amount"].sum())
    self.investments_repo.update_prior_wealth(investment_id, prior_wealth)

def get_total_prior_wealth(self) -> float:
    """
    Sum prior_wealth_amount across all open (non-closed) investments.

    Returns
    -------
    float
        Total prior wealth across open investments.
    """
    df = self.investments_repo.get_all_investments(include_closed=False)
    if df.empty:
        return 0.0
    return float(df["prior_wealth_amount"].sum())
```

**Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py::TestInvestmentsServicePriorWealth -v
```

Expected: PASS

**Step 5: Run all investment service tests to check no regressions**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py -v
```

Expected: All PASS

**Step 6: Commit**

```bash
git add backend/services/investments_service.py tests/backend/unit/services/test_investments_service.py
git commit -m "feat: add recalculate_prior_wealth and get_total_prior_wealth to InvestmentsService"
```

---

## Task 4: Update `TransactionsService` — add investment prior wealth rows, remove old offset logic

**Files:**
- Modify: `backend/services/transactions_service.py`
- Test: `tests/backend/unit/services/test_transactions_service.py`

### 4a: Add `InvestmentsRepository` to `TransactionsService.__init__`

**Step 1: Update the import and `__init__`**

In `backend/services/transactions_service.py`, add import at the top:

```python
from backend.repositories.investments_repository import InvestmentsRepository
```

In `__init__`, add after `self.balance_repo = BankBalanceRepository(db)`:

```python
self.investments_repo = InvestmentsRepository(db)
```

**Step 2: Verify no import errors**

```bash
poetry run python -c "from backend.services.transactions_service import TransactionsService; print('OK')"
```

Expected: `OK`

### 4b: Add `_build_investment_prior_wealth_rows()`

**Step 1: Write the failing test**

Add to `tests/backend/unit/services/test_transactions_service.py` in the `TestTransactionsServiceDataRetrieval` class:

```python
def test_get_data_for_analysis_includes_investment_prior_wealth(
    self, db_session, seed_investments
):
    """Verify investment prior wealth synthetic rows appear in analysis data."""
    from backend.models.investment import Investment as InvModel

    # Set prior_wealth_amount on the open investment
    stock_fund = seed_investments["investments"][0]
    stock_fund.prior_wealth_amount = 12000.0
    db_session.commit()

    service = TransactionsService(db_session)
    result = service.get_data_for_analysis()

    tag_col = TransactionsTableFields.TAG.value
    source_col = TransactionsTableFields.SOURCE.value

    inv_pw_rows = result[
        (result[tag_col] == PRIOR_WEALTH_TAG) & (result[source_col] == "investments")
    ]
    # Only stock_fund is open (bond_fund is closed), so 1 row
    assert len(inv_pw_rows) == 1
    assert inv_pw_rows.iloc[0]["amount"] == pytest.approx(12000.0)
    assert inv_pw_rows.iloc[0]["category"] == IncomeCategories.OTHER_INCOME.value
```

**Step 2: Run to verify failure**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServiceDataRetrieval::test_get_data_for_analysis_includes_investment_prior_wealth -v
```

Expected: FAIL

**Step 3: Implement `_build_investment_prior_wealth_rows()`**

In `backend/services/transactions_service.py`, add after `_build_bank_prior_wealth_rows`:

```python
def _build_investment_prior_wealth_rows(self) -> pd.DataFrame:
    """Build synthetic prior wealth rows from Investment.prior_wealth_amount.

    Mirrors _build_bank_prior_wealth_rows for bank accounts.
    Only includes open (non-closed) investments with prior_wealth_amount != 0.
    """
    investments_df = self.investments_repo.get_all_investments(include_closed=False)
    if investments_df.empty:
        return pd.DataFrame()

    rows = []
    for _, inv in investments_df.iterrows():
        if inv["prior_wealth_amount"] == 0:
            continue
        rows.append({
            TransactionsTableFields.ID.value: f"inv_pw_{inv['id']}",
            TransactionsTableFields.DATE.value: inv.get("created_date", ""),
            TransactionsTableFields.PROVIDER.value: "manual_investments",
            TransactionsTableFields.ACCOUNT_NAME.value: inv["name"],
            TransactionsTableFields.ACCOUNT_NUMBER.value: None,
            TransactionsTableFields.DESCRIPTION.value: f"Prior Wealth ({inv['name']})",
            TransactionsTableFields.AMOUNT.value: inv["prior_wealth_amount"],
            TransactionsTableFields.CATEGORY.value: IncomeCategories.OTHER_INCOME.value,
            TransactionsTableFields.TAG.value: PRIOR_WEALTH_TAG,
            TransactionsTableFields.UNIQUE_ID.value: f"inv_pw_{inv['id']}",
            TransactionsTableFields.SOURCE.value: "investments",
            TransactionsTableFields.SPLIT_ID.value: None,
            TransactionsTableFields.TYPE.value: "normal",
        })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)
```

**Step 4: Wire it into `get_data_for_analysis()`**

In `get_data_for_analysis()`, add after the bank prior wealth append block:

```python
investment_prior_wealth_df = self._build_investment_prior_wealth_rows()
if not investment_prior_wealth_df.empty:
    dfs.append(investment_prior_wealth_df)
```

**Step 5: Run the new test**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServiceDataRetrieval::test_get_data_for_analysis_includes_investment_prior_wealth -v
```

Expected: PASS

### 4c: Remove `manual_investments` from `sync_prior_wealth_offset`

**Step 1: Check existing prior wealth tests that cover `manual_investments`**

Look in `test_transactions_service.py` for `TestTransactionsServicePriorWealth`. Any test that exercises `sync_prior_wealth_offset` for `manual_investments` needs to be removed or updated to verify it no longer runs that path.

**Step 2: Write a new test verifying manual_investments is NOT synced**

Add to `TestTransactionsServicePriorWealth` in `test_transactions_service.py`:

```python
def test_sync_prior_wealth_skips_manual_investments(self, db_session):
    """Verify sync_prior_wealth_offset does not create offset for manual_investments."""
    from backend.models.transaction import ManualInvestmentTransaction
    inv_tx = ManualInvestmentTransaction(
        id="test_inv_1",
        date="2024-01-01",
        provider="manual_investments",
        account_name="Investment Account",
        description="Deposit",
        amount=-5000.0,
        category="Investments",
        tag="Stock Fund",
        source="manual_investment_transactions",
        type="normal",
        status="completed",
    )
    db_session.add(inv_tx)
    db_session.commit()

    service = TransactionsService(db_session)
    service.sync_prior_wealth_offset()  # should NOT touch manual_investments

    from backend.repositories.transactions_repository import TransactionsRepository
    repo = TransactionsRepository(db_session)
    inv_df = repo.get_table("manual_investments")
    pw_rows = inv_df[inv_df["tag"] == PRIOR_WEALTH_TAG]
    assert len(pw_rows) == 0
```

**Step 3: Run to verify it currently FAILS** (current code creates offset for manual_investments)

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_sync_prior_wealth_skips_manual_investments -v
```

Expected: FAIL (offset IS created in current code)

**Step 4: Remove `manual_investments` from `sync_prior_wealth_offset`**

In `backend/services/transactions_service.py`:

Change the `services_to_sync` initialization in `sync_prior_wealth_offset`:

```python
# Before:
services_to_sync = (
    [target_service]
    if target_service
    else [Services.CASH.value, Services.MANUAL_INVESTMENTS.value]
)

# After:
services_to_sync = (
    [target_service]
    if target_service
    else [Services.CASH.value]
)
```

Also guard the `elif service == Services.MANUAL_INVESTMENTS.value` branch — change it to raise `ValueError` for any non-cash service:

```python
# In the loop body, change:
if service == Services.CASH.value:
    repo = self.transactions_repository.cash_repo
elif service == Services.MANUAL_INVESTMENTS.value:
    repo = self.transactions_repository.manual_investments_repo
else:
    raise ValueError(...)

# To:
if service == Services.CASH.value:
    repo = self.transactions_repository.cash_repo
else:
    raise ValueError(
        f"Service '{service}' not supported for prior wealth offset"
    )
```

Update the method docstring and signature to remove references to `manual_investments`:

```python
def sync_prior_wealth_offset(
    self, target_service: Literal["cash"] | None = None
) -> None:
    """
    Synchronize the prior wealth offset transaction for cash transactions.

    Tracks cash deposits (negative amounts) and maintains a single
    consolidated "Prior Wealth" transaction in the cash table.
    Investment prior wealth is handled separately via Investment.prior_wealth_amount.
    """
```

**Step 5: Run the new test**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_sync_prior_wealth_skips_manual_investments -v
```

Expected: PASS

### 4d: Wire `recalculate_prior_wealth` into `create_transaction` and `delete_transaction`

**Step 1: Write failing tests**

Add to `TestTransactionsServicePriorWealth` in `test_transactions_service.py`:

```python
def test_create_manual_investments_transaction_updates_prior_wealth(
    self, db_session, seed_investments
):
    """Verify creating a manual_investments transaction recalculates Investment.prior_wealth_amount."""
    service = TransactionsService(db_session)
    stock_fund = seed_investments["investments"][0]
    # Existing txns: -10000, -2000 → current prior_wealth = 0 (not set yet in fixture)

    data = {
        "date": date(2024, 3, 1),
        "description": "Extra deposit",
        "amount": -3000.0,
        "account_name": "Investment Account",
        "category": "Investments",
        "tag": "Stock Fund",
    }
    service.create_transaction(data, "manual_investments")

    db_session.refresh(stock_fund)
    # Txns: -10000 + -2000 + -3000 = -15000 → prior_wealth = 15000
    assert stock_fund.prior_wealth_amount == pytest.approx(15000.0)

def test_delete_manual_investments_transaction_updates_prior_wealth(
    self, db_session, seed_investments
):
    """Verify deleting a manual_investments transaction recalculates Investment.prior_wealth_amount."""
    service = TransactionsService(db_session)
    stock_fund = seed_investments["investments"][0]
    txns = seed_investments["transactions"]
    # inv_txn_2 is a Stock Fund txn with amount=-2000
    inv_txn_2 = next(t for t in txns if t.id == "inv_txn_2")

    service.delete_transaction(inv_txn_2.unique_id, "manual_investment_transactions")

    db_session.refresh(stock_fund)
    # After deleting -2000, remaining: -10000 → prior_wealth = 10000
    assert stock_fund.prior_wealth_amount == pytest.approx(10000.0)
```

**Step 2: Run to verify failure**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_create_manual_investments_transaction_updates_prior_wealth tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_delete_manual_investments_transaction_updates_prior_wealth -v
```

Expected: FAIL

**Step 3: Update `create_transaction` to trigger recalculation**

In `backend/services/transactions_service.py`, replace the end of `create_transaction`:

```python
# Before:
self.sync_prior_wealth_offset()

# After:
if service == "cash":
    self.sync_prior_wealth_offset(target_service="cash")
elif service == "manual_investments":
    category = data.get("category")
    tag = data.get("tag")
    if category and tag:
        from backend.services.investments_service import InvestmentsService
        InvestmentsService(self.db).recalculate_prior_wealth_by_tag(category, tag)
```

**Step 4: Add `recalculate_prior_wealth_by_tag` to `InvestmentsService`**

In `backend/services/investments_service.py`, add after `recalculate_prior_wealth`:

```python
def recalculate_prior_wealth_by_tag(self, category: str, tag: str) -> None:
    """
    Look up investment by category and tag, then recalculate prior_wealth_amount.

    Parameters
    ----------
    category : str
        Investment category (e.g. "Investments").
    tag : str
        Investment tag identifying the specific investment.
    """
    inv_df = self.investments_repo.get_by_category_tag(category, tag)
    if inv_df.empty:
        return
    self.recalculate_prior_wealth(int(inv_df.iloc[0]["id"]))
```

**Step 5: Update `delete_transaction` to trigger recalculation**

In `backend/services/transactions_service.py`, in `delete_transaction`, capture category/tag BEFORE deleting, then replace `self.sync_prior_wealth_offset()`:

```python
# Before `success = target_repo.delete_transaction_by_unique_id(unique_id)`, add:
inv_category = None
inv_tag = None
if source == "manual_investment_transactions":
    inv_category = getattr(tx_record, "category", None)
    inv_tag = getattr(tx_record, "tag", None)

# Replace the final sync call:
# Before:
self.sync_prior_wealth_offset()

# After:
if source == "cash_transactions":
    self.sync_prior_wealth_offset(target_service="cash")
elif source == "manual_investment_transactions" and inv_category and inv_tag:
    from backend.services.investments_service import InvestmentsService
    InvestmentsService(self.db).recalculate_prior_wealth_by_tag(inv_category, inv_tag)
```

**Step 6: Run the failing tests**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_create_manual_investments_transaction_updates_prior_wealth tests/backend/unit/services/test_transactions_service.py::TestTransactionsServicePriorWealth::test_delete_manual_investments_transaction_updates_prior_wealth -v
```

Expected: PASS

**Step 7: Run all transaction service tests**

```bash
poetry run pytest tests/backend/unit/services/test_transactions_service.py -v
```

Expected: All PASS (update any tests that assumed `manual_investments` prior wealth offset still being created)

**Step 8: Commit**

```bash
git add backend/services/transactions_service.py backend/services/investments_service.py tests/backend/unit/services/test_transactions_service.py tests/backend/unit/services/test_investments_service.py
git commit -m "feat: wire investment prior wealth recalculation into TransactionsService"
```

---

## Task 5: Update `AnalysisService` to add `_get_investment_prior_wealth_total()`

**Files:**
- Modify: `backend/services/analysis_service.py`
- Test: `tests/backend/unit/services/test_analysis_service.py` (if it exists, otherwise check integration tests)

**Step 1: Write the failing test**

Find or create `tests/backend/unit/services/test_analysis_service.py`. Add:

```python
"""Tests for AnalysisService."""

import pytest
from backend.services.analysis_service import AnalysisService


class TestAnalysisServiceInvestmentPriorWealth:
    """Tests for investment prior wealth aggregation in AnalysisService."""

    def test_get_investment_prior_wealth_total_sums_open_investments(
        self, db_session, seed_investments
    ):
        """Verify _get_investment_prior_wealth_total sums prior_wealth_amount for open investments."""
        stock_fund, bond_fund = seed_investments["investments"]
        stock_fund.prior_wealth_amount = 12000.0
        bond_fund.prior_wealth_amount = -160.0   # closed, should be excluded
        db_session.commit()

        service = AnalysisService(db_session)
        total = service._get_investment_prior_wealth_total()

        assert total == pytest.approx(12000.0)

    def test_get_investment_prior_wealth_total_returns_zero_with_no_investments(
        self, db_session
    ):
        """Verify _get_investment_prior_wealth_total returns 0.0 when no investments exist."""
        service = AnalysisService(db_session)
        assert service._get_investment_prior_wealth_total() == 0.0
```

**Step 2: Run to verify failure**

```bash
poetry run pytest tests/backend/unit/services/test_analysis_service.py -v
```

Expected: FAIL

**Step 3: Implement `_get_investment_prior_wealth_total()`**

In `backend/services/analysis_service.py`, add the import at the top:

```python
from backend.repositories.investments_repository import InvestmentsRepository
```

In `__init__`, add after `self.investments_service = InvestmentsService(db)`:

```python
self.investments_repo = InvestmentsRepository(db)
```

Add the method after `_get_bank_prior_wealth_total`:

```python
def _get_investment_prior_wealth_total(self) -> float:
    """Get total prior wealth from all open investments."""
    df = self.investments_repo.get_all_investments(include_closed=False)
    if df.empty:
        return 0.0
    return float(df["prior_wealth_amount"].sum())
```

**Step 4: Run tests**

```bash
poetry run pytest tests/backend/unit/services/test_analysis_service.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/services/analysis_service.py tests/backend/unit/services/test_analysis_service.py
git commit -m "feat: add _get_investment_prior_wealth_total to AnalysisService"
```

---

## Task 6: Startup migration — seed `prior_wealth_amount` and clean up old offset transactions

**Files:**
- Modify: `backend/main.py`

**Step 1: Add the migration block to `lifespan`**

In `backend/main.py`, inside the `lifespan` function, add a new `with get_db_context() as db:` block after the existing seeding block:

```python
# Migrate: seed Investment.prior_wealth_amount from transactions
# and clean up legacy manual_investments prior wealth offset transactions
with get_db_context() as db:
    from sqlalchemy import text
    from backend.repositories.investments_repository import InvestmentsRepository
    from backend.repositories.transactions_repository import TransactionsRepository
    from backend.constants.categories import PRIOR_WEALTH_TAG, IncomeCategories
    from backend.constants.tables import TransactionsTableFields

    engine = get_engine()

    # 1. Add the column if not present (SQLite doesn't auto-add columns for existing tables)
    with engine.connect() as conn:
        cols = [
            row[1]
            for row in conn.execute(text("PRAGMA table_info(investments)")).fetchall()
        ]
        if "prior_wealth_amount" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE investments ADD COLUMN prior_wealth_amount REAL NOT NULL DEFAULT 0.0"
                )
            )
            conn.commit()

    investments_repo = InvestmentsRepository(db)
    txns_repo = TransactionsRepository(db)

    # 2. Seed prior_wealth_amount for every investment from its transactions
    investments_df = investments_repo.get_all_investments(include_closed=True)
    if not investments_df.empty:
        txns_df = txns_repo.get_table("manual_investments")
        for _, inv in investments_df.iterrows():
            if not txns_df.empty:
                mask = (txns_df["category"] == inv["category"]) & (
                    txns_df["tag"] == inv["tag"]
                )
                inv_txns = txns_df[mask]
                prior_wealth = (
                    -float(inv_txns["amount"].sum())
                    if not inv_txns.empty
                    else 0.0
                )
            else:
                prior_wealth = 0.0
            investments_repo.update_prior_wealth(int(inv["id"]), prior_wealth)

    # 3. Remove legacy manual_investments prior wealth offset transactions
    manual_inv_repo = txns_repo.manual_investments_repo
    inv_all_df = manual_inv_repo.get_table()
    if not inv_all_df.empty:
        tag_col = TransactionsTableFields.TAG.value
        cat_col = TransactionsTableFields.CATEGORY.value
        acct_col = TransactionsTableFields.ACCOUNT_NAME.value
        uid_col = TransactionsTableFields.UNIQUE_ID.value

        pw_mask = (
            (inv_all_df[tag_col] == PRIOR_WEALTH_TAG)
            & (inv_all_df[cat_col] == IncomeCategories.OTHER_INCOME.value)
            & (inv_all_df[acct_col] == PRIOR_WEALTH_TAG)
        )
        for _, row in inv_all_df[pw_mask].iterrows():
            manual_inv_repo.delete_transaction_by_unique_id(str(row[uid_col]))
```

**Step 2: Start the server and verify migration runs without error**

```bash
poetry run uvicorn backend.main:app --reload
```

Expected: Server starts cleanly, no errors in console. If you have an existing DB, check that `prior_wealth_amount` is populated.

**Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add startup migration to seed Investment.prior_wealth_amount"
```

---

## Task 7: Update `seed_investments` fixture to include `prior_wealth_amount`

**Files:**
- Modify: `tests/backend/conftest.py`

**Step 1: Update the fixture**

In `tests/backend/conftest.py`, in `seed_investments`, add `prior_wealth_amount` to both `Investment` instantiations:

```python
stock_fund = Investment(
    category="Investments",
    tag="Stock Fund",
    type="mutual_fund",
    name="Migdal S&P 500 Fund",
    interest_rate=7.5,
    interest_rate_type="variable",
    created_date="2023-06-15",
    is_closed=0,
    prior_wealth_amount=12000.0,  # -((-10000) + (-2000))
)
bond_fund = Investment(
    category="Investments",
    tag="Bond Fund",
    type="bond",
    name="Psagot Government Bond",
    interest_rate=3.2,
    interest_rate_type="fixed",
    created_date="2023-01-10",
    is_closed=1,
    closed_date="2024-01-10",
    maturity_date="2024-01-10",
    prior_wealth_amount=-160.0,  # -((-5000) + 5160)
)
```

**Step 2: Update `seed_prior_wealth_transactions` to remove the manual_inv_pw transaction**

The `manual_inv_pw` transaction in `seed_prior_wealth_transactions` was the old portfolio-level offset. Remove it:

```python
# Remove these lines:
manual_inv_pw = ManualInvestmentTransaction(
    id="inv_pw_1",
    ...
)
# And remove manual_inv_pw from db_session.add_all([...])
# And remove it from the return dict
```

The fixture's return value becomes:
```python
return {
    "cash": cash_pw,
    "bank_balances": [bank_balance_1, bank_balance_2],
}
```

**Step 3: Run all tests to see what breaks**

```bash
poetry run pytest tests/ -v 2>&1 | head -80
```

Fix any failing tests that referenced `seed_prior_wealth_transactions["manual_investment"]`.

**Step 4: Commit**

```bash
git add tests/backend/conftest.py
git commit -m "test: update seed_investments and seed_prior_wealth_transactions fixtures for prior wealth refactor"
```

---

## Task 8: Run full test suite and fix regressions

**Step 1: Run all tests**

```bash
poetry run pytest tests/ -v
```

**Step 2: Fix any remaining failures**

Common failures to expect:
- Tests that checked `sync_prior_wealth_offset` created a `manual_investments` offset — update to verify no offset created
- Tests that expected `seed_prior_wealth_transactions["manual_investment"]` key — update to use synthetic rows
- Route tests for `POST /api/transactions/` with `manual_investments` — verify `Investment.prior_wealth_amount` is updated instead of a prior wealth transaction being created

**Step 3: Run with coverage**

```bash
poetry run pytest tests/ --cov=backend --cov-report=term-missing
```

**Step 4: Commit fixes**

```bash
git add -p  # stage selectively
git commit -m "test: fix test regressions after investment prior wealth refactor"
```

---

## Task 9: Final verification

**Step 1: Start both servers**

```bash
python .claude/scripts/with_server.py -- echo "Servers started"
```

**Step 2: Verify the API responses**

Check analytics endpoints still return valid data:
- `GET /api/analytics/net-worth-over-time` — should include investment value
- `GET /api/analytics/sankey` — should show investment prior wealth in Prior Wealth source

**Step 3: Run full test suite one final time**

```bash
poetry run pytest tests/ -v
```

Expected: All PASS

**Step 4: Final commit**

```bash
git add .
git commit -m "chore: investment prior wealth refactor complete"
```

---

## Summary of Changes

| File | What changed |
|------|-------------|
| `backend/models/investment.py` | +`prior_wealth_amount` column |
| `backend/repositories/investments_repository.py` | +`update_prior_wealth()` |
| `backend/services/investments_service.py` | +`recalculate_prior_wealth()`, +`recalculate_prior_wealth_by_tag()`, +`get_total_prior_wealth()` |
| `backend/services/transactions_service.py` | +`InvestmentsRepository`; +`_build_investment_prior_wealth_rows()`; call in `get_data_for_analysis()`; remove `manual_investments` from `sync_prior_wealth_offset`; lazy-import trigger in `create_transaction` / `delete_transaction` |
| `backend/services/analysis_service.py` | +`InvestmentsRepository`; +`_get_investment_prior_wealth_total()` |
| `backend/main.py` | Startup migration: ALTER TABLE + seed + cleanup |
| `tests/backend/conftest.py` | `seed_investments` adds `prior_wealth_amount`; `seed_prior_wealth_transactions` drops `manual_inv_pw` |
| `tests/backend/unit/repositories/test_investments_repository.py` | New — `update_prior_wealth` tests |
| `tests/backend/unit/services/test_investments_service.py` | New class — `TestInvestmentsServicePriorWealth` |
| `tests/backend/unit/services/test_transactions_service.py` | Updated prior wealth tests; new investment trigger tests |
| `tests/backend/unit/services/test_analysis_service.py` | New — `_get_investment_prior_wealth_total` tests |
