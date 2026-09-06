# Unused Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demote categories with no transactions in the last 6 months into a collapsed "Unused categories" section on the Categories page, so the page stays lean as categories accumulate.

**Architecture:** The backend owns the entire rule. A new `GET /tagging/categories/usage` endpoint returns `{name: {last_used, unused}}` for every category, computed from a pure-SQL cross-table `MAX(date) GROUP BY category` plus `Category.created_at` and `PROTECTED_CATEGORIES`. The frontend splits the existing categories map into two grids by that boolean. Nothing else in the app changes — this is display-only.

**Tech Stack:** FastAPI + SQLAlchemy + pandas (backend), React 19 + TanStack Query + Tailwind CSS 4 + i18next (frontend), pytest / vitest+MSW / Playwright (tests).

**Spec:** `docs/superpowers/specs/2026-09-05-unused-categories-design.md`

## Global Constraints

- A category is unused iff: no transaction dated within the last **6 months**, AND `created_at` older than 6 months, AND not in `PROTECTED_CATEGORIES`. All three must hold.
- `UNUSED_CATEGORY_MONTHS = 6` is the single constant governing both windows. Never hardcode `6` anywhere else.
- Month arithmetic uses `pd.DateOffset` — the project has **no `dateutil` dependency**, so `relativedelta` is unavailable.
- Transaction `date` columns are `YYYY-MM-DD` **strings**. Lexicographic `MAX`/`<` comparison is chronologically correct; do not cast to dates in SQL.
- Usage spans the **merged view**: the four non-insurance tables (`bank_transactions`, `credit_card_transactions`, `cash_transactions`, `manual_investment_transactions`), excluding `type == 'split_parent'` rows, including split children via their parent's date. Insurance is excluded.
- `unique_id` is a per-table auto-increment. Every split join MUST pair `split_transactions.transaction_id` with `split_transactions.source == <that table>`.
- Every user-visible string uses `t("...")` with keys added to **both** `frontend/src/locales/en.json` and `he.json`.
- Tailwind logical properties only (`ps-*`, `pe-*`, `ms-*`, `me-*`, `start-*`, `end-*`, `text-start`) — never physical `left`/`right`.
- No migration: `Category` already inherits `created_at` from `TimestampMixin`.
- No PWA changes: the endpoint is neither sensitive nor real-time, so `frontend/vite.config.ts` and `frontend/src/queryClient.ts` stay untouched.
- Targeted pytest runs need `--no-cov` (the repo has a 40% coverage gate that a small run cannot clear). Use the main checkout's venv from this worktree: `../../../.venv/bin/python -m pytest <path> --no-cov`

---

### Task 1: Backend — last-used date per category

