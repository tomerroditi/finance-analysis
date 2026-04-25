# Auto-create Investments from Scraped Keren Hishtalmut — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically create and maintain Investment records + balance snapshots when Keren Hishtalmut data is scraped from insurance providers.

**Architecture:** Extend `InsuranceScraperAdapter._post_save_hook()` to call a new `InvestmentsService.sync_from_insurance()` method for hishtalmut policies. Link investments to insurance accounts via a new `insurance_policy_id` column on the `investments` table.

**Tech Stack:** Python, SQLAlchemy ORM, Alembic, pytest

---

## Chunk 1: Model + Migration + Repository

### Task 1: Add `insurance_policy_id` column to Investment model

**Files:**
- Modify: `backend/models/investment.py`
- Modify: `backend/constants/tables.py:119-145` (InvestmentsTableFields enum)

- [ ] **Step 1: Add column to Investment model**

In `backend/models/investment.py`, add after `prior_wealth_amount`:

```python
insurance_policy_id = Column(String, nullable=True, unique=True)
```

- [ ] **Step 2: Add field to InvestmentsTableFields enum**

In `backend/constants/tables.py`, add to the `InvestmentsTableFields` enum:

```python
INSURANCE_POLICY_ID = "insurance_policy_id"
```

- [ ] **Step 3: Commit**

```bash
git add backend/models/investment.py backend/constants/tables.py
git commit -m "feat: add insurance_policy_id column to Investment model"
```

### Task 2: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/<auto>_add_insurance_policy_id_to_investments.py`

- [ ] **Step 1: Generate migration**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/charming-brahmagupta
source .venv/bin/activate
alembic -c backend/alembic.ini revision --autogenerate -m "add insurance_policy_id to investments"
```

- [ ] **Step 2: Verify migration contents**

Open the generated file and confirm it contains:
- `op.add_column('investments', sa.Column('insurance_policy_id', sa.String(), nullable=True))`
- `op.create_unique_constraint(...)` for the column
- Corresponding `downgrade()` that drops the column

If autogenerate didn't pick it up (common with SQLite), manually write:

```python
def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('investments')]
    if 'insurance_policy_id' not in columns:
        op.add_column('investments', sa.Column('insurance_policy_id', sa.String(), nullable=True, unique=True))

def downgrade() -> None:
    op.drop_column('investments', 'insurance_policy_id')
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: add migration for insurance_policy_id column"
```

### Task 3: Add `get_by_insurance_policy_id` to InvestmentsRepository

**Files:**
- Modify: `backend/repositories/investments_repository.py`
- Test: `tests/backend/unit/repositories/test_investments_repository.py`

- [ ] **Step 1: Write failing test**

Add to `tests/backend/unit/repositories/test_investments_repository.py`:

```python
class TestGetByInsurancePolicyId:
    """Tests for looking up investments by insurance_policy_id."""

    def test_returns_matching_investment(self, db_session):
        """Verify lookup by insurance_policy_id returns the linked investment."""
        from backend.models.investment import Investment

        inv = Investment(
            category="Investments",
            tag="Keren Hishtalmut - hafenix",
            type="hishtalmut",
            name="Test Hishtalmut",
            interest_rate_type="variable",
            created_date="2025-01-01",
            is_closed=0,
            prior_wealth_amount=0.0,
            insurance_policy_id="POL-123",
        )
        db_session.add(inv)
        db_session.flush()

        repo = InvestmentsRepository(db_session)
        result = repo.get_by_insurance_policy_id("POL-123")
        assert not result.empty
        assert result.iloc[0]["name"] == "Test Hishtalmut"

    def test_returns_empty_when_not_found(self, db_session):
        """Verify lookup returns empty DataFrame when no match exists."""
        repo = InvestmentsRepository(db_session)
        result = repo.get_by_insurance_policy_id("NONEXISTENT")
        assert result.empty
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/backend/unit/repositories/test_investments_repository.py::TestGetByInsurancePolicyId -v
```

Expected: FAIL — `AttributeError: 'InvestmentsRepository' object has no attribute 'get_by_insurance_policy_id'`

- [ ] **Step 3: Implement the method**

Add to `backend/repositories/investments_repository.py` after `get_by_category_tag`:

```python
def get_by_insurance_policy_id(self, policy_id: str) -> pd.DataFrame:
    """Find an investment linked to an insurance policy.

    Parameters
    ----------
    policy_id : str
        The insurance policy ID to look up.

    Returns
    -------
    pd.DataFrame
        Matching investment row, or empty DataFrame if not found.
    """
    stmt = select(Investment).where(
        Investment.insurance_policy_id == policy_id
    )
    return pd.read_sql(stmt, self.db.bind)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
