# Demo Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace "Test Mode" with "Demo Mode" that loads a rich pre-built dataset showcasing every app feature, with dynamically shifted dates so charts always look current.

**Architecture:** Pre-built SQLite DB (`backend/resources/demo_data.db`) + date-shift on activation. Rename all test mode references to demo mode across backend (AppConfig, routes, services) and frontend (context, header, API). A seed script generates the DB with ~1,200 transactions over 14 months for a fictional Israeli family.

**Tech Stack:** Python 3.12, SQLAlchemy ORM, SQLite, FastAPI, React 19, TypeScript, Tailwind CSS 4

---

### Task 1: Rename AppConfig — test mode → demo mode

**Files:**
- Modify: `backend/config.py` (entire file)

**Step 1: Rename all test mode references in AppConfig**

Replace the entire content of `backend/config.py`:

```python
"""
Centralized configuration management for the Finance Analysis backend.
Handles environment switching between production and demo modes.
"""

import os


class AppConfig:
    """Singleton configuration manager for the Finance Analysis backend.

    Provides a single shared instance (via ``__new__``) that controls whether
    the application runs in production or demo mode. In demo mode all paths
    point to an isolated ``demo_env/`` subdirectory so demos never touch
    production data. Paths can also be overridden via environment variables
    (``FAD_USER_DIR``, ``FAD_DB_PATH``, ``FAD_CREDENTIALS_PATH``, etc.).
    """

    _instance = None
    _demo_mode = False

    # Base user directory
    _base_user_dir = os.environ.get(
        "FAD_USER_DIR", os.path.join(os.path.expanduser("~"), ".finance-analysis")
    )

    def __new__(cls):
        """Return the shared singleton instance, creating it on first call."""
        if cls._instance is None:
            cls._instance = super(AppConfig, cls).__new__(cls)
        return cls._instance

    @property
    def is_demo_mode(self) -> bool:
        """Return ``True`` when the application is running in demo mode."""
        return self._demo_mode

    def set_demo_mode(self, enabled: bool):
        """Enable or disable demo mode.

        When enabling, the demo user directory is created if it does not exist.

        Parameters
        ----------
        enabled : bool
            ``True`` to switch to the isolated demo environment,
            ``False`` to switch back to production.
        """
        self._demo_mode = enabled
        # Ensure demo directory exists if entering demo mode
        if enabled:
            os.makedirs(self.get_user_dir(), exist_ok=True)

    def get_user_dir(self) -> str:
        """Get the current user directory based on mode."""
        if self._demo_mode:
            return os.path.join(self._base_user_dir, "demo_env")
        return self._base_user_dir

    def get_db_path(self) -> str:
        """Get the current database path."""
        # Allow override via env var in non-demo mode only
        if not self._demo_mode and os.environ.get("FAD_DB_PATH"):
            return os.environ.get("FAD_DB_PATH")

        filename = "demo_data.db" if self._demo_mode else "data.db"
        return os.path.join(self.get_user_dir(), filename)

    def get_credentials_path(self) -> str:
        """Get the current credentials file path."""
        if not self._demo_mode and os.environ.get("FAD_CREDENTIALS_PATH"):
            return os.environ.get("FAD_CREDENTIALS_PATH")

        return os.path.join(self.get_user_dir(), "credentials.yaml")

    def get_categories_path(self) -> str:
        """Get the current categories file path."""
        if not self._demo_mode and os.environ.get("FAD_CATEGORIES_PATH"):
            return os.environ.get("FAD_CATEGORIES_PATH")

        return os.path.join(self.get_user_dir(), "categories.yaml")

    def get_categories_icons_path(self) -> str:
        """Get the current categories icons file path."""
        if not self._demo_mode and os.environ.get("FAD_CATEGORIES_ICONS_PATH"):
            return os.environ.get("FAD_CATEGORIES_ICONS_PATH")

        return os.path.join(self.get_user_dir(), "categories_icons.yaml")
```

**Step 2: Update all config tests**

Modify `tests/backend/unit/test_config.py` — replace every occurrence of:
- `_test_mode` → `_demo_mode`
- `is_test_mode` → `is_demo_mode`
- `set_test_mode` → `set_demo_mode`
- `"test_env"` → `"demo_env"`
- `"test_data.db"` → `"demo_data.db"`
- Test method names: `test_mode` → `demo_mode` in test names and docstrings

**Step 3: Run config tests**