**Files:**
- Modify: `backend/constants/categories.py` (append constant)
- Modify: `backend/repositories/transactions/core.py` (add method after `count_uncategorized`, which ends at line 458)
- Test: `tests/backend/unit/repositories/test_transactions_repository.py` (append a test class)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `backend.constants.categories.UNUSED_CATEGORY_MONTHS: int = 6`
  - `TransactionsRepository.get_category_last_used() -> dict[str, str]` — maps category name to its most recent transaction date as a `"YYYY-MM-DD"` string. Categories with no transactions are **absent** from the dict (not present with `None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/backend/unit/repositories/test_transactions_repository.py`:

```python
class TestGetCategoryLastUsed:
    """Tests for TransactionsRepository.get_category_last_used."""

    def test_empty_db_returns_empty_dict(self, db_session):
        """A database with no transactions yields no last-used entries."""
        repo = TransactionsRepository(db_session)
        assert repo.get_category_last_used() == {}

    def test_max_date_taken_across_tables(self, db_session):
        """The latest date wins even when it lives in a different table."""
        db_session.add(
            BankTransaction(
                id="bank-1",
                date="2025-01-10",
                provider="hapoalim",
                account_name="Main",
                description="old food",
                amount=-50.0,
                category="Food",
                tag="Groceries",
                source="bank_transactions",
                type=None,
                status="completed",
            )
        )
        db_session.add(
            CreditCardTransaction(
                id="cc-1",
                date="2025-06-20",
                provider="isracard",
                account_name="Main Card",
                description="new food",
                amount=-30.0,
                category="Food",
                tag="Restaurants",
                source="credit_card_transactions",
                type=None,
                status="completed",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert repo.get_category_last_used()["Food"] == "2025-06-20"

    def test_null_category_is_excluded(self, db_session):
        """Rows with no category contribute no entry."""
        db_session.add(
            BankTransaction(
                id="bank-2",
                date="2025-01-10",
                provider="hapoalim",
                account_name="Main",
                description="untagged",
                amount=-50.0,
                category=None,
                tag=None,
                source="bank_transactions",
                type=None,
                status="completed",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert repo.get_category_last_used() == {}

    def test_split_parent_row_is_ignored(self, db_session):
        """A split-parent row's own date does not count as usage."""
        db_session.add(
            CreditCardTransaction(
                id="cc-parent-1",
                date="2025-03-04",
                provider="isracard",
                account_name="Main Card",
                description="split parent",
                amount=-100.0,
                category="Food",
                tag=None,
                source="credit_card_transactions",
                type="split_parent",
                status="completed",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert "Food" not in repo.get_category_last_used()

    def test_split_child_counts_with_parent_date(self, db_session):
        """A split child has no date of its own; its parent's date is used."""
        parent = CreditCardTransaction(
            id="cc-parent-2",
            date="2025-03-04",
            provider="isracard",
            account_name="Main Card",
            description="split parent",
            amount=-100.0,
            category="Food",
            tag=None,
            source="credit_card_transactions",
            type="split_parent",
            status="completed",
        )
        db_session.add(parent)
        db_session.commit()
        db_session.add(
            SplitTransaction(
                transaction_id=parent.unique_id,
                source="credit_card_transactions",
                amount=-10.0,
                category="Transport",
                tag="Gas",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert repo.get_category_last_used()["Transport"] == "2025-03-04"

    def test_orphaned_split_is_ignored(self, db_session):
        """A split whose parent row is gone contributes nothing."""
        db_session.add(
            SplitTransaction(
                transaction_id=999999,
                source="credit_card_transactions",
                amount=-10.0,
                category="Transport",
                tag="Gas",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert repo.get_category_last_used() == {}

    def test_split_id_is_not_matched_across_tables(self, db_session):
        """unique_id is per-table: a bank row must not satisfy a cc-sourced split."""
        bank = BankTransaction(
            id="bank-3",
            date="2025-05-05",
            provider="hapoalim",
            account_name="Main",
            description="unrelated",
            amount=-50.0,
            category="Food",
            tag=None,
            source="bank_transactions",
            type=None,
            status="completed",
        )
        db_session.add(bank)
        db_session.commit()
        db_session.add(
            SplitTransaction(
                transaction_id=bank.unique_id,
                source="credit_card_transactions",
                amount=-10.0,
                category="Transport",
                tag="Gas",
            )
        )
        db_session.commit()
        repo = TransactionsRepository(db_session)
        assert "Transport" not in repo.get_category_last_used()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/repositories/test_transactions_repository.py::TestGetCategoryLastUsed -v --no-cov
```

Expected: FAIL — `AttributeError: 'TransactionsRepository' object has no attribute 'get_category_last_used'`

- [ ] **Step 3: Add the constant**

Append to `backend/constants/categories.py`:

```python
#: A category is considered unused when it has had no transactions for this
#: many months AND was itself created longer ago than this. One constant
#: governs both windows so the rule reads as a single sentence.
UNUSED_CATEGORY_MONTHS = 6
```

- [ ] **Step 4: Implement the repository method**

Add to `backend/repositories/transactions/core.py`, directly after `count_uncategorized` (which ends at line 458). `select`, `func`, `or_` and `SplitTransaction` are all already imported in this module — `count_uncategorized` uses every one of them, so no import changes are needed. Each sub-repo exposes `.model` (the ORM class) and `.table` (the table-name string); both are already used by `count_uncategorized` at lines 429 and 451.

```python
    def get_category_last_used(self) -> dict[str, str]:
        """Return each category's most recent transaction date.

        Scans the four non-insurance transaction tables plus their split
        children, mirroring the merged view used elsewhere: ``split_parent``
        rows are skipped (their children replace them) and split children take
        their date from the parent row, which they are joined to on both
        ``unique_id`` and ``source`` because ``unique_id`` is a per-table
        auto-increment. Orphaned splits are dropped by the inner join, exactly
        as the pandas merged view drops them. Insurance transactions are
        excluded. Pure SQL ``MAX``/``GROUP BY`` — no DataFrame load.

        Dates are ``YYYY-MM-DD`` strings, so lexicographic ``MAX`` is
        chronologically correct.

        Returns
        -------
        dict[str, str]
            Mapping of category name to its latest transaction date. Categories
            with no transactions at all are absent from the mapping.
        """
        last_used: dict[str, str] = {}

        def _record(category: str | None, date_value: str | None) -> None:
            if not category or not date_value:
                return
            current = last_used.get(category)
            if current is None or date_value > current:
                last_used[category] = date_value

        for repo in [
            self.cc_repo,
            self.bank_repo,
            self.cash_repo,
            self.manual_investments_repo,
        ]:
            model = repo.model

            direct_stmt = (
                select(model.category, func.max(model.date))
                .where(
                    model.category.is_not(None),
                    or_(model.type.is_(None), model.type != "split_parent"),
                )
                .group_by(model.category)
            )
            for category, date_value in self.db.execute(direct_stmt).all():
                _record(category, date_value)

            split_stmt = (
                select(SplitTransaction.category, func.max(model.date))
                .join(model, model.unique_id == SplitTransaction.transaction_id)
                .where(
                    SplitTransaction.category.is_not(None),
                    SplitTransaction.source == repo.table,
                )
                .group_by(SplitTransaction.category)
            )
            for category, date_value in self.db.execute(split_stmt).all():
                _record(category, date_value)

        return last_used
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/repositories/test_transactions_repository.py::TestGetCategoryLastUsed -v --no-cov
```

Expected: PASS, 7 tests.



- [ ] **Step 6: Run the surrounding suite for regressions**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/repositories/test_transactions_repository.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/constants/categories.py backend/repositories/transactions/core.py tests/backend/unit/repositories/test_transactions_repository.py
git commit -m "feat(categories): add per-category last-used date query

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend — the unused rule in the service

**Files:**
- Modify: `backend/repositories/tagging_repository.py` (add method after `get_categories_icons`, line 265)
- Modify: `backend/services/tagging_service.py` (add method; the class starts at line 30)
- Test: `tests/backend/unit/services/test_categories_tags_service.py` (append a test class)

**Interfaces:**
- Consumes: `TransactionsRepository.get_category_last_used() -> dict[str, str]` and `UNUSED_CATEGORY_MONTHS` from Task 1.
- Produces: `CategoriesTagsService.get_category_usage() -> dict[str, dict]`, returning an entry for **every** category:
  `{"<name>": {"last_used": str | None, "unused": bool}}` where `last_used` is a `"YYYY-MM-DD"` string or `None`.
  Also `TaggingRepository.get_categories_created_at() -> dict[str, datetime]`.

- [ ] **Step 1: Write the failing tests**

Note the fixture reality: `seed_categories` inserts rows with `created_at` defaulting to **now**, so every seeded category is inside the creation grace and can never be unused. Tests must explicitly age the rows.

Append to `tests/backend/unit/services/test_categories_tags_service.py`:

```python
class TestGetCategoryUsage:
    """Tests for CategoriesTagsService.get_category_usage."""

    @staticmethod
    def _age_all_categories(db_session):
        """Backdate every category so the creation grace never applies."""
        from datetime import datetime

        from backend.models.category import Category

        old = datetime(2020, 1, 1)
        for cat in db_session.query(Category).all():
            cat.created_at = old
        db_session.commit()

    @staticmethod
    def _add_bank_txn(db_session, category, date_str):
        """Insert one categorized bank transaction."""
        from backend.models.transaction import BankTransaction

        db_session.add(
            BankTransaction(
                id=f"txn-{category}-{date_str}",
                date=date_str,
                provider="hapoalim",
                account_name="Main",
                description="x",
                amount=-10.0,
                category=category,
                tag=None,
                source="bank_transactions",
                type=None,
                status="completed",
            )
        )
        db_session.commit()

    @staticmethod
    def _iso_months_ago(months):
        """Return an ISO date string that many months in the past."""
        import pandas as pd

        return (
            pd.Timestamp.today().normalize() - pd.DateOffset(months=months)
        ).strftime("%Y-%m-%d")

    def test_every_category_is_present(self, categories_service, db_session):
        """The result covers every category, used or not."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        assert set(result) == set(categories_service.get_categories_and_tags())

    def test_stale_category_is_unused(self, categories_service, db_session):
        """A category whose only transaction is older than the window is unused."""
        self._age_all_categories(db_session)
        self._add_bank_txn(db_session, "Food", self._iso_months_ago(9))
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is True
        assert result["Food"]["last_used"] == self._iso_months_ago(9)

    def test_recent_transaction_keeps_category_active(
        self, categories_service, db_session
    ):
        """A transaction inside the window keeps the category active."""
        self._age_all_categories(db_session)
        self._add_bank_txn(db_session, "Food", self._iso_months_ago(1))
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False

    def test_never_used_old_category_is_unused(
        self, categories_service, db_session
    ):
        """An old category with no transactions at all is unused."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is True
        assert result["Food"]["last_used"] is None

    def test_protected_category_is_never_unused(
        self, categories_service, db_session
    ):
        """Protected categories are exempt even with no transactions."""
        self._age_all_categories(db_session)
        result = categories_service.get_category_usage()
        for name in PROTECTED_CATEGORIES:
            if name in result:
                assert result[name]["unused"] is False

    def test_recently_created_category_is_exempt(
        self, categories_service, db_session
    ):
        """A category created inside the window is exempt despite no usage."""
        self._age_all_categories(db_session)
        from datetime import datetime

        from backend.models.category import Category

        fresh = db_session.query(Category).filter_by(name="Food").one()
        fresh.created_at = datetime.now()
        db_session.commit()
        result = categories_service.get_category_usage()
        assert result["Food"]["unused"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/services/test_categories_tags_service.py::TestGetCategoryUsage -v --no-cov
```

Expected: FAIL — `AttributeError: 'CategoriesTagsService' object has no attribute 'get_category_usage'`

- [ ] **Step 3: Add the repository method**

Add to `backend/repositories/tagging_repository.py`:

```python
    def get_categories_created_at(self) -> dict[str, datetime]:
        """Return each category's creation timestamp.

        Returns
        -------
        dict[str, datetime]
            Mapping of category name to its ``created_at`` value.
        """
        return {
            name: created_at
            for name, created_at in self.db.execute(
                select(Category.name, Category.created_at)
            ).all()
        }
```

`select` and `Category` are already imported in that module. `datetime` is not — add `from datetime import datetime` to the import block at the top.

- [ ] **Step 4: Add the service method**

Add to `backend/services/tagging_service.py`:

First extend the module-level imports at the top of the file. `PROTECTED_CATEGORIES` is already imported from `backend.constants.categories` — add the new constant to that same line:

```python
from backend.constants.categories import (
    PROTECTED_CATEGORIES,
    PROTECTED_TAGS,
    UNUSED_CATEGORY_MONTHS,
)
```

and add, with the other stdlib/third-party imports:

```python
from datetime import date

import pandas as pd
```

Then add the method. `TransactionsRepository` is already constructed in `__init__` as `self.transactions_repo`, and the tagging repository as `self.tagging_repo` — reuse both rather than building new ones:

```python
    def get_category_usage(self) -> dict[str, dict]:
        """Return per-category usage info and the unused verdict.

        A category is unused when it has had no transaction for
        ``UNUSED_CATEGORY_MONTHS`` months, was itself created longer ago than
        that, and is not protected. The creation grace stops a freshly added
        category — which has no transactions by definition — from being
        demoted the moment it is created.

        Returns
        -------
        dict[str, dict]
            Mapping of category name to ``{"last_used": str | None,
            "unused": bool}``. ``last_used`` is a ``YYYY-MM-DD`` string, or
            ``None`` when the category has never been used.
        """
        cutoff = (
            pd.Timestamp.today().normalize()
            - pd.DateOffset(months=UNUSED_CATEGORY_MONTHS)
        ).date()

        last_used_map = self.transactions_repo.get_category_last_used()
        created_at_map = self.tagging_repo.get_categories_created_at()

        usage: dict[str, dict] = {}
        for name in self.get_categories_and_tags():
            last_used = last_used_map.get(name)
            created_at = created_at_map.get(name)
            created_before_cutoff = (
                created_at is not None and created_at.date() < cutoff
            )
            used_recently = (
                last_used is not None and date.fromisoformat(last_used) >= cutoff
            )
            usage[name] = {
                "last_used": last_used,
                "unused": (
                    name not in PROTECTED_CATEGORIES
                    and created_before_cutoff
                    and not used_recently
                ),
            }
        return usage
```

Both attribute names are verified against `__init__` (line 40): the class already builds `self.tagging_repo` and `self.transactions_repo`. Do not construct new repository instances.

- [ ] **Step 5: Run tests to verify they pass**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/services/test_categories_tags_service.py::TestGetCategoryUsage -v --no-cov
```

Expected: PASS, 6 tests.

- [ ] **Step 6: Run the surrounding suites**

```bash
../../../.venv/bin/python -m pytest tests/backend/unit/services/test_categories_tags_service.py tests/backend/unit/repositories/test_tagging_repository.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/repositories/tagging_repository.py backend/services/tagging_service.py tests/backend/unit/services/test_categories_tags_service.py
git commit -m "feat(categories): compute the unused-category verdict in the service

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Backend route + frontend API wiring

**Files:**
- Modify: `backend/routes/tagging.py` (add route near `get_categories`, line 51)
- Modify: `frontend/src/services/api.ts` (add to `taggingApi`, which starts at line 246)
- Modify: `frontend/src/services/queryKeys.ts` (add to the `tagging` group, line 82)
- Modify: `frontend/src/mocks/handlers.ts` (add handler beside the other tagging handlers, line 290)
- Test: `tests/backend/routes/test_tagging_routes.py` (exists — append a class)

**Interfaces:**
- Consumes: `CategoriesTagsService.get_category_usage()` from Task 2.
- Produces:
  - Endpoint `GET /tagging/categories/usage`
  - `taggingApi.getCategoryUsage()` → axios promise of `Record<string, { last_used: string | null; unused: boolean }>`
  - `qk.tagging.categoryUsage()` query key
  - MSW handler for `/api/tagging/categories/usage`

- [ ] **Step 1: Write the failing route test**

`tests/backend/routes/test_tagging_routes.py` already exists — append this class to it:

```python
class TestCategoryUsageRoute:
    """Tests for GET /tagging/categories/usage."""

    def test_returns_an_entry_per_category(self, test_client, seed_categories):
        """Every category appears in the usage response."""
        response = test_client.get("/api/tagging/categories/usage")

        assert response.status_code == 200
        body = response.json()
        categories = test_client.get("/api/tagging/categories").json()
        assert set(body) == set(categories)

    def test_entry_shape(self, test_client, seed_categories):
        """Each entry carries last_used and unused."""
        response = test_client.get("/api/tagging/categories/usage")

        entry = next(iter(response.json().values()))
        assert set(entry) == {"last_used", "unused"}
        assert isinstance(entry["unused"], bool)

    def test_freshly_seeded_categories_are_not_unused(
        self, test_client, seed_categories
    ):
        """Categories created just now are inside the creation grace."""
        body = test_client.get("/api/tagging/categories/usage").json()

        assert all(entry["unused"] is False for entry in body.values())
```

The prefix is verified: `backend/main.py:426` mounts the router with `prefix="/api/tagging"`, so these paths are correct as written.

- [ ] **Step 2: Run the test to verify it fails**

```bash
../../../.venv/bin/python -m pytest tests/backend/routes/test_tagging_routes.py::TestCategoryUsageRoute -v --no-cov
```

Expected: FAIL with 404.

- [ ] **Step 3: Add the route**

Add to `backend/routes/tagging.py`, immediately after `get_categories`:

```python
@router.get("/categories/usage")
def get_category_usage(db: Session = Depends(get_database)):
    """Get per-category last-used date and whether the category is unused.

    A category is unused when it has had no transactions for six months, was
    created longer ago than that, and is not protected. Display-only — no
    other endpoint filters on this.
    """
    return CategoriesTagsService(db).get_category_usage()
```

This must sit above nothing in particular for correctness — `/categories/{name}` has only `DELETE` and `PUT`, no `GET`, so there is no path-shadowing conflict.

- [ ] **Step 4: Run the test to verify it passes**

```bash
../../../.venv/bin/python -m pytest tests/backend/routes/test_tagging_routes.py::TestCategoryUsageRoute -v --no-cov
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Add the frontend API client entry**

In `frontend/src/services/api.ts`, add directly under `getCategories` in `taggingApi`:

```typescript
  getCategoryUsage: () => api.get("/tagging/categories/usage"),
```

- [ ] **Step 6: Add the query key**

In `frontend/src/services/queryKeys.ts`, inside the `tagging` group:

```typescript
      categoryUsage: () => ["category-usage", demo] as const,
```

- [ ] **Step 7: Add the MSW handler**

In `frontend/src/mocks/handlers.ts`, add above the existing `http.get("/api/tagging/categories", ...)` handler:

```typescript
  http.get("/api/tagging/categories/usage", () =>
    HttpResponse.json(
      Object.fromEntries(
        Object.keys(mockCategories).map((name) => [
          name,
          { last_used: "2026-08-01", unused: false },
        ]),
      ),
    ),
  ),
```

Every category defaults to used, so existing page tests are unaffected. Tests that need an unused category override this handler per-test.

- [ ] **Step 8: Verify the frontend still builds**

```bash
cd frontend && npm run lint && npm run build && cd ..
```

Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add backend/routes/tagging.py tests/backend/routes/test_tagging_routes.py frontend/src/services/api.ts frontend/src/services/queryKeys.ts frontend/src/mocks/handlers.ts
git commit -m "feat(categories): expose category usage endpoint and client wiring

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Extract the category card component

**Files:**
- Create: `frontend/src/components/categories/CategoryCard.tsx`
- Modify: `frontend/src/pages/Categories.tsx:88-114` (replace the inline card JSX)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CategoryCard` — a default-exported-by-name React component:

```typescript
interface CategoryCardProps {
  category: string;
  icon: string | undefined;
  subtitle: string;
  onClick: () => void;
  muted?: boolean;
}
export function CategoryCard(props: CategoryCardProps): JSX.Element
```

It renders the same `data-testid={`category-card-${category}`}` the existing tests and e2e specs rely on. This is a pure refactor — no behavior changes in this task.

- [ ] **Step 1: Verify the existing tests pass before refactoring**

```bash
cd frontend && npx vitest run src/pages/Categories.test.tsx && cd ..
```

Expected: PASS. This is the safety net for the refactor — a pure extraction needs no new test.

- [ ] **Step 2: Create the component**

`frontend/src/components/categories/CategoryCard.tsx`:

```tsx
import { Wallet } from "lucide-react";

interface CategoryCardProps {
  /** Category name, shown as the card title. */
  category: string;
  /** Emoji icon, or undefined to fall back to the wallet glyph. */
  icon: string | undefined;
  /** Secondary line: tag count for active cards, last-used for unused ones. */
  subtitle: string;
  onClick: () => void;
  /** Dim the card, marking it as unused. */
  muted?: boolean;
}

/**
 * One category tile in the categories grid. Shared by the active grid and the
 * unused section so the two stay visually identical apart from the muting.
 */
export function CategoryCard({
  category,
  icon,
  subtitle,
  onClick,
  muted = false,
}: CategoryCardProps) {
  return (
    <button
      data-testid={`category-card-${category}`}
      onClick={onClick}
      className={`flex flex-col items-center gap-1.5 sm:gap-2 p-2 sm:p-4 bg-[var(--surface)] rounded-xl sm:rounded-2xl border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--surface-light)]/30 transition-all text-center group ${
        muted ? "opacity-60 hover:opacity-100" : ""
      }`}
    >
      <div className="w-9 h-9 sm:w-12 sm:h-12 flex items-center justify-center rounded-lg sm:rounded-xl bg-blue-500/10 border border-blue-500/20 text-lg sm:text-2xl shrink-0">
        {icon ? (
          <span>{icon}</span>
        ) : (
          <Wallet className="text-blue-400 w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]" />
        )}
      </div>
      <h3 className="font-bold text-xs sm:text-sm truncate w-full" dir="auto">
        {category}
      </h3>
      <span className="text-[10px] sm:text-xs text-[var(--text-muted)]" dir="ltr">
        {subtitle}
      </span>
    </button>
  );
}
```