poetry run pytest tests/backend/unit/repositories/test_investments_repository.py::TestGetByInsurancePolicyId -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/repositories/investments_repository.py tests/backend/unit/repositories/test_investments_repository.py
git commit -m "feat: add get_by_insurance_policy_id to InvestmentsRepository"
```

## Chunk 2: Service Method + Adapter Integration

### Task 4: Add `sync_from_insurance` to InvestmentsService

**Files:**
- Modify: `backend/services/investments_service.py`
- Test: `tests/backend/unit/services/test_investments_service.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/backend/unit/services/test_investments_service.py`:

```python
class TestSyncFromInsurance:
    """Tests for syncing investments from scraped insurance data."""

    def _make_hishtalmut_meta(self, **overrides):
        """Build a minimal hishtalmut insurance metadata dict."""
        meta = {
            "policy_id": "POL-HST-001",
            "policy_type": "hishtalmut",
            "provider": "hafenix",
            "account_name": "קרן השתלמות כלשהי",
            "balance": 150000.0,
            "balance_date": "2025-06-15",
            "commission_deposits_pct": 1.0,
            "commission_savings_pct": 0.5,
            "liquidity_date": "2029-05-31",
        }
        meta.update(overrides)
        return meta

    def test_creates_investment_on_first_sync(self, db_session):
        """Verify first sync creates a new Investment record with correct fields."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        inv = investments[0]
        assert inv["insurance_policy_id"] == "POL-HST-001"
        assert inv["type"] == "hishtalmut"
        assert inv["category"] == "Investments"
        assert inv["tag"] == "Keren Hishtalmut - hafenix"
        assert inv["name"] == "קרן השתלמות כלשהי"
        assert inv["commission_deposit"] == 1.0
        assert inv["commission_management"] == 0.5
        assert inv["liquidity_date"] == "2029-05-31"
        assert inv["interest_rate_type"] == "variable"

    def test_creates_balance_snapshot_on_first_sync(self, db_session):
        """Verify first sync creates a scraped balance snapshot."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        snapshots = service.get_balance_snapshots(investments[0]["id"])
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 150000.0
        assert snapshots[0]["date"] == "2025-06-15"
        assert snapshots[0]["source"] == "scraped"

    def test_updates_existing_investment_on_resync(self, db_session):
        """Verify subsequent sync updates metadata without creating duplicates."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        updated_meta = self._make_hishtalmut_meta(
            account_name="קרן השתלמות מעודכנת",
            commission_deposits_pct=0.8,
            commission_savings_pct=0.4,
            liquidity_date="2030-01-01",
            balance=160000.0,
            balance_date="2025-07-15",
        )
        service.sync_from_insurance(updated_meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        inv = investments[0]
        assert inv["name"] == "קרן השתלמות מעודכנת"
        assert inv["commission_deposit"] == 0.8
        assert inv["commission_management"] == 0.4
        assert inv["liquidity_date"] == "2030-01-01"

    def test_skips_pension_policies(self, db_session):
        """Verify pension policies are ignored by sync."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta(policy_type="pension")

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 0

    def test_does_not_overwrite_manual_snapshot(self, db_session):
        """Verify scraped snapshot skips dates with existing manual snapshots."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        inv_id = service.get_all_investments()[0]["id"]
        # Overwrite the scraped snapshot with a manual one on the same date
        service.create_balance_snapshot(inv_id, "2025-06-15", 999999.0, source="manual")

        # Re-sync with different balance on same date
        meta["balance"] = 160000.0
        service.sync_from_insurance(meta)

        snapshots = service.get_balance_snapshots(inv_id)
        snapshot_on_date = [s for s in snapshots if s["date"] == "2025-06-15"]
        assert len(snapshot_on_date) == 1
        assert snapshot_on_date[0]["balance"] == 999999.0
        assert snapshot_on_date[0]["source"] == "manual"

    def test_updates_existing_scraped_snapshot_on_same_date(self, db_session):
        """Verify re-scraping the same date updates the scraped snapshot balance."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta()
        service.sync_from_insurance(meta)

        meta["balance"] = 155000.0
        service.sync_from_insurance(meta)

        inv_id = service.get_all_investments()[0]["id"]
        snapshots = service.get_balance_snapshots(inv_id)
        assert len(snapshots) == 1
        assert snapshots[0]["balance"] == 155000.0

    def test_skips_snapshot_when_no_balance(self, db_session):
        """Verify no snapshot is created when balance data is missing."""
        service = InvestmentsService(db_session)
        meta = self._make_hishtalmut_meta(balance=None, balance_date=None)

        service.sync_from_insurance(meta)

        investments = service.get_all_investments()
        assert len(investments) == 1
        snapshots = service.get_balance_snapshots(investments[0]["id"])
        assert len(snapshots) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py::TestSyncFromInsurance -v