```bash
poetry run pytest tests/backend/unit/test_config.py -v
```
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add backend/config.py tests/backend/unit/test_config.py
git commit -m "refactor: rename AppConfig test mode to demo mode"
```

---

### Task 2: Rename backend routes and services — test mode → demo mode

**Files:**
- Modify: `backend/routes/testing.py`
- Modify: `backend/services/credentials_service.py`
- Modify: `backend/repositories/credentials_repository.py`

**Step 1: Update testing.py route**

In `backend/routes/testing.py`:
- Rename `TestModeRequest` → `DemoModeRequest` and field stays `enabled`
- Rename endpoint `/toggle_test_mode` → `/toggle_demo_mode`
- Rename function `toggle_test_mode` → `toggle_demo_mode`
- Rename endpoint `/test_mode_status` → `/demo_mode_status`
- Rename function `get_test_mode_status` → `get_demo_mode_status`
- Replace `config.is_test_mode` → `config.is_demo_mode`
- Replace `config.set_test_mode` → `config.set_demo_mode`
- Replace `"test_mode"` response key → `"demo_mode"`
- Replace `seed_test_credentials` → `seed_demo_credentials`
- Update all docstrings: "test mode" → "demo mode", "test environment" → "demo environment"

**Step 2: Update credentials_service.py**

In `backend/services/credentials_service.py`:
- Replace `AppConfig().is_test_mode` → `AppConfig().is_demo_mode` (line 248)
- Rename `seed_test_credentials` → `seed_demo_credentials` (line 269)
- Update docstrings: "test scrapers" → "demo scrapers"

**Step 3: Update credentials_repository.py**

In `backend/repositories/credentials_repository.py`:
- Replace `AppConfig().is_test_mode` → `AppConfig().is_demo_mode` (line 47)
- Update keyring namespace: `"-test"` → `"-demo"` (same line area)

**Step 4: Update credential service tests**

In `tests/backend/unit/services/test_credentials_service.py`:
- Replace `is_test_mode` → `is_demo_mode` in monkeypatch targets (line 138)

**Step 5: Run all backend tests**

```bash
poetry run pytest tests/backend/ -v
```
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add backend/routes/testing.py backend/services/credentials_service.py backend/repositories/credentials_repository.py tests/backend/unit/services/test_credentials_service.py
git commit -m "refactor: rename test mode to demo mode in backend routes and services"
```

---

### Task 3: Add demo data loading to the toggle endpoint

**Files:**
- Modify: `backend/routes/testing.py`

**Step 1: Add demo data copy and date-shift logic**

Add imports at the top of `backend/routes/testing.py`:
```python
import os
import shutil
from datetime import date, timedelta
```

Add a constant for the reference date (will match what the seed script uses):
```python
# Reference date used when generating demo_data.db.
# All dates in the DB are relative to this date.
DEMO_REFERENCE_DATE = date(2026, 2, 25)
```

Add a helper function `_prepare_demo_database` after `_sync_missing_columns`:

```python
def _prepare_demo_database() -> None:
    """Copy the pre-built demo DB and shift all dates to be relative to today.

    Copies ``backend/resources/demo_data.db`` to the demo environment directory
    and runs SQL UPDATE statements to shift every date column by the offset
    between the reference date (when the DB was generated) and today.
    """
    config = AppConfig()
    demo_db_path = config.get_db_path()
    source_db = os.path.join(
        os.path.dirname(__file__), "..", "resources", "demo_data.db"
    )

    # Copy pre-built DB (overwrites any previous demo data)
    if os.path.exists(source_db):
        shutil.copy2(source_db, demo_db_path)

    # Shift dates
    offset_days = (date.today() - DEMO_REFERENCE_DATE).days
    if offset_days == 0:
        return

    engine = database.get_engine()
    with engine.connect() as conn:
        offset_str = f"+{offset_days} days" if offset_days > 0 else f"{offset_days} days"

        # Shift date columns in transaction tables
        for table in [
            "bank_transactions",
            "credit_card_transactions",
            "cash_transactions",
            "manual_investment_transactions",
        ]:
            conn.execute(text(
                f"UPDATE {table} SET date = date(date, :offset)"
            ), {"offset": offset_str})

        # Shift investment balance snapshots
        conn.execute(text(
            "UPDATE investment_balance_snapshots SET date = date(date, :offset)"
        ), {"offset": offset_str})

        # Shift investment date fields
        for col in ["created_date", "closed_date", "liquidity_date", "maturity_date"]:
            conn.execute(text(
                f"UPDATE investments SET {col} = date({col}, :offset) WHERE {col} IS NOT NULL"
            ), {"offset": offset_str})

        # Shift scraping history
        conn.execute(text(
            "UPDATE scraping_history SET date = date(date, :offset)"
        ), {"offset": offset_str})

        # Shift budget rules year/month
        # Calculate month offset and apply
        if offset_days != 0:
            # Get all distinct year/month pairs
            rows = conn.execute(text(
                "SELECT DISTINCT id, year, month FROM budget_rules WHERE year IS NOT NULL"
            )).fetchall()
            for row in rows:
                old_date = date(row[1], row[2], 1)
                new_date = old_date + timedelta(days=offset_days)
                conn.execute(text(
                    "UPDATE budget_rules SET year = :year, month = :month WHERE id = :id"
                ), {"year": new_date.year, "month": new_date.month, "id": row[0]})

        conn.commit()
```