- [ ] **Step 3: Use it in the page**

In `frontend/src/pages/Categories.tsx`, replace the whole `filteredEntries.map(...)` callback body (the inline `<button>`, lines 88–114) with:

```tsx
          {filteredEntries.map(([category, tags]) => (
            <CategoryCard
              key={category}
              category={category}
              icon={icons?.[category]}
              subtitle={t("categories.tagsCount", { count: tags.length })}
              onClick={() => setSelectedCategory(category)}
            />
          ))}
```

Add the import:

```tsx
import { CategoryCard } from "../components/categories/CategoryCard";
```

Then remove `Wallet` from the `lucide-react` import in `Categories.tsx` if nothing else in that file uses it — the build's `noUnusedLocals` will fail otherwise.

- [ ] **Step 4: Run tests and build**

```bash
cd frontend && npx vitest run src/pages/Categories.test.tsx && npm run lint && npm run build && cd ..
```

Expected: PASS and a clean build. Identical rendering — this task changes no behavior.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/categories/CategoryCard.tsx frontend/src/pages/Categories.tsx
git commit -m "refactor(categories): extract CategoryCard from the categories grid

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: The unused-categories section component

**Files:**
- Create: `frontend/src/components/categories/UnusedCategoriesSection.tsx`
- Create: `frontend/src/components/categories/UnusedCategoriesSection.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

**Interfaces:**
- Consumes: `CategoryCard` from Task 4.
- Produces:

```typescript
interface UnusedCategoriesSectionProps {
  entries: [string, string[]][];
  icons: Record<string, string>;
  usage: Record<string, { last_used: string | null; unused: boolean }>;
  expanded: boolean;
  onToggle: () => void;
  onSelect: (category: string) => void;
}
export function UnusedCategoriesSection(
  props: UnusedCategoriesSectionProps,
): JSX.Element | null
```

Returns `null` when `entries` is empty. Expansion is **controlled by the parent** so Task 6 can force it open on search. Exposes `data-testid="unused-categories-toggle"` and `data-testid="unused-categories-grid"`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/categories/UnusedCategoriesSection.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { UnusedCategoriesSection } from "./UnusedCategoriesSection";

const usage = {
  Wedding: { last_used: "2025-01-20", unused: true },
  Renovation: { last_used: null, unused: true },
};

describe("UnusedCategoriesSection", () => {
  it("renders nothing when there are no unused categories", () => {
    const { container } = renderWithProviders(
      <UnusedCategoriesSection
        entries={[]}
        icons={{}}
        usage={{}}
        expanded={false}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("hides the grid when collapsed", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={false}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("unused-categories-grid")).not.toBeInTheDocument();
  });

  it("shows the cards when expanded", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("category-card-Wedding")).toBeInTheDocument();
  });

  it("calls onToggle when the disclosure is clicked", () => {
    const onToggle = vi.fn();
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={false}
        onToggle={onToggle}
        onSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("unused-categories-toggle"));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("labels a never-used category distinctly from a stale one", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[
          ["Wedding", ["Venue"]],
          ["Renovation", ["Labor"]],
        ]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    const wedding = screen.getByTestId("category-card-Wedding");
    const renovation = screen.getByTestId("category-card-Renovation");
    expect(wedding.textContent).not.toEqual(renovation.textContent);
    expect(renovation.textContent).toMatch(/neverUsed|never used/i);
  });

  it("calls onSelect with the category when a card is clicked", () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("category-card-Wedding"));
    expect(onSelect).toHaveBeenCalledWith("Wedding");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/components/categories/UnusedCategoriesSection.test.tsx && cd ..
```