```

Expected: FAIL — `AttributeError: 'InvestmentsService' object has no attribute 'sync_from_insurance'`

- [ ] **Step 3: Implement `sync_from_insurance`**

Add to `backend/services/investments_service.py`:

```python
def sync_from_insurance(self, insurance_meta: dict) -> None:
    """Create or update an Investment from scraped insurance account metadata.

    Only processes hishtalmut policies. Creates the Investment if not found
    by ``insurance_policy_id``, otherwise updates metadata fields. Upserts
    a ``"scraped"`` balance snapshot if balance data is present, without
    overwriting existing ``"manual"`` snapshots.

    Parameters
    ----------
    insurance_meta : dict
        Insurance account metadata with keys: ``policy_id``, ``policy_type``,
        ``provider``, ``account_name``, ``balance``, ``balance_date``,
        ``commission_deposits_pct``, ``commission_savings_pct``,
        ``liquidity_date``.
    """
    if insurance_meta.get("policy_type") != "hishtalmut":
        return

    from backend.constants.categories import INVESTMENTS_CATEGORY

    policy_id = insurance_meta["policy_id"]
    provider = insurance_meta.get("provider", "unknown")
    tag = f"Keren Hishtalmut - {provider}"

    existing = self.investments_repo.get_by_insurance_policy_id(policy_id)

    if existing.empty:
        self.investments_repo.create_investment(
            category=INVESTMENTS_CATEGORY,
            tag=tag,
            type_="hishtalmut",
            name=insurance_meta["account_name"],
            interest_rate_type="variable",
            commission_deposit=insurance_meta.get("commission_deposits_pct"),
            commission_management=insurance_meta.get("commission_savings_pct"),
            liquidity_date=insurance_meta.get("liquidity_date"),
        )
        # Set insurance_policy_id on the newly created record
        created = self.investments_repo.get_by_category_tag(INVESTMENTS_CATEGORY, tag)
        if not created.empty:
            inv_id = int(created.iloc[0]["id"])
            self.investments_repo.update_investment(
                inv_id, insurance_policy_id=policy_id
            )
    else:
        inv_id = int(existing.iloc[0]["id"])
        self.investments_repo.update_investment(
            inv_id,
            name=insurance_meta["account_name"],
            commission_deposit=insurance_meta.get("commission_deposits_pct"),
            commission_management=insurance_meta.get("commission_savings_pct"),
            liquidity_date=insurance_meta.get("liquidity_date"),
        )

    # Upsert balance snapshot if balance data is present
    balance = insurance_meta.get("balance")
    balance_date = insurance_meta.get("balance_date")
    if balance is not None and balance_date is not None:
        inv_df = self.investments_repo.get_by_insurance_policy_id(policy_id)
        inv_id = int(inv_df.iloc[0]["id"])

        # Check for existing manual snapshot on this date — don't overwrite
        existing_snapshot = self.snapshots_repo.get_snapshots_for_investment(inv_id)
        if not existing_snapshot.empty:
            date_match = existing_snapshot[existing_snapshot["date"] == balance_date]
            if not date_match.empty and date_match.iloc[0]["source"] == "manual":
                return

        self.snapshots_repo.upsert_snapshot(inv_id, balance_date, balance, source="scraped")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py::TestSyncFromInsurance -v