**Step 2: Update the toggle endpoint to call `_prepare_demo_database`**

In the `toggle_demo_mode` function, after `_sync_missing_columns(engine)` and before the credentials seeding, add:

```python
            _prepare_demo_database()
```

The full enabling block becomes:
```python
        if request.enabled:
            engine = database.get_engine()
            Base.metadata.create_all(bind=engine)
            _sync_missing_columns(engine)
            _prepare_demo_database()

            with get_db_context() as demo_db:
                creds_service = CredentialsService(demo_db)
                creds_service.seed_demo_credentials()
```

**Step 3: Run backend tests**

```bash
poetry run pytest tests/backend/ -v
```
Expected: All tests PASS.

**Step 4: Commit**

```bash
git add backend/routes/testing.py
git commit -m "feat: add demo data loading with date shifting on demo mode activation"
```

---

### Task 4: Rename frontend — test mode → demo mode

**Files:**
- Rename: `frontend/src/context/TestModeContext.tsx` → `frontend/src/context/DemoModeContext.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/layout/Header.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/DataSources.tsx`
- Modify: `frontend/src/mocks/handlers.ts`

**Step 1: Create DemoModeContext.tsx (rename + update)**

Create `frontend/src/context/DemoModeContext.tsx` with all references renamed:
- `TestModeContextType` → `DemoModeContextType`
- `isTestMode` → `isDemoMode`
- `toggleTestMode` → `toggleDemoMode`
- `TestModeContext` → `DemoModeContext`
- `TestModeProvider` → `DemoModeProvider`
- `useTestMode` → `useDemoMode`
- `testingApi.getTestModeStatus()` → `testingApi.getDemoModeStatus()`
- `testingApi.toggleTestMode()` → `testingApi.toggleDemoMode()`
- `res.data.test_mode` → `res.data.demo_mode`

Then delete the old `TestModeContext.tsx`.

**Step 2: Update api.ts**

In `frontend/src/services/api.ts` (lines 380-388):
```typescript
export const testingApi = {
  toggleDemoMode: (enabled: boolean) =>
    api.post<{ status: string; demo_mode: boolean }>(
      "/testing/toggle_demo_mode",
      { enabled },
    ),
  getDemoModeStatus: () =>
    api.get<{ demo_mode: boolean }>("/testing/demo_mode_status"),
};
```

**Step 3: Update Header.tsx**

In `frontend/src/components/layout/Header.tsx`:
- `import { useTestMode }` → `import { useDemoMode }` from `"../../context/DemoModeContext"`
- `const { isTestMode, toggleTestMode, isLoading } = useTestMode()` → `const { isDemoMode, toggleDemoMode, isLoading } = useDemoMode()`
- All `isTestMode` → `isDemoMode` in JSX
- `onClick={() => toggleTestMode(!isTestMode)}` → `onClick={() => toggleDemoMode(!isDemoMode)}`
- Label text: `"Test Mode"` → `"Demo Mode"`
- Icon: `FlaskConical` → `Presentation` (from lucide-react) for a more demo-appropriate icon

**Step 4: Update App.tsx**

In `frontend/src/App.tsx`:
- `import { TestModeProvider }` → `import { DemoModeProvider }` from `"./context/DemoModeContext"`
- `<TestModeProvider>` → `<DemoModeProvider>`

**Step 5: Update Dashboard.tsx**