Expected: FAIL — cannot resolve `./UnusedCategoriesSection`.

- [ ] **Step 3: Add the i18n keys**

In `frontend/src/locales/en.json`, inside the `categories` object:

```json
    "unusedSection": "Unused categories",
    "unusedHint": "No transactions in the last 6 months",
    "lastUsed": "Last used {{date}}",
    "neverUsed": "Never used",
```

In `frontend/src/locales/he.json`, inside the same object:

```json
    "unusedSection": "קטגוריות לא בשימוש",
    "unusedHint": "ללא תנועות בששת החודשים האחרונים",
    "lastUsed": "שימוש אחרון {{date}}",
    "neverUsed": "לא היה בשימוש",
```

- [ ] **Step 4: Create the component**

`frontend/src/components/categories/UnusedCategoriesSection.tsx`:

```tsx
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { CategoryCard } from "./CategoryCard";
import { formatMonthYear } from "../../utils/dateFormatting";

interface CategoryUsage {
  last_used: string | null;
  unused: boolean;
}

interface UnusedCategoriesSectionProps {
  /** Unused categories as [name, tags] pairs, already filtered and sorted. */
  entries: [string, string[]][];
  icons: Record<string, string>;
  usage: Record<string, CategoryUsage>;
  /** Controlled by the parent so a search can force the section open. */
  expanded: boolean;
  onToggle: () => void;
  onSelect: (category: string) => void;
}

/**
 * Collapsed disclosure holding categories that have gone quiet, keeping the
 * main grid lean as categories accumulate. Display-only: these categories are
 * still fully usable everywhere else in the app.
 */
export function UnusedCategoriesSection({
  entries,
  icons,
  usage,
  expanded,
  onToggle,
  onSelect,
}: UnusedCategoriesSectionProps) {
  const { t } = useTranslation();

  if (entries.length === 0) return null;

  return (
    <div className="border border-[var(--surface-light)] rounded-xl overflow-hidden">
      <button
        data-testid="unused-categories-toggle"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 px-4 py-3 text-start hover:bg-[var(--surface-light)]/30 transition-colors"
      >
        <ChevronDown
          size={16}
          className={`shrink-0 text-[var(--text-muted)] transition-transform ${
            expanded ? "" : "-rotate-90 rtl:rotate-90"
          }`}
        />
        <span className="font-bold text-sm">
          {t("categories.unusedSection")}
        </span>
        <span className="text-xs text-[var(--text-muted)]" dir="ltr">
          ({entries.length})
        </span>
        <span className="ms-auto text-xs text-[var(--text-muted)] hidden sm:inline">
          {t("categories.unusedHint")}
        </span>
      </button>

      {expanded && (
        <div
          data-testid="unused-categories-grid"
          className="grid grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-3 p-3"
        >
          {entries.map(([category]) => {
            const lastUsed = usage[category]?.last_used;
            return (
              <CategoryCard
                key={category}
                category={category}
                icon={icons[category]}
                muted
                subtitle={
                  lastUsed
                    ? t("categories.lastUsed", {
                        date: formatMonthYear(lastUsed),
                      })
                    : t("categories.neverUsed")
                }
                onClick={() => onSelect(category)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/components/categories/UnusedCategoriesSection.test.tsx && cd ..
```