```

Expected: All 7 tests PASS

- [ ] **Step 5: Run full investments test suite for regressions**

```bash
poetry run pytest tests/backend/unit/services/test_investments_service.py -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/investments_service.py tests/backend/unit/services/test_investments_service.py
git commit -m "feat: add sync_from_insurance to InvestmentsService"
```

### Task 5: Integrate into InsuranceScraperAdapter._post_save_hook

**Files:**
- Modify: `backend/scraper/adapter.py:415-443`

- [ ] **Step 1: Extend `_post_save_hook`**

In `backend/scraper/adapter.py`, modify `InsuranceScraperAdapter._post_save_hook()` — after the existing metadata upsert loop and commit, add investment sync:

```python
def _post_save_hook(self, result) -> None:
    """Persist insurance account metadata and sync hishtalmut investments."""
    from backend.models.insurance_account import InsuranceAccount

    accounts_to_upsert = [
        account.metadata
        for account in result.accounts
        if account.metadata
    ]
    if not accounts_to_upsert:
        return

    with get_db_context() as db:
        for meta in accounts_to_upsert:
            existing = db.query(InsuranceAccount).filter_by(
                policy_id=meta["policy_id"]
            ).first()
            if existing:
                for key, value in meta.items():
                    if key != "policy_id":
                        setattr(existing, key, value)
            else:
                db.add(InsuranceAccount(**meta))
        db.commit()
        logger.info(
            "%s: %s: Saved metadata for %d insurance accounts",
            self.provider_name, self.account_name, len(accounts_to_upsert),
        )

        # Sync hishtalmut policies to investments
        from backend.services.investments_service import InvestmentsService

        inv_service = InvestmentsService(db)
        for meta in accounts_to_upsert:
            if meta.get("policy_type") == "hishtalmut":
                try:
                    inv_service.sync_from_insurance(meta)
                    logger.info(
                        "%s: %s: Synced hishtalmut investment for policy %s",
                        self.provider_name, self.account_name, meta["policy_id"],
                    )
                except Exception:
                    logger.exception(
                        "%s: %s: Failed to sync hishtalmut investment for policy %s",
                        self.provider_name, self.account_name, meta["policy_id"],
                    )
```

- [ ] **Step 2: Run full test suite to check for regressions**

```bash
poetry run pytest tests/backend/ -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/scraper/adapter.py
git commit -m "feat: sync hishtalmut investments from insurance scraper post-save hook"
```

### Task 6: Final verification

- [ ] **Step 1: Run full test suite**

```bash
poetry run pytest
```

Expected: All tests PASS

- [ ] **Step 2: Run frontend build to verify no type issues**

```bash
cd /Users/tomer/Desktop/finance-analysis/.claude/worktrees/charming-brahmagupta/frontend && npm run build
```

Expected: Build succeeds (no frontend changes, but verify nothing broke)