In `frontend/src/pages/Dashboard.tsx`:
- `import { useTestMode }` → `import { useDemoMode }` from `"../context/DemoModeContext"`
- `const { isTestMode } = useTestMode()` → `const { isDemoMode } = useDemoMode()`
- All `isTestMode` in queryKey arrays → `isDemoMode`

**Step 6: Update DataSources.tsx**

In `frontend/src/pages/DataSources.tsx`:
- `import { useTestMode }` → `import { useDemoMode }` from `"../context/DemoModeContext"`
- `const { isTestMode } = useTestMode()` → `const { isDemoMode } = useDemoMode()`
- All `isTestMode` in queryKey arrays → `isDemoMode`

**Step 7: Update mocks/handlers.ts**

In `frontend/src/mocks/handlers.ts`:
- `"/api/testing/test_mode_status"` → `"/api/testing/demo_mode_status"`
- `"/api/testing/toggle_test_mode"` → `"/api/testing/toggle_demo_mode"`
- `{ test_mode: false }` → `{ demo_mode: false }`
- `{ status: "ok", test_mode: true }` → `{ status: "ok", demo_mode: true }`

**Step 8: Build frontend to verify no TypeScript errors**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no errors.

**Step 9: Commit**

```bash
git add -A frontend/src/context/ frontend/src/services/api.ts frontend/src/components/layout/Header.tsx frontend/src/App.tsx frontend/src/pages/Dashboard.tsx frontend/src/pages/DataSources.tsx frontend/src/mocks/handlers.ts
git commit -m "refactor: rename test mode to demo mode in frontend"
```

---

### Task 5: Update CLAUDE.md and rules references

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.claude/rules/testing.md`

**Step 1: Update CLAUDE.md**

In `CLAUDE.md`, find the "UI Testing" section and replace:
```
## UI Testing

When smoke-testing UI changes in the browser, **enable Demo Mode first** (toggle in the top-right header). Demo Mode switches the backend to a separate demo database with pre-built sample data, so real financial data is not accidentally modified. Remember to disable it when done.
```

**Step 2: Update .claude/rules/testing.md**

In `.claude/rules/testing.md`, update the config test reset pattern:
```python
@pytest.fixture(autouse=True)
def reset_config():
    """Reset AppConfig singleton state between tests."""
    AppConfig._demo_mode = False
    AppConfig._base_user_dir = None
    yield
    AppConfig._demo_mode = False
    AppConfig._base_user_dir = None
```

**Step 3: Commit**

```bash
git add CLAUDE.md .claude/rules/testing.md
git commit -m "docs: update CLAUDE.md and testing rules for demo mode rename"
```

---

### Task 6: Create the demo data seed script

**Files:**
- Create: `scripts/generate_demo_data.py`

This is the largest task. The script generates the complete demo SQLite database.

**Step 1: Create the seed script**

Create `scripts/generate_demo_data.py` — a standalone Python script that:

1. Adds project root to `sys.path` so it can import backend models
2. Creates a fresh SQLite DB at `backend/resources/demo_data.db`
3. Uses SQLAlchemy `Base.metadata.create_all()` to create schema
4. Uses a fixed `REFERENCE_DATE = date(2026, 2, 25)` — must match `DEMO_REFERENCE_DATE` in `testing.py`
5. Uses `random.seed(42)` for reproducibility
6. Generates all demo data (details below)

**Data generation structure:**

```python
#!/usr/bin/env python3
"""Generate the pre-built demo database for Demo Mode.

Run: python scripts/generate_demo_data.py
Output: backend/resources/demo_data.db

Uses a fixed reference date (2026-02-25). When demo mode activates,
the backend shifts all dates by the offset from this reference to today.
"""

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models import (
    Base,
    BankTransaction,
    CreditCardTransaction,
    CashTransaction,
    ManualInvestmentTransaction,
    SplitTransaction,
    BankBalance,
    CashBalance,
    Category,
    BudgetRule,
    Investment,
    InvestmentBalanceSnapshot,
    TaggingRule,
    ScrapingHistory,
    PendingRefund,
    RefundLink,
)

REFERENCE_DATE = date(2026, 2, 25)
START_DATE = REFERENCE_DATE - timedelta(days=420)  # ~14 months back
random.seed(42)

DB_PATH = Path(__file__).parent.parent / "backend" / "resources" / "demo_data.db"