Expected: PASS, 6 tests.

- [ ] **Step 6: Verify both locale files parse and have matching keys**

```bash
cd frontend && node -e "
const en = require('./src/locales/en.json').categories;
const he = require('./src/locales/he.json').categories;
const keys = ['unusedSection','unusedHint','lastUsed','neverUsed'];
for (const k of keys) {
  if (!en[k]) throw new Error('missing en.' + k);
  if (!he[k]) throw new Error('missing he.' + k);
}
console.log('both locales OK');
" && cd ..
```

Expected: `both locales OK`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/categories/UnusedCategoriesSection.tsx frontend/src/components/categories/UnusedCategoriesSection.test.tsx frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(categories): add the collapsed unused-categories section

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Wire the section into the Categories page

**Files:**
- Modify: `frontend/src/hooks/useCategories.ts` (append the hook)
- Modify: `frontend/src/pages/Categories.tsx`
- Modify: `frontend/src/pages/Categories.test.tsx` (append tests)

**Interfaces:**
- Consumes: `taggingApi.getCategoryUsage()` and `qk.tagging.categoryUsage()` (Task 3), `UnusedCategoriesSection` (Task 5), `CategoryCard` (Task 4).
- Produces: `useCategoryUsage()` returning a TanStack Query result whose `data` is `Record<string, { last_used: string | null; unused: boolean }> | undefined`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/pages/Categories.test.tsx`. The file currently imports `{ describe, it, expect }` from vitest and `{ screen, waitFor, fireEvent }` from testing-library; those are sufficient. `server.use(...)` overrides are reset between tests by the existing global MSW setup, so no manual cleanup hook is needed.

```tsx
  describe("unused categories", () => {
    it("does not render the section when every category is in use", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("unused-categories-toggle"),
      ).not.toBeInTheDocument();
    });

    it("moves unused categories out of the main grid and into the section", async () => {
      server.use(
        http.get("/api/tagging/categories/usage", () =>
          HttpResponse.json({
            Food: { last_used: "2026-08-01", unused: false },
            Transport: { last_used: "2025-01-05", unused: true },
          }),
        ),
      );
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
      });
      expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      expect(screen.queryByTestId("category-card-Transport")).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId("unused-categories-toggle"));
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Transport")).toBeInTheDocument();
      });
    });

    it("auto-expands the section when a search matches an unused category", async () => {
      server.use(
        http.get("/api/tagging/categories/usage", () =>
          HttpResponse.json({
            Food: { last_used: "2026-08-01", unused: false },
            Transport: { last_used: "2025-01-05", unused: true },
          }),
        ),
      );
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("category-card-Transport")).not.toBeInTheDocument();

      fireEvent.change(
        screen.getByPlaceholderText(/searchPlaceholder|search categories/i),
        { target: { value: "Transport" } },
      );
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Transport")).toBeInTheDocument();
      });
    });
  });
```

Add at the top of the file:

```tsx
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
```

That path is verified: `frontend/src/mocks/server.ts:4` exports `server`.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && npx vitest run src/pages/Categories.test.tsx && cd ..
```

Expected: the three new tests FAIL (no `unused-categories-toggle` element); the existing tests still PASS.

- [ ] **Step 3: Add the hook**

Append to `frontend/src/hooks/useCategories.ts`:

```typescript
export interface CategoryUsage {
  last_used: string | null;
  unused: boolean;
}

/**
 * Per-category usage info: last transaction date and whether the category has
 * gone unused (no transactions for six months, created longer ago than that,
 * and not protected). Display-only — used to demote quiet categories into a
 * collapsed section on the Categories page.
 */
export function useCategoryUsage() {
  const qk = useQueryKeys();
  return useQuery({
    queryKey: qk.tagging.categoryUsage(),
    queryFn: () =>
      taggingApi
        .getCategoryUsage()
        .then((res) => res.data as Record<string, CategoryUsage>),
  });
}
```

- [ ] **Step 4: Split the grids in the page**

In `frontend/src/pages/Categories.tsx`:

Update the imports:

```tsx
import { useCategories, useCategoryUsage } from "../hooks/useCategories";
import { UnusedCategoriesSection } from "../components/categories/UnusedCategoriesSection";
```