def main():
    # Remove old DB if exists
    if DB_PATH.exists():
        DB_PATH.unlink()

    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    create_categories(session)
    create_bank_transactions(session)
    create_credit_card_transactions(session)
    create_cash_transactions(session)
    create_investment_transactions(session)
    create_split_transactions(session)
    create_investments(session)
    create_budget_rules(session)
    create_tagging_rules(session)
    create_bank_balances(session)
    create_cash_balances(session)
    create_pending_refunds(session)
    create_scraping_history(session)

    session.commit()
    session.close()
    engine.dispose()
    print(f"Demo database generated at {DB_PATH}")
```

**Key data generation functions (implement in the script):**

**`create_categories(session)`** — Insert ~15 categories with tags:
- Food: [Groceries, Restaurants, Coffee, Delivery]
- Transportation: [Gas, Parking, Public Transportation, Taxi]
- Household: [Mortgage, Electricity, Water, Internet, Cleaning Supplies, Home Insurance]
- Entertainment: [Streaming, Cinema, Events, Games]
- Health: [Pharmacy, Doctor, Gym, Dental]
- Kids: [Daycare, Activities, Clothing, School Supplies]
- Shopping: [Electronics, Clothing, Online, Gifts]
- Education: [Courses, Books]
- Subscriptions: [Netflix, Spotify, Chat-GPT]
- Vacations: [Flights, Hotel, Food]
- Other: [ATM, Bank Commisions, Haircut]
- Salary: []
- Other Income: [Prior Wealth, Freelance]
- Investments: [Stock Market Fund, Savings Plan, Corporate Bond]
- Liabilities: [Mortgage]
- Credit Cards: []
- Ignore: [Credit Card Bill, Internal Transactions]
- Home Renovation: [Materials, Labor, Furniture] (project category)

Set icons using the same emoji mapping from `categories_icons.yaml`.

**`create_bank_transactions(session)`** — Generate ~4-6 bank transactions per month for 14 months:
- 2 salary deposits per month (18,000 and 12,000, positive, "Salary"/"")
- 1 mortgage payment per month (-3,800, "Liabilities"/"Mortgage")
- 1 CC bill payment per month for Max card (-variable amount matching CC totals, "Credit Cards"/"")
- 1 CC bill payment per month for Visa Cal (-variable amount, "Credit Cards"/"")
- Occasional: freelance income (3-4 times/year, 1,000-2,500 positive, "Other Income"/"Freelance")
- 1 mortgage receipt 14 months ago (450,000 positive, "Liabilities"/"Mortgage")
- Provider: "hapoalim", account_name: "Main Account", source: "bank_transactions"

**`create_credit_card_transactions(session)`** — Generate ~50-70 CC transactions per month:

For Max (Family Card), ~35-45/month:
- Groceries: 8-12x/month, -80 to -350 each ("SHUFERSAL", "RAMI LEVY", "MEGA", "AM:PM")
- Restaurants: 4-6x/month, -60 to -250 ("CAFE CAFE", "AROMA", "MCDONALDS", "PIZZA HUT")
- Gas: 3-4x/month, -150 to -350 ("SONOL", "PAZ", "DELEK")
- Kids daycare: 1x/month, -2,500 to -3,000 ("GAN YELADIM")
- Pharmacy: 1-2x/month, -30 to -150 ("SUPER-PHARM")
- Gym: 1x/month, -250 ("HOLMES PLACE")

For Visa Cal (Online Shopping), ~20-30/month:
- Subscriptions: Netflix -49.90, Spotify -29.90, ChatGPT -75 (monthly)
- Online shopping: 3-5x/month, -50 to -500 ("AMAZON", "ALIEXPRESS", "SHEIN")
- Electronics: 0-1x/month, -200 to -2,000 ("KSP", "BUG")
- Kids clothing: 1-2x/month, -80 to -300 ("NEXT KIDS", "H&M KIDS")

Provider for Max: "max", account_name: "Family Card"
Provider for Visa Cal: "visa cal", account_name: "Online Shopping"
Source: "credit_card_transactions"

**Important:** Ensure sum of CC transactions per month approximately matches CC bill payments in bank. Allow 2-5% variance for realism.

**`create_cash_transactions(session)`** — ~3-5 per month:
- Market purchases: -20 to -60 ("Cash Market Purchase")
- Tips: -10 to -50 ("Tip")
- Source: "cash_transactions", provider: "cash", account_name: "Petty Cash"

**`create_investment_transactions(session)`** — Monthly deposits + 1 withdrawal:
- Stock Fund deposit: -2,000/month (negative = money out), tag: "Stock Market Fund"
- Savings Plan deposit: -1,500/month, tag: "Savings Plan"
- Corporate Bond initial deposit: -50,000 once (~12 months ago), tag: "Corporate Bond"
- Corporate Bond withdrawal: +53,800 (~6 months ago, bond matured), tag: "Corporate Bond"
- Source: "manual_investment_transactions", provider: "manual", account_name: "Investments"
- Category: "Investments" for all

**`create_split_transactions(session)`** — 3 split examples:
1. Find a large grocery transaction (~500 ILS CC), mark as split_parent, create 2 splits: Food/Groceries -350, Household/Cleaning Supplies -150
2. Find a vacation-related CC transaction, split: Vacations/Hotel -800, Entertainment/Events -200
3. Find an online order, split: Shopping/Online -300, Kids/Clothing -200

Update the parent transaction's `type` to `"split_parent"`.

**`create_investments(session)`** — 3 instruments:
1. Stock Market Fund: type="mutual_fund", interest_rate=0.085, interest_rate_type="variable", is_closed=0, created_date=START_DATE+30 days
2. Savings Plan: type="savings", interest_rate=0.042, interest_rate_type="fixed", is_closed=0, created_date=START_DATE+60 days, maturity_date=REFERENCE_DATE+365 days
3. Corporate Bond: type="bond", interest_rate=0.038, interest_rate_type="fixed", is_closed=1, created_date=START_DATE+30 days, closed_date=REFERENCE_DATE-180 days, maturity_date=REFERENCE_DATE-180 days

For Stock Market Fund: create 12-14 monthly `InvestmentBalanceSnapshot` records with source="manual" showing growth from ~2,000 to ~28,000 with some variance (not monotonic — add some dips)

For Savings Plan: create snapshots with source="calculated" using daily compounding formula

For Corporate Bond: snapshots showing growth up to maturity, then a final 0-balance snapshot on the last transaction date

**`create_budget_rules(session)`** — Budget rules for the last 3 months:

For each of the last 3 months (relative to REFERENCE_DATE), create:
- Total Budget: 28,000
- Food: 5,000
- Transportation: 1,800
- Household: 8,000
- Entertainment: 800
- Health: 600
- Kids: 3,500
- Shopping: 2,000

Also create 1 project budget (year=NULL, month=NULL):
- name: "Home Renovation", amount: 30000, category: "Home Renovation", tags: "Materials;Labor;Furniture"

Add ~15 "Home Renovation" transactions spread over the last 6 months in credit_card_transactions:
- Materials: 5-6 purchases, -500 to -3,000 ("ACE HARDWARE", "HOME CENTER")
- Labor: 3-4 payments, -2,000 to -5,000 ("PLUMBER", "ELECTRICIAN", "PAINTER")
- Furniture: 3-4 purchases, -1,000 to -4,000 ("IKEA", "POTTERY BARN")

**`create_tagging_rules(session)`** — 8 rules with JSON conditions:

```python
rules = [
    ("Supermarket", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SHUFERSAL"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "RAMI LEVY"},
    ]}, "Food", "Groceries"),
    ("Rides", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "UBER"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "GETT"},
    ]}, "Transportation", "Taxi"),
    ("Streaming", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "NETFLIX"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SPOTIFY"},
    ]}, "Subscriptions", "Netflix"),
    ("Gas Station", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "PAZ"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SONOL"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "DELEK"},
    ]}, "Transportation", "Gas"),
    ("Pharmacy", {"type": "CONDITION", "field": "description", "operator": "contains", "value": "SUPER-PHARM"}, "Health", "Pharmacy"),
    ("Daycare", {"type": "AND", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "GAN"},
        {"type": "CONDITION", "field": "amount", "operator": "less_than", "value": "-1000"},
    ]}, "Kids", "Daycare"),
    ("Gym", {"type": "CONDITION", "field": "description", "operator": "contains", "value": "HOLMES PLACE"}, "Health", "Gym"),
    ("Online Shopping", {"type": "OR", "subconditions": [
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "AMAZON"},
        {"type": "CONDITION", "field": "description", "operator": "contains", "value": "ALIEXPRESS"},
    ]}, "Shopping", "Online"),
]
```

**`create_bank_balances(session)`** — 1 record:
- provider: "hapoalim", account_name: "Main Account"
- balance: ~85,000 (current realistic bank balance)
- prior_wealth_amount: ~50,000 (wealth before tracking started)
- last_scrape_update: REFERENCE_DATE - 1 day

**`create_cash_balances(session)`** — 1 record:
- account_name: "Petty Cash"
- balance: ~500
- prior_wealth_amount: ~1,000
- last_manual_update: REFERENCE_DATE - 7 days

**`create_pending_refunds(session)`** — 2 records:
1. Pending refund for a CC transaction (e.g., a returned item, ~300 ILS). Status: "pending", notes: "Returned jacket, waiting for refund"
2. Resolved refund for another CC transaction (~150 ILS). Status: "resolved", with a RefundLink pointing to a positive bank transaction (the actual refund). Create the positive refund transaction in bank_transactions too.

**`create_scraping_history(session)`** — 4-6 records:
- Recent successful scrapes for Hapoalim, Max, Visa Cal
- 1 failed scrape (older, error_message: "Timeout waiting for page load")
- Dates spread over last 2 weeks

**Untagged transactions:** Leave 5-8 transactions with `category=None, tag=None`. These should have descriptions that match the tagging rules above (e.g., "SHUFERSAL DEAL RAANANA", "UBER TRIP 1234", "NETFLIX.COM") so the auto-tagging demo works.

**Step 2: Run the seed script**

```bash
python scripts/generate_demo_data.py
```
Expected: "Demo database generated at backend/resources/demo_data.db"

**Step 3: Verify the DB has data**

```bash
python -c "
import sqlite3
conn = sqlite3.connect('backend/resources/demo_data.db')
for table in ['bank_transactions', 'credit_card_transactions', 'cash_transactions', 'manual_investment_transactions', 'categories', 'budget_rules', 'tagging_rules', 'investments', 'investment_balance_snapshots', 'pending_refunds', 'scraping_history', 'bank_balances', 'cash_balances', 'split_transactions']:
    count = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
    print(f'{table}: {count} rows')