Add state and the query alongside the existing ones:

```tsx
  const [unusedExpanded, setUnusedExpanded] = useState(false);
  const { data: usage } = useCategoryUsage();
```

Replace the `filteredEntries` memo with a split that keeps the same filtering:

```tsx
  const { activeEntries, unusedEntries } = useMemo(() => {
    if (!categoriesRecord) return { activeEntries: [], unusedEntries: [] };
    const allEntries = Object.entries(categoriesRecord).sort(([a], [b]) =>
      a.localeCompare(b),
    );
    const query = searchQuery.toLowerCase().trim();
    const matching = query
      ? allEntries.filter(
          ([category, tags]) =>
            category.toLowerCase().includes(query) ||
            tags.some((tagName) => tagName.toLowerCase().includes(query)),
        )
      : allEntries;
    // Until the usage query resolves, every category renders in the main grid
    // — the page degrades to its previous behavior rather than flashing cards
    // in and out of the collapsed section.
    return {
      activeEntries: matching.filter(([category]) => !usage?.[category]?.unused),
      unusedEntries: matching.filter(([category]) => usage?.[category]?.unused),
    };
  }, [categoriesRecord, searchQuery, usage]);
```

The empty-state check below the grid uses `filteredEntries.length > 0`; change it to render the grid when `activeEntries.length > 0`, and change the "no results" branch condition to `searchQuery.trim() && activeEntries.length === 0 && unusedEntries.length === 0` so a search that only matches an unused category does not show "no results" alongside the populated section.

Map `activeEntries` in the main grid instead of `filteredEntries`.

Render the section immediately after the main grid block and before the detail panel:

```tsx
      <UnusedCategoriesSection
        entries={unusedEntries}
        icons={icons ?? {}}
        usage={usage ?? {}}
        expanded={unusedExpanded || searchQuery.trim().length > 0}
        onToggle={() => setUnusedExpanded((prev) => !prev)}
        onSelect={setSelectedCategory}
      />
```