conn.close()
"
```

Expected output should show substantial row counts (bank: ~80+, CC: ~800+, investments: 3, snapshots: 20+, etc.)

**Step 4: Commit**

```bash
git add scripts/generate_demo_data.py backend/resources/demo_data.db
git commit -m "feat: add demo data seed script and pre-built demo database"
```

---

### Task 7: Smoke test — toggle demo mode in browser

**Files:** None (testing only)

**Step 1: Start both servers**

```bash
python .claude/scripts/with_server.py -- echo "Servers running"
```

Or manually:
```bash
# Terminal 1
poetry run uvicorn backend.main:app --reload
# Terminal 2
cd frontend && npm run dev
```

**Step 2: Enable demo mode in browser**

1. Open http://localhost:5173
2. Click the "Demo Mode" toggle in the top-right header
3. Verify the toggle turns amber/active

**Step 3: Verify all pages have data**

Check each page:
- **Dashboard:** KPI cards show realistic numbers. Charts render with 14 months of data. Sankey diagram shows cash flow.
- **Transactions:** Table populated with ~1,200 transactions. Filters work. Some untagged transactions visible.
- **Budget:** Monthly budgets show spending vs limits. "Home Renovation" project budget visible.
- **Categories:** All categories with tags and icons displayed.
- **Investments:** 3 investment cards. Stock Fund and Savings Plan open, Corporate Bond closed. Balance charts render.
- **Data Sources:** 4 test scraper accounts shown. Recent scraping history visible.

**Step 4: Verify demo mode disables cleanly**

Click the toggle again to disable demo mode. Verify the app returns to production data (or empty if no production data).

**Step 5: Commit any fixes**

If any issues found, fix and commit:
```bash
git add -A && git commit -m "fix: address demo mode smoke test issues"
```

---

### Task 8: Run full test suite and final verification

**Files:** None (verification only)

**Step 1: Run all backend tests**

```bash
poetry run pytest -v
```
Expected: All tests PASS.

**Step 2: Run frontend build**

```bash
cd frontend && npm run build
```
Expected: Build succeeds.

**Step 3: Run frontend lint**

```bash
cd frontend && npm run lint
```
Expected: No errors.

**Step 4: Final commit if any remaining changes**

```bash
git status
# If any unstaged changes:
git add -A && git commit -m "chore: final demo mode cleanup"
```