Deriving `expanded` this way is what auto-expands the section on search: any non-empty query forces it open, and clearing the query returns it to the user's manual state.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd frontend && npx vitest run src/pages/Categories.test.tsx && cd ..
```

Expected: PASS, all tests including the three new ones.

- [ ] **Step 6: Run the full frontend gate**

```bash
cd frontend && npm run lint && npm run build && npm test && cd ..
```

Expected: clean lint, clean build, all vitest suites green.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useCategories.ts frontend/src/pages/Categories.tsx frontend/src/pages/Categories.test.tsx
git commit -m "feat(categories): split the grid into active and unused sections

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: e2e coverage

**Files:**
- Modify: `frontend/e2e/categories.spec.ts` (add a second `test()` inside the existing `test.describe`)

**Interfaces:**
- Consumes: the DOM contract from Tasks 4–6 (`unused-categories-toggle`, `unused-categories-grid`, `category-card-<name>`).
- Produces: nothing consumed by later tasks.

**Why this is a separate `test()` and not part of the journey.** The spec originally called for folding these checks into the existing single-load journey test. That is not possible: the frozen demo DB seeds every category with `created_at = 2026-07-29`, and `_shift_dates` in `backend/demo_setup.py` shifts only transaction-bearing tables — `categories` is not in its list. So in Demo Mode every category is inside the creation grace and the section never renders today, while it *would* start rendering once real time passes six months from that stamp. Asserting either way against demo data yields a test that is vacuous now and flips later. Stubbing the usage response with `page.route()` makes the assertion deterministic, and a route stub is exactly the documented reason to open a separate `test()` (a different pre-boot env). The stub intercepts a GET only, so the spec performs no backend writes and stays eligible for `READ_ONLY_SPECS`, where it is currently listed at `frontend/playwright.config.ts:74`.

- [ ] **Step 1: Write the test**

Add inside the existing `test.describe("Categories", ...)` block in `frontend/e2e/categories.spec.ts`, after the journey test:

```typescript
  // Separate test (not folded into the journey above) because it needs a
  // page.route() stub installed before the page boots. The demo DB stamps
  // every category's created_at at snapshot-build time and demo_setup's
  // date shift does not touch the categories table, so no demo category is
  // ever old enough to be unused — the stub is what makes this assertable.
  test("unused categories collapse into their own section", async ({ page }) => {
    await page.route("**/api/tagging/categories/usage", async (route) => {
      const response = await route.fetch();
      const usage = await response.json();
      const stubbed = Object.fromEntries(
        Object.keys(usage).map((name) => [
          name,
          name === "Wedding"
            ? { last_used: "2025-01-20", unused: true }
            : { last_used: "2026-08-01", unused: false },
        ]),
      );
      await route.fulfill({ json: stubbed });
    });

    await page.setViewportSize({ width: 1280, height: 800 });
    await navigateTo(page, "/categories");

    const toggle = page.getByTestId("unused-categories-toggle");
    await expect(toggle).toBeVisible({ timeout: 10_000 });

    // --- Collapsed by default: the unused card is out of the main grid ---
    await expect(page.getByTestId("unused-categories-grid")).toBeHidden();
    await expect(page.getByTestId("category-card-Wedding")).toBeHidden();
    await expect(page.getByTestId("category-card-Food")).toBeVisible();

    // --- Expanding reveals the card ---
    await toggle.click();
    await expect(page.getByTestId("category-card-Wedding")).toBeVisible();

    // --- Searching an unused category auto-expands the section ---
    await toggle.click();
    await expect(page.getByTestId("category-card-Wedding")).toBeHidden();
    await page.getByPlaceholder(/Search categories and tags/i).fill("Wedding");
    await expect(page.getByTestId("category-card-Wedding")).toBeVisible();
  });
```

- [ ] **Step 2: Confirm "Wedding" exists in the demo data**

```bash
python3 -c "
import sqlite3
c = sqlite3.connect('backend/resources/demo_data.db')
print([r[0] for r in c.execute('select name from categories')])
"
```

Expected: the list contains `Wedding`. If it does not, pick any non-protected category from the printed list and substitute it throughout the test.

- [ ] **Step 3: Run the spec**

```bash
cd frontend && npm run test:e2e:isolated -- e2e/categories.spec.ts && cd ..
```

If the runner rejects a positional filter, run the serial fallback instead:

```bash
python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/categories.spec.ts"
```

Expected: PASS, both tests in the file. A browser that fails to launch means the spec did not run — that is not a pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/categories.spec.ts
git commit -m "test(categories): e2e coverage for the unused-categories section

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Full pre-PR verification

**Files:** none modified — this task only runs the gates.

**Interfaces:**
- Consumes: everything from Tasks 1–7.
- Produces: a green local run of every check CI will run.

- [ ] **Step 1: Backend suite with coverage**

```bash
poetry run pytest
```

Expected: PASS with the coverage gate satisfied. If `poetry` is unavailable in this worktree, bootstrap first with `./.claude/scripts/bootstrap_venv.sh` (~90 s).

- [ ] **Step 2: Frontend lint, build, unit tests**

```bash
cd frontend && npm run lint && npm run build && npm test && cd ..
```

Expected: all clean.

- [ ] **Step 3: Full e2e suite**

```bash
cd frontend && npm run test:e2e:isolated && cd ..
```

Expected: PASS. The whole suite matters, not just `categories.spec.ts` — `CategoryCard` is shared and the page layout changed.

- [ ] **Step 4: Report results**

State the actual command output for each gate. Do not claim a gate passed without having run it.
