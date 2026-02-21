# Test Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement ~383 new tests across repositories, services, scrapers, integration, and routes for the finance-analysis FastAPI backend.

**Architecture:** Bottom-up layer testing. Repositories tested with in-memory SQLite. Services tested with mocked repos. Routes tested with FastAPI TestClient and dependency overrides. Composable seed fixtures provide realistic test data.

**Tech Stack:** pytest, SQLAlchemy (in-memory SQLite), unittest.mock, FastAPI TestClient, pandas

---

## Conventions

All test files follow these project rules:
- **Always use test classes** to group related tests
- **Every test class and function MUST have a docstring**
- **Naming:** `test_<method>_<scenario>_<expected>`
- **Imports:** Use absolute imports from `backend.*`
- **Run command:** `source .venv/bin/activate && python -m pytest <path> -v`

## Existing Files Reference

These files already exist and pass — don't recreate them:
- `tests/conftest.py` — `db_engine`, `db_session` fixtures
- `tests/backend/unit/repositories/test_transactions_repository.py` — 3 delegation tests
- `tests/backend/unit/repositories/test_pending_refunds_repository.py` — 12 tests
- `tests/backend/unit/repositories/test_bank_balance_repository.py` — 7 tests
- `tests/backend/unit/services/test_pending_refunds_service.py` — 12 tests
- `tests/backend/unit/services/test_bank_balance_service.py` — 8 tests
- `tests/backend/unit/services/test_budget_service.py` — 1 test (ProjectBudgetService)
- `tests/backend/unit/services/test_tagging_rules_service.py` — 7 tests
- `tests/backend/unit/test_models.py` — 35 tests
- `tests/backend/unit/test_text_utils.py` — 20 tests

---

## Task 1: Seed Fixtures & Test Infrastructure

**Files:**
- Create: `tests/backend/conftest.py`

**What:** Create composable seed fixtures that insert realistic ORM records into the in-memory SQLite database. These fixtures are the foundation for all subsequent tests.

**Context:**
- `tests/conftest.py` already provides `db_engine` and `db_session` (function-scoped, in-memory SQLite)
- Transaction models: `CreditCardTransaction`, `BankTransaction`, `CashTransaction`, `ManualInvestmentTransaction` in `backend/models/transaction.py`
- Key fields: `date`, `description`, `amount` (negative=expense), `category`, `tag`, `provider`, `account_name`, `account_number`, `status`, `type`
- Split model: `SplitTransaction` with `transaction_id`, `source`, `amount`, `category`, `tag`
- Budget model: `BudgetRule` with `name`, `amount`, `category`, `tags` (semicolon-separated), `month`, `year`
- Non-expense categories: "Ignore", "Salary", "Other Income", "Investments", "Liabilities"

**Step 1: Create `tests/backend/conftest.py` with all seed fixtures**

The file must contain these fixtures (all function-scoped, accepting `db_session`):

1. `seed_base_transactions(db_session)` — ~30 transactions across 3 months (2024-01 to 2024-03):
   - CC transactions: Food/Groceries (-150), Food/Restaurants (-80), Transport/Gas (-60), Entertainment/Cinema (-40)
   - Bank transactions: Salary (+8000), Rent/Housing (-3000), Ignore/Transfer (-500, +500)
   - Cash transactions: Food/Coffee (-15), Transport/Parking (-10)
   - Spread across months with varying amounts
   - Return the list of created ORM objects

2. `seed_split_transactions(db_session)` — ~6 records:
   - 1 CC parent transaction (-300, category=None after split)
   - 3 split children: Food/Groceries (-150), Home/Cleaning (-100), Other (-50)
   - 1 bank parent transaction (-200)
   - 2 split children

3. `seed_prior_wealth_transactions(db_session)` — ~4 records:
   - Cash transaction: "Prior Wealth" tag, Other Income category, +5000
   - Manual investment transaction: "Prior Wealth" tag, Other Income, +3000
   - BankBalance records with prior_wealth_amount set

4. `seed_untagged_transactions(db_session)` — ~8 records:
   - CC and bank transactions with `category=None, tag=None`
   - Various descriptions matching potential tagging rules (e.g., "SUPERMARKET", "UBER", "Netflix")

5. `seed_project_transactions(db_session)` — ~10 records:
   - Transactions categorized as "Wedding" and "Renovation" projects
   - Various tags: "Venue", "Catering", "Materials", "Labor"
   - BudgetRule entries for the projects

6. `seed_budget_rules(db_session)` — Budget rules for 2024-01:
   - Total Budget: 10000
   - Food: 2000 (tags: "All Tags")
   - Transport: 500
   - Entertainment: 300

7. `seed_tagging_rules(db_session)` — TaggingRule entries:
   - Rule 1: description contains "SUPERMARKET" → Food/Groceries (priority 10)
   - Rule 2: description contains "UBER" → Transport/Rides (priority 5)
   - Rule 3: description contains "Netflix" → Entertainment/Streaming (priority 3)

8. `seed_investments(db_session)` — Investment + ManualInvestmentTransaction records:
   - 2 investments: "Stock Fund" (open), "Bond Fund" (closed)
   - Related transactions for each

9. `sample_categories_yaml()` — Returns dict:
   ```python
   {"Food": ["Groceries", "Restaurants", "Coffee"],
    "Transport": ["Gas", "Parking", "Rides"],
    "Entertainment": ["Cinema", "Streaming"],
    "Salary": [], "Other Income": ["Prior Wealth"],
    "Ignore": ["Transfer"], "Investments": ["Stock Fund", "Bond Fund"],
    "Liabilities": ["Mortgage"], "Wedding": ["Venue", "Catering"],
    "Renovation": ["Materials", "Labor"]}
   ```

10. `sample_credentials_yaml()` — Returns fake credentials dict (same structure as existing `DataFixtures.fake_credentials`)

**Step 2: Run to verify fixtures load**
```bash
source .venv/bin/activate && python -m pytest tests/backend/conftest.py --collect-only
```
Expected: Collection succeeds, fixtures are discoverable.

**Step 3: Commit**
```bash
git add tests/backend/conftest.py
git commit -m "test: add composable seed fixtures for test suite"
```

---

## Task 2: Budget Repository Tests

**Files:**
- Create: `tests/backend/unit/repositories/test_budget_repository.py`
- Reference: `backend/repositories/budget_repository.py`

**What:** Test BudgetRepository CRUD operations using real in-memory SQLite.

**Tests to write (~12):**

```python
class TestBudgetRepository:
    """Tests for BudgetRepository CRUD operations."""

    def test_add_monthly_rule(self, db_session):
        """Verify adding a monthly budget rule persists correctly."""

    def test_add_project_rule(self, db_session):
        """Verify adding a project rule (month=None, year=None) persists correctly."""

    def test_read_all(self, db_session):
        """Verify read_all returns all rules as DataFrame."""

    def test_read_by_id(self, db_session):
        """Verify read_by_id returns correct rule."""

    def test_read_by_month(self, db_session):
        """Verify read_by_month filters correctly."""

    def test_read_project_rules(self, db_session):
        """Verify read_project_rules returns only rules with null month/year."""

    def test_update_rule(self, db_session):
        """Verify update changes the specified fields."""

    def test_delete_rule(self, db_session):
        """Verify delete removes the rule."""

    def test_delete_by_month(self, db_session):
        """Verify delete_by_month removes all rules for that month."""

    def test_delete_by_category(self, db_session):
        """Verify delete_by_category removes all rules for that category."""

    def test_delete_by_category_and_tags(self, db_session):
        """Verify delete_by_category_and_tags removes matching rules."""

    def test_tags_stored_as_semicolon_string(self, db_session):
        """Verify tags are stored as semicolon-separated string."""
```

**Key details:**
- Use `db_session` fixture (from `tests/conftest.py`)
- Create BudgetRepository(db_session) in each test
- Call `repo.add(name, amount, category, tags_str, month, year)` then verify with `repo.read_all()`
- Tags are stored as semicolon-separated strings (e.g., `"Groceries;Restaurants"`)
- Project rules have `month=None, year=None`

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/repositories/test_budget_repository.py -v`

**Commit:** `git commit -m "test: add BudgetRepository unit tests"`

---

## Task 3: Split Transactions Repository Tests

**Files:**
- Create: `tests/backend/unit/repositories/test_split_transactions_repository.py`
- Reference: `backend/repositories/split_transactions_repository.py`

**Tests to write (~10):**

```python
class TestSplitTransactionsRepository:
    """Tests for SplitTransactionsRepository operations."""

    def test_add_split(self, db_session):
        """Verify adding a split returns its ID."""

    def test_get_data_empty(self, db_session):
        """Verify get_data returns empty DataFrame when no splits exist."""

    def test_get_data_with_splits(self, db_session):
        """Verify get_data returns all splits."""

    def test_get_splits_for_transaction(self, db_session):
        """Verify filtering splits by transaction_id and source."""

    def test_update_split(self, db_session):
        """Verify updating split amount/category/tag."""

    def test_delete_split(self, db_session):
        """Verify deleting a single split."""

    def test_delete_all_splits_for_transaction(self, db_session):
        """Verify deleting all splits for a transaction."""

    def test_nullify_category_and_tag(self, db_session):
        """Verify nullifying category and tag across all splits."""

    def test_update_category_for_tag(self, db_session):
        """Verify updating category for a specific tag."""

    def test_nullify_category(self, db_session):
        """Verify nullifying just category."""
```

**Key details:**
- `add_split(transaction_id, source, amount, category, tag)` → returns int split_id
- `source` is the table name string (e.g., "credit_card_transactions")
- Split amounts should be negative (expense convention)

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/repositories/test_split_transactions_repository.py -v`

**Commit:** `git commit -m "test: add SplitTransactionsRepository unit tests"`

---

## Task 4: Tagging Rules Repository Tests

**Files:**
- Create: `tests/backend/unit/repositories/test_tagging_rules_repository.py`
- Reference: `backend/repositories/tagging_rules_repository.py`

**Tests to write (~10):**

```python
class TestTaggingRulesRepository:
    """Tests for TaggingRulesRepository operations."""

    def test_add_rule(self, db_session):
        """Verify adding a tagging rule returns its ID."""

    def test_get_all_rules_empty(self, db_session):
        """Verify get_all_rules returns empty DataFrame when no rules exist."""

    def test_get_all_rules(self, db_session):
        """Verify get_all_rules returns all rules with conditions."""

    def test_get_rule_by_id(self, db_session):
        """Verify retrieving a single rule by ID."""

    def test_get_rule_by_id_not_found(self, db_session):
        """Verify None returned for non-existent ID."""

    def test_update_rule(self, db_session):
        """Verify updating rule fields."""

    def test_delete_rule(self, db_session):
        """Verify deleting a rule by ID."""

    def test_delete_rules_by_category(self, db_session):
        """Verify deleting all rules for a category."""

    def test_delete_rules_by_category_and_tag(self, db_session):
        """Verify deleting rules matching both category and tag."""

    def test_update_category_for_tag(self, db_session):
        """Verify updating category for rules matching a tag."""
```

**Key details:**
- `conditions` is a dict (stored as JSON): `{"operator": "contains", "field": "description", "value": "SUPERMARKET"}`
- `add_rule(name, conditions, category, tag)` → returns int rule_id
- Rules have auto-incrementing priority

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/repositories/test_tagging_rules_repository.py -v`

**Commit:** `git commit -m "test: add TaggingRulesRepository unit tests"`

---

## Task 5: Investments Repository Tests

**Files:**
- Create: `tests/backend/unit/repositories/test_investments_repository.py`
- Reference: `backend/repositories/investments_repository.py`

**Tests to write (~8):**

```python
class TestInvestmentsRepository:
    """Tests for InvestmentsRepository operations."""

    def test_create_investment(self, db_session):
        """Verify creating an investment with all fields."""

    def test_get_all_investments_excludes_closed(self, db_session):
        """Verify get_all_investments excludes closed by default."""

    def test_get_all_investments_includes_closed(self, db_session):
        """Verify include_closed=True returns closed investments."""

    def test_get_by_id(self, db_session):
        """Verify retrieving investment by ID."""

    def test_get_by_category_tag(self, db_session):
        """Verify filtering by category and tag."""

    def test_update_investment(self, db_session):
        """Verify updating investment fields."""

    def test_close_and_reopen_investment(self, db_session):
        """Verify closing sets is_closed and closed_date, reopening clears them."""

    def test_delete_investment(self, db_session):
        """Verify deleting removes the investment."""
```

**Key details:**
- `create_investment(category, tag, type_, name, ...)` — many optional fields
- `close_investment(id, closed_date)` sets `is_closed=True`
- `get_all_investments(include_closed=False)` filters by default

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/repositories/test_investments_repository.py -v`

**Commit:** `git commit -m "test: add InvestmentsRepository unit tests"`

---

## Task 6: Scraping History Repository Tests

**Files:**
- Create: `tests/backend/unit/repositories/test_scraping_history_repository.py`
- Reference: `backend/repositories/scraping_history_repository.py`

**Tests to write (~8):**

```python
class TestScrapingHistoryRepository:
    """Tests for ScrapingHistoryRepository operations."""

    def test_record_scrape_start(self, db_session):
        """Verify recording a scrape start returns an ID."""

    def test_record_scrape_end_success(self, db_session):
        """Verify recording scrape end with success status."""

    def test_record_scrape_end_failed(self, db_session):
        """Verify recording scrape end with failed status and error message."""

    def test_get_scraping_status(self, db_session):
        """Verify getting status by scrape ID."""

    def test_get_error_message(self, db_session):
        """Verify getting error message for failed scrape."""

    def test_get_scraping_history(self, db_session):
        """Verify getting full history as DataFrame."""

    def test_get_last_successful_scrape_date(self, db_session):
        """Verify getting last successful scrape date for an account."""

    def test_get_last_successful_scrape_date_none(self, db_session):
        """Verify None returned when no successful scrapes exist."""
```

**Key details:**
- `record_scrape_start(service_name, provider_name, account_name, start_date, status)` → int
- `record_scrape_end(scrape_id, status, error_message=None)`
- Status constants: `IN_PROGRESS`, `SUCCESS`, `FAILED`, `CANCELED`, `WAITING_FOR_2FA`

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/repositories/test_scraping_history_repository.py -v`

**Commit:** `git commit -m "test: add ScrapingHistoryRepository unit tests"`

---

## Task 7: Transactions Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_transactions_service.py`
- Reference: `backend/services/transactions_service.py`

**What:** Test TransactionsService business logic. Use `db_session` + seed fixtures for tests that need real data. Use mocks for isolation where appropriate.

**Tests to write (~25):**

```python
class TestTransactionsServiceDataRetrieval:
    """Tests for TransactionsService data retrieval methods."""

    def test_get_data_for_analysis_empty_db(self, db_session):
        """Verify empty DataFrame returned when no transactions exist."""

    def test_get_data_for_analysis_merges_sources(self, db_session, seed_base_transactions):
        """Verify data from CC, bank, cash, and manual_investments are merged."""

    def test_get_data_for_analysis_excludes_split_parents(self, db_session, seed_base_transactions, seed_split_transactions):
        """Verify split parent transactions are excluded by default."""

    def test_get_data_for_analysis_includes_split_children(self, db_session, seed_base_transactions, seed_split_transactions):
        """Verify split children appear in analysis data."""

    def test_get_data_for_analysis_includes_prior_wealth(self, db_session, seed_prior_wealth_transactions):
        """Verify bank prior wealth synthetic rows are included."""

    def test_get_table_for_analysis_single_service(self, db_session, seed_base_transactions):
        """Verify filtering by a single service."""

    def test_get_all_transactions_invalid_service(self, db_session):
        """Verify ValueError for invalid service name."""

    def test_get_untagged_transactions(self, db_session, seed_untagged_transactions):
        """Verify only untagged (null category) transactions returned."""

    def test_get_transactions_by_tag(self, db_session, seed_base_transactions):
        """Verify filtering by category and optional tag."""


class TestTransactionsServiceCRUD:
    """Tests for TransactionsService create/update/delete operations."""

    def test_create_cash_transaction(self, db_session):
        """Verify creating a cash transaction."""

    def test_create_manual_investments_transaction(self, db_session):
        """Verify creating a manual investment transaction."""

    def test_create_transaction_invalid_service(self, db_session):
        """Verify ValueError for unsupported service."""

    def test_update_transaction_manual_source(self, db_session):
        """Verify manual sources can edit description/amount/provider."""

    def test_update_transaction_scraped_source_only_tags(self, db_session, seed_base_transactions):
        """Verify scraped sources can only update category/tag."""

    def test_delete_transaction_cash(self, db_session):
        """Verify deleting a cash transaction."""

    def test_delete_transaction_scraped_source_forbidden(self, db_session, seed_base_transactions):
        """Verify PermissionError when deleting non-manual transaction."""

    def test_delete_transaction_protected_tag(self, db_session):
        """Verify PermissionError when deleting Prior Wealth transaction."""

    def test_bulk_tag_transactions(self, db_session, seed_untagged_transactions):
        """Verify bulk tagging updates multiple transactions."""


class TestTransactionsServiceKPIs:
    """Tests for TransactionsService KPI calculations."""

    def test_get_kpis(self, db_session, seed_base_transactions):
        """Verify KPI calculations (income, expenses, savings rate)."""

    def test_split_data_by_category_types(self, db_session, seed_base_transactions):
        """Verify data split into expenses, investments, income, liabilities."""

    def test_get_liabilities_summary(self, db_session, seed_base_transactions):
        """Verify liabilities breakdown by tag."""


class TestTransactionsServicePriorWealth:
    """Tests for prior wealth offset synchronization."""

    def test_sync_prior_wealth_creates_offset(self, db_session):
        """Verify offset transaction created for cash deposits."""

    def test_sync_prior_wealth_updates_existing(self, db_session):
        """Verify existing offset updated when deposits change."""

    def test_sync_prior_wealth_deletes_when_zero(self, db_session):
        """Verify offset deleted when no deposits exist."""
```

**Key details:**
- `TransactionsService(db_session)` — constructor takes a Session
- Transaction amounts: negative = expense, positive = income
- `PROTECTED_TAGS = ["Prior Wealth"]` — cannot delete these
- `sync_prior_wealth_offset()` maintains offset transactions in cash/manual_investments tables
- `get_kpis(df)` calculates: income, expenses, savings_rate, bank_balance_increase, etc.

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_transactions_service.py -v`

**Commit:** `git commit -m "test: add TransactionsService unit tests"`

---

## Task 8: Analysis Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_analysis_service.py`
- Reference: `backend/services/analysis_service.py`

**Tests to write (~20):**

```python
class TestAnalysisServiceOverview:
    """Tests for AnalysisService financial overview."""

    def test_get_overview_with_data(self, db_session, seed_base_transactions):
        """Verify overview returns correct totals."""

    def test_get_overview_with_date_filter(self, db_session, seed_base_transactions):
        """Verify overview respects date range filters."""

    def test_get_overview_empty_db(self, db_session):
        """Verify overview handles empty database."""


class TestAnalysisServiceTimeSeries:
    """Tests for AnalysisService time series data."""

    def test_get_income_expenses_over_time(self, db_session, seed_base_transactions):
        """Verify monthly income/expense breakdown."""

    def test_get_income_expenses_over_time_date_filter(self, db_session, seed_base_transactions):
        """Verify date filtering on time series."""

    def test_get_net_balance_over_time(self, db_session, seed_base_transactions):
        """Verify cumulative balance calculation."""

    def test_get_net_balance_over_time_excludes_cc(self, db_session, seed_base_transactions):
        """Verify credit card transactions excluded from balance (only bank source used)."""

    def test_get_net_balance_over_time_empty(self, db_session):
        """Verify empty list for empty database."""


class TestAnalysisServiceCategories:
    """Tests for AnalysisService category breakdown."""

    def test_get_expenses_by_category(self, db_session, seed_base_transactions):
        """Verify category grouping with expenses and refunds separated."""

    def test_get_expenses_by_category_excludes_non_expenses(self, db_session, seed_base_transactions):
        """Verify Salary, Ignore, Investments excluded from expense breakdown."""

    def test_get_expenses_by_category_empty(self, db_session):
        """Verify empty result for no data."""


class TestAnalysisServiceIncomeExpenses:
    """Tests for income/expense classification logic."""

    def test_get_income_and_expenses(self, db_session, seed_base_transactions):
        """Verify income vs expense calculation."""

    def test_income_mask_includes_salary(self, db_session, seed_base_transactions):
        """Verify Salary category counted as income."""

    def test_income_mask_includes_other_income(self, db_session, seed_base_transactions):
        """Verify Other Income category counted as income."""

    def test_income_mask_liability_positive_is_income(self, db_session):
        """Verify positive Liabilities amounts (loans received) counted as income."""


class TestAnalysisServiceSankey:
    """Tests for Sankey diagram data generation."""

    def test_get_sankey_data_structure(self, db_session, seed_base_transactions):
        """Verify Sankey returns nodes and links."""

    def test_get_sankey_data_includes_prior_wealth(self, db_session, seed_base_transactions, seed_prior_wealth_transactions):
        """Verify Prior Wealth node included from bank balances."""

    def test_get_sankey_data_empty(self, db_session):
        """Verify empty nodes/links for no data."""

    def test_get_sankey_data_excludes_ignore(self, db_session, seed_base_transactions):
        """Verify Ignore category excluded from Sankey."""
```

**Key details:**
- `AnalysisService(db_session)` — uses TransactionsRepository and BankBalanceRepository
- `get_income_and_expenses(df)` excludes `credit_card_transactions` source to avoid double-counting
- Income mask: Salary, Other Income categories + positive Liabilities amounts
- Sankey diagram: Sources → "Total Income" node → Destinations

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_analysis_service.py -v`

**Commit:** `git commit -m "test: add AnalysisService unit tests"`

---

## Task 9: Budget Service Tests (Monthly + Project)

**Files:**
- Modify: `tests/backend/unit/services/test_budget_service.py` (add to existing file)
- Reference: `backend/services/budget_service.py`

**What:** Add tests for BudgetService, MonthlyBudgetService, and ProjectBudgetService. The file already has 1 test for ProjectBudgetService — add more.

**Tests to write (~20, on top of existing 1):**

```python
class TestBudgetServiceBase:
    """Tests for BudgetService base functionality."""

    def test_get_all_rules_parses_tags(self, db_session, seed_budget_rules):
        """Verify tags are parsed from semicolon-separated strings to lists."""

    def test_add_rule_converts_tags_list(self, db_session):
        """Verify tags list is joined with semicolons before storage."""

    def test_update_rule_valid_fields(self, db_session, seed_budget_rules):
        """Verify update accepts name, amount, category, tags."""

    def test_update_rule_invalid_field_raises(self, db_session, seed_budget_rules):
        """Verify AssertionError for invalid field names."""

    def test_validate_rule_inputs_empty_name(self, db_session):
        """Verify validation rejects empty name."""

    def test_validate_rule_inputs_zero_amount(self, db_session):
        """Verify validation rejects zero amount."""

    def test_validate_rule_inputs_duplicate_name(self, db_session, seed_budget_rules):
        """Verify validation rejects duplicate names in same month."""

    def test_validate_rule_inputs_exceeds_total(self, db_session, seed_budget_rules):
        """Verify validation rejects when rules exceed total budget."""


class TestMonthlyBudgetService:
    """Tests for MonthlyBudgetService functionality."""

    def test_get_all_rules_monthly_only(self, db_session, seed_budget_rules):
        """Verify only monthly rules returned (not project rules)."""

    def test_get_month_rules(self, db_session, seed_budget_rules):
        """Verify filtering rules by year and month."""

    def test_create_rule_with_validation(self, db_session, seed_budget_rules):
        """Verify create_rule validates before adding."""

    def test_copy_last_month_rules(self, db_session, seed_budget_rules):
        """Verify rules copied from previous month."""

    def test_copy_last_month_rules_none_when_empty(self, db_session):
        """Verify None returned when previous month has no rules."""

    def test_get_monthly_budget_view(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify budget view computes current_amount per rule."""

    def test_get_monthly_budget_view_other_expenses(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify 'Other Expenses' catch-all created for unmatched transactions."""

    def test_get_monthly_analysis(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify full analysis includes rules, project spending, pending refunds."""

    def test_delete_rules_by_month(self, db_session, seed_budget_rules):
        """Verify all rules for a month are deleted."""


class TestProjectBudgetService:
    """Tests for ProjectBudgetService functionality."""

    # Existing test: test_get_project_budget_view_with_unmatched_transactions

    def test_create_project(self, db_session):
        """Verify creating a project creates total budget + tag rules."""

    def test_get_all_projects_names(self, db_session, seed_project_transactions):
        """Verify project names list."""

    def test_delete_project(self, db_session, seed_project_transactions):
        """Verify deleting removes all project rules."""

    def test_get_project_transactions(self, db_session, seed_project_transactions):
        """Verify filtering transactions by project category."""
```

**Key details:**
- `MonthlyBudgetService(db_session)` — filters rules where year/month are NOT null
- `ProjectBudgetService(db_session)` — filters rules where year/month ARE null
- `get_monthly_budget_view()` creates "Other Expenses" catch-all for unmatched transactions
- Budget view returns list of `{"rule": {...}, "current_amount": float, "data": [...], "allow_edit": bool, "allow_delete": bool}`
- The `CategoriesTagsService()` is used internally — may need mock or real categories YAML fixture

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_budget_service.py -v`

**Commit:** `git commit -m "test: add Budget service unit tests (monthly + project)"`

---

## Task 10: Categories Tags Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_categories_tags_service.py`
- Reference: `backend/services/tagging_service.py`

**Tests to write (~15):**

```python
class TestCategoriesTagsServiceRead:
    """Tests for CategoriesTagsService read operations."""

    def test_get_categories_and_tags(self, db_session, monkeypatch, sample_categories_yaml):
        """Verify categories loaded from YAML."""

    def test_get_categories_and_tags_copy(self, db_session, monkeypatch, sample_categories_yaml):
        """Verify copy=True returns a deep copy."""

    def test_get_categories_icons(self, db_session, monkeypatch):
        """Verify icons loaded."""


class TestCategoriesTagsServiceCategories:
    """Tests for category management."""

    def test_add_category(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify adding a new category."""

    def test_add_category_duplicate_rejected(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify duplicate category name returns False."""

    def test_add_category_empty_name_rejected(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify empty name returns False."""

    def test_add_category_title_case(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify category name normalized to title case."""

    def test_delete_category(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify deleting a category nullifies transactions and removes rules."""

    def test_delete_category_protected(self, db_session, monkeypatch, sample_categories_yaml):
        """Verify protected categories cannot be deleted."""


class TestCategoriesTagsServiceTags:
    """Tests for tag management."""

    def test_add_tag(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify adding a tag to a category."""

    def test_add_tag_duplicate_rejected(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify duplicate tag returns False."""

    def test_delete_tag(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify deleting a tag nullifies transactions."""

    def test_reallocate_tag(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify moving a tag between categories updates DB and YAML."""

    def test_reallocate_tag_invalid_category(self, db_session, monkeypatch, sample_categories_yaml):
        """Verify False returned for non-existent category."""

    def test_add_new_credit_card_tags(self, db_session, monkeypatch, sample_categories_yaml, tmp_path):
        """Verify CC account tags added to Credit Cards category."""
```

**Key details:**
- CategoriesTagsService uses a global `_categories_cache` — use `monkeypatch` to reset it between tests
- `monkeypatch.setattr("backend.services.tagging_service._categories_cache", None)` before each test
- Mock `TaggingRepository.get_categories` to return `sample_categories_yaml`
- Mock `TaggingRepository.save_categories_to_file` to write to `tmp_path`
- Protected categories: "Credit Cards", "Salary", "Other Income", "Investments", "Ignore", "Liabilities"

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_categories_tags_service.py -v`

**Commit:** `git commit -m "test: add CategoriesTagsService unit tests"`

---

## Task 11: Credentials Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_credentials_service.py`
- Reference: `backend/services/credentials_service.py`

**Tests to write (~10):**

```python
class TestCredentialsService:
    """Tests for CredentialsService operations."""

    def test_load_credentials(self, monkeypatch, sample_credentials_yaml):
        """Verify credentials loaded from YAML with keyring passwords."""

    def test_generate_keyring_key(self):
        """Verify keyring key format: service:provider:account:field."""

    def test_get_available_data_sources(self, monkeypatch, sample_credentials_yaml):
        """Verify data sources list format."""

    def test_get_data_sources_credentials_filters(self, monkeypatch, sample_credentials_yaml):
        """Verify filtering credentials by selected data sources."""

    def test_save_credentials_stores_passwords_in_keyring(self, monkeypatch, tmp_path):
        """Verify passwords extracted to keyring and cleared from YAML."""

    def test_delete_account(self, monkeypatch, sample_credentials_yaml, tmp_path):
        """Verify account removed from credentials."""

    def test_get_safe_credentials_no_passwords(self, monkeypatch, sample_credentials_yaml):
        """Verify safe credentials contain no password fields."""

    def test_get_accounts_list(self, monkeypatch, sample_credentials_yaml):
        """Verify flat list of accounts."""

    def test_get_available_providers(self, monkeypatch):
        """Verify providers filtered by test mode."""

    def test_delete_credential_cleans_keyring(self, monkeypatch, sample_credentials_yaml, tmp_path):
        """Verify keyring entries deleted on credential removal."""
```

**Key details:**
- CredentialsService uses `CredentialsRepository()` (singleton) — mock it with monkeypatch
- Clear `_credentials_cache` between tests
- Mock `keyring.get_password` / `keyring.set_password` via the repository's methods
- `get_safe_credentials()` strips passwords, returns only provider/account structure

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_credentials_service.py -v`

**Commit:** `git commit -m "test: add CredentialsService unit tests"`

---

## Task 12: Investments Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_investments_service.py`
- Reference: `backend/services/investments_service.py`

**Tests to write (~10):**

```python
class TestInvestmentsServiceCRUD:
    """Tests for InvestmentsService CRUD operations."""

    def test_create_investment(self, db_session):
        """Verify creating an investment."""

    def test_get_all_investments(self, db_session, seed_investments):
        """Verify listing investments as dict list."""

    def test_get_investment_by_id(self, db_session, seed_investments):
        """Verify retrieving single investment."""

    def test_close_and_reopen(self, db_session, seed_investments):
        """Verify close sets balance to 0, reopen restores."""

    def test_delete_investment(self, db_session, seed_investments):
        """Verify deletion."""


class TestInvestmentsServiceCalculations:
    """Tests for InvestmentsService financial calculations."""

    def test_calculate_current_balance(self, db_session, seed_investments):
        """Verify balance = -(sum of transactions)."""

    def test_calculate_profit_loss(self, db_session, seed_investments):
        """Verify deposits, withdrawals, ROI calculation."""

    def test_calculate_balance_over_time(self, db_session, seed_investments):
        """Verify daily balance series."""

    def test_get_portfolio_overview(self, db_session, seed_investments):
        """Verify portfolio totals and allocation."""

    def test_get_portfolio_overview_empty(self, db_session):
        """Verify empty portfolio returns zeros."""
```

**Key details:**
- Transaction sign for investments: negative = deposit (money out), positive = withdrawal (money in)
- Balance = -(sum of all transactions) — if deposited -1000, balance = +1000
- ROI = (final_value / total_deposits - 1) * 100
- Closed investments have balance 0

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_investments_service.py -v`

**Commit:** `git commit -m "test: add InvestmentsService unit tests"`

---

## Task 13: Scraping Service Tests

**Files:**
- Create: `tests/backend/unit/services/test_scraping_service.py`
- Reference: `backend/services/scraping_service.py`

**Tests to write (~15):**

```python
class TestScrapingServiceStatus:
    """Tests for ScrapingService status operations."""

    def test_get_scraping_status(self, db_session):
        """Verify status retrieval by process ID."""

    def test_get_scraping_status_unknown(self, db_session):
        """Verify 'unknown' status for non-existent process."""

    def test_get_last_scrape_dates(self, db_session, monkeypatch):
        """Verify last scrape dates for all accounts."""


class TestScrapingServiceStart:
    """Tests for starting scrape operations."""

    def test_start_scraping_single(self, db_session, monkeypatch):
        """Verify scraping starts in background thread."""

    def test_start_scraping_creates_history(self, db_session, monkeypatch):
        """Verify scraping history record created."""

    def test_start_scraping_2fa_adds_to_waiting(self, db_session, monkeypatch):
        """Verify 2FA scraper added to _tfa_scrapers_waiting dict."""


class TestScrapingService2FA:
    """Tests for 2FA flow."""

    def test_submit_2fa_code(self, db_session, monkeypatch):
        """Verify OTP code forwarded to scraper."""

    def test_submit_2fa_code_not_found(self, db_session):
        """Verify EntityNotFoundException for unknown scraper."""


class TestScrapingServiceAbort:
    """Tests for aborting scrape operations."""

    def test_abort_scraping_process(self, db_session, monkeypatch):
        """Verify abort marks process as failed."""

    def test_abort_2fa_scraper(self, db_session, monkeypatch):
        """Verify abort sends CANCEL to 2FA scraper."""
```

**Key details:**
- Mock `get_scraper()` to avoid creating real scrapers
- Mock `CredentialsRepository().get_credentials()` and `list_accounts()`
- Mock `Thread` to avoid background execution
- `_tfa_scrapers_waiting` is a module-level dict — monkeypatch to control it
- `is_2fa_required(service, provider)` — separate function, can be tested directly

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/services/test_scraping_service.py -v`

**Commit:** `git commit -m "test: add ScrapingService unit tests"`

---

## Task 14: Scraper Base & Parsing Tests

**Files:**
- Create: `tests/backend/unit/scraper/test_scraper_base.py`
- Create: `tests/backend/unit/scraper/test_scraper_parsing.py`
- Reference: `backend/scraper/scrapers.py`

**Tests for test_scraper_base.py (~12):**

```python
class TestGetScraper:
    """Tests for the get_scraper factory function."""

    def test_get_credit_card_scraper(self):
        """Verify correct scraper returned for credit card provider."""

    def test_get_bank_scraper(self):
        """Verify correct scraper returned for bank provider."""

    def test_get_dummy_regular_scraper(self):
        """Verify DummyRegularScraper returned for test_bank."""

    def test_get_dummy_tfa_scraper(self):
        """Verify DummyTFAScraper returned for test_bank_2fa."""

    def test_get_scraper_unsupported_raises(self):
        """Verify ValueError for unsupported service."""


class TestIs2FARequired:
    """Tests for is_2fa_required function."""

    def test_onezero_requires_2fa(self):
        """Verify OneZero bank requires 2FA."""

    def test_test_bank_no_2fa(self):
        """Verify test_bank does not require 2FA."""

    def test_test_bank_2fa_requires_2fa(self):
        """Verify test_bank_2fa requires 2FA."""


class TestScraperBaseAttributes:
    """Tests for Scraper base class initialization and attributes."""

    def test_scraper_init(self):
        """Verify scraper initializes with account_name, credentials, process_id."""

    def test_scraper_cancel_constant(self):
        """Verify CANCEL constant is 'cancel'."""

    def test_set_otp_code(self):
        """Verify set_otp_code sets code and signals event."""

    def test_is_waiting_for_otp(self):
        """Verify is_waiting_for_otp checks code value."""
```

**Tests for test_scraper_parsing.py (~10):**

Read the scraper's `_parse_output`, `_handle_error`, and data transformation methods, then write tests:

```python
class TestScraperErrorMapping:
    """Tests for error type mapping from Node.js stderr."""

    def test_credentials_error(self):
        """Verify INVALID_PASSWORD maps to CredentialsError."""

    def test_connection_error(self):
        """Verify GENERIC maps to ConnectionError."""

    def test_timeout_error(self):
        """Verify TIMEOUT maps to TimeoutError."""

    def test_unknown_error(self):
        """Verify unknown error type handled gracefully."""
```

**Key details:**
- Use `DummyRegularScraper` or `DummyTFAScraper` as concrete test subjects
- `get_scraper(service_name, provider_name, account_name, credentials, start_date, process_id)`
- `Scraper.set_otp_code(code)` sets `self.otp_code` and `self.otp_event.set()`
- Error hierarchy in `backend/scraper/exceptions.py`

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/scraper/ -v`

**Commit:** `git commit -m "test: add Scraper unit tests (base, parsing, 2FA)"`

---

## Task 15: Scraper 2FA Tests

**Files:**
- Create: `tests/backend/unit/scraper/test_scraper_2fa.py`
- Reference: `backend/scraper/scrapers.py`

**Tests to write (~8):**

```python
class TestScraper2FA:
    """Tests for Scraper 2FA (Two-Factor Authentication) flow."""

    def test_otp_event_initially_unset(self):
        """Verify OTP event starts unset."""

    def test_set_otp_code_sets_event(self):
        """Verify set_otp_code triggers the event."""

    def test_set_otp_code_stores_code(self):
        """Verify OTP code stored on scraper instance."""

    def test_cancel_sets_cancel_constant(self):
        """Verify 'cancel' string triggers cancellation."""

    def test_is_waiting_for_otp_true(self):
        """Verify waiting state when code is 'waiting for input'."""

    def test_is_waiting_for_otp_false(self):
        """Verify not waiting after code is set."""

    def test_requires_2fa_attribute(self):
        """Verify requires_2fa is True for 2FA scrapers."""

    def test_requires_2fa_false_for_regular(self):
        """Verify requires_2fa is False for regular scrapers."""
```

**Key details:**
- Use `DummyTFAScraper` for 2FA tests, `DummyRegularScraper` for non-2FA
- `otp_event` is a `threading.Event`
- `is_waiting_for_otp` checks `self.otp_code == "waiting for input"`

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/unit/scraper/test_scraper_2fa.py -v`

**Commit:** `git commit -m "test: add Scraper 2FA unit tests"`

---

## Task 16: Integration — Tagging Pipeline

**Files:**
- Create: `tests/backend/integration/test_tagging_pipeline.py`
- Reference: `backend/services/tagging_rules_service.py`, `backend/repositories/tagging_rules_repository.py`

**Tests to write (~10):**

```python
class TestTaggingPipeline:
    """Integration tests for the full tagging pipeline: rules → transactions → auto-tag."""

    def test_create_rule_and_apply(self, db_session, seed_untagged_transactions):
        """Verify creating a rule and applying it tags matching transactions."""

    def test_priority_ordering(self, db_session, seed_untagged_transactions):
        """Verify higher priority rules match first."""

    def test_rule_does_not_overwrite_existing_tags(self, db_session, seed_base_transactions):
        """Verify rules skip already-tagged transactions by default."""

    def test_rule_overwrite_mode(self, db_session, seed_base_transactions):
        """Verify overwrite=True re-tags all matching transactions."""

    def test_contains_operator(self, db_session, seed_untagged_transactions):
        """Verify 'contains' operator matches substring in description."""

    def test_delete_rule_does_not_untag(self, db_session, seed_untagged_transactions):
        """Verify deleting a rule doesn't remove existing tags from transactions."""

    def test_multiple_rules_different_categories(self, db_session, seed_untagged_transactions):
        """Verify each untagged transaction gets the correct category from its matching rule."""

    def test_update_rule_conditions(self, db_session, seed_untagged_transactions):
        """Verify updating conditions changes which transactions match."""

    def test_preview_rule(self, db_session, seed_untagged_transactions):
        """Verify preview returns matching transactions without applying."""

    def test_validate_rule_conflict(self, db_session, seed_untagged_transactions):
        """Verify conflict detection between overlapping rules."""
```

**Key details:**
- `TaggingRulesService(db_session)` — orchestrates rules + transactions
- `add_rule(name, conditions, category, tag)` → creates rule AND applies it
- `apply_rules(overwrite=False)` → applies all active rules
- `preview_rule(conditions, limit)` → returns matching transactions without tagging
- Conditions format: `{"operator": "AND", "children": [{"field": "description", "operator": "contains", "value": "SUPERMARKET"}]}`

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/integration/test_tagging_pipeline.py -v`

**Commit:** `git commit -m "test: add tagging pipeline integration tests"`

---

## Task 17: Integration — Budget Pipeline

**Files:**
- Create: `tests/backend/integration/test_budget_pipeline.py`
- Reference: `backend/services/budget_service.py`

**Tests to write (~10):**

```python
class TestBudgetPipeline:
    """Integration tests for budget rules + transactions → analysis."""

    def test_monthly_budget_vs_actual(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify budget view shows correct spent amounts per rule."""

    def test_total_budget_calculation(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify Total Budget rule sums all expenses."""

    def test_other_expenses_catch_all(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify unmatched expenses appear in 'Other Expenses'."""

    def test_project_budget_view(self, db_session, seed_project_transactions):
        """Verify project budget aggregation by tag."""

    def test_project_unmatched_auto_creates_rules(self, db_session, seed_project_transactions):
        """Verify unmatched tags auto-create budget rules in project."""

    def test_copy_month_rules(self, db_session, seed_budget_rules):
        """Verify rules copied from month N to month N+1."""

    def test_budget_excludes_non_expenses(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify Salary, Ignore etc. excluded from budget calculations."""

    def test_budget_excludes_project_transactions(self, db_session, seed_budget_rules, seed_base_transactions, seed_project_transactions):
        """Verify project transactions excluded from monthly budget."""

    def test_split_transaction_amounts_in_budget(self, db_session, seed_budget_rules, seed_base_transactions, seed_split_transactions):
        """Verify split children counted correctly, parents excluded."""

    def test_pending_refunds_excluded(self, db_session, seed_budget_rules, seed_base_transactions):
        """Verify pending refund transactions excluded from budget view."""
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/integration/test_budget_pipeline.py -v`

**Commit:** `git commit -m "test: add budget pipeline integration tests"`

---

## Task 18: Integration — Split Transactions Pipeline

**Files:**
- Create: `tests/backend/integration/test_split_transactions_pipeline.py`

**Tests to write (~6):**

```python
class TestSplitTransactionsPipeline:
    """Integration tests for split transaction lifecycle."""

    def test_split_transaction(self, db_session, seed_base_transactions):
        """Verify splitting a transaction creates children and marks parent."""

    def test_split_children_in_analysis(self, db_session, seed_base_transactions):
        """Verify split children appear in analysis data."""

    def test_split_parent_excluded_from_analysis(self, db_session, seed_base_transactions):
        """Verify split parent excluded when include_split_parents=False."""

    def test_revert_split(self, db_session, seed_base_transactions):
        """Verify reverting deletes children and restores parent."""

    def test_split_amounts_sum_to_parent(self, db_session, seed_base_transactions):
        """Verify split child amounts sum to parent amount."""

    def test_split_children_independent_categories(self, db_session, seed_base_transactions):
        """Verify each split child can have different category/tag."""
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/integration/test_split_transactions_pipeline.py -v`

**Commit:** `git commit -m "test: add split transactions pipeline integration tests"`

---

## Task 19: Route Tests — Transactions

**Files:**
- Create: `tests/backend/routes/conftest.py`
- Create: `tests/backend/routes/test_transactions_routes.py`
- Reference: `backend/routes/transactions.py`, `backend/main.py`

**What:** Create route test infrastructure and transaction endpoint tests.

**`tests/backend/routes/conftest.py`:**
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.dependencies import get_database
from backend.models.base import Base


@pytest.fixture(scope="function")
def test_client(db_session):
    """FastAPI TestClient with overridden database dependency."""
    def override_get_database():
        yield db_session

    app.dependency_overrides[get_database] = override_get_database
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
```

**Tests to write (~12):**

```python
class TestTransactionsRoutes:
    """Tests for transaction API endpoints."""

    def test_get_transactions(self, test_client, seed_base_transactions):
        """GET /api/transactions returns 200 with transaction list."""

    def test_get_transactions_filter_service(self, test_client, seed_base_transactions):
        """GET /api/transactions?service=credit_cards filters correctly."""

    def test_create_cash_transaction(self, test_client):
        """POST /api/transactions creates cash transaction."""

    def test_create_transaction_invalid_service(self, test_client):
        """POST /api/transactions with invalid service returns 400."""

    def test_update_transaction(self, test_client, seed_base_transactions):
        """PUT /api/transactions/{id} updates transaction."""

    def test_delete_cash_transaction(self, test_client):
        """DELETE /api/transactions/{id} deletes cash transaction."""

    def test_delete_scraped_transaction_forbidden(self, test_client, seed_base_transactions):
        """DELETE /api/transactions/{id} for scraped source returns 403."""

    def test_split_transaction(self, test_client, seed_base_transactions):
        """POST /api/transactions/{id}/split creates splits."""

    def test_revert_split(self, test_client, seed_base_transactions, seed_split_transactions):
        """DELETE /api/transactions/{id}/split reverts split."""

    def test_bulk_tag(self, test_client, seed_untagged_transactions):
        """POST /api/transactions/bulk-tag tags multiple transactions."""

    def test_get_transaction_by_id(self, test_client, seed_base_transactions):
        """GET /api/transactions/{id} returns single transaction."""

    def test_get_transaction_not_found(self, test_client):
        """GET /api/transactions/99999 returns 404."""
```

**Key details:**
- Router prefix from main.py — check `app.include_router(transactions.router, prefix="/api/transactions")`
- TestClient needs `app.dependency_overrides[get_database]` to inject test db_session
- Also override `get_db` from `backend.database` if pending_refunds routes use it directly

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/routes/test_transactions_routes.py -v`

**Commit:** `git commit -m "test: add transaction route tests with TestClient infrastructure"`

---

## Task 20: Route Tests — Budget

**Files:**
- Create: `tests/backend/routes/test_budget_routes.py`
- Reference: `backend/routes/budget.py`

**Tests to write (~10):**

```python
class TestBudgetRoutes:
    """Tests for budget API endpoints."""

    def test_get_budget_rules(self, test_client, seed_budget_rules):
        """GET /api/budget/rules returns all rules."""

    def test_get_budget_rules_by_month(self, test_client, seed_budget_rules):
        """GET /api/budget/rules/2024/1 returns monthly rules."""

    def test_create_budget_rule(self, test_client, seed_budget_rules):
        """POST /api/budget/rules creates a rule."""

    def test_create_budget_rule_invalid(self, test_client, seed_budget_rules):
        """POST /api/budget/rules with invalid data returns 400."""

    def test_update_budget_rule(self, test_client, seed_budget_rules):
        """PUT /api/budget/rules/{id} updates a rule."""

    def test_delete_budget_rule(self, test_client, seed_budget_rules):
        """DELETE /api/budget/rules/{id} deletes a rule."""

    def test_get_monthly_analysis(self, test_client, seed_budget_rules, seed_base_transactions):
        """GET /api/budget/analysis/2024/1 returns analysis."""

    def test_get_projects(self, test_client, seed_project_transactions):
        """GET /api/budget/projects returns project names."""

    def test_create_project(self, test_client):
        """POST /api/budget/projects creates a project."""

    def test_get_project_details(self, test_client, seed_project_transactions):
        """GET /api/budget/projects/{name} returns project view."""
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/routes/test_budget_routes.py -v`

**Commit:** `git commit -m "test: add budget route tests"`

---

## Task 21: Route Tests — Tagging & Tagging Rules

**Files:**
- Create: `tests/backend/routes/test_tagging_routes.py`
- Create: `tests/backend/routes/test_tagging_rules_routes.py`

**Tagging tests (~8):**

```python
class TestTaggingRoutes:
    """Tests for category and tag management endpoints."""

    def test_get_categories(self, test_client):
    def test_add_category(self, test_client):
    def test_delete_category(self, test_client):
    def test_create_tag(self, test_client):
    def test_delete_tag(self, test_client):
    def test_relocate_tag(self, test_client):
    def test_get_category_icons(self, test_client):
    def test_update_category_icon(self, test_client):
```

**Tagging rules tests (~8):**

```python
class TestTaggingRulesRoutes:
    """Tests for tagging rule endpoints."""

    def test_get_tagging_rules(self, test_client, seed_tagging_rules):
    def test_create_tagging_rule(self, test_client, seed_untagged_transactions):
    def test_update_tagging_rule(self, test_client, seed_tagging_rules):
    def test_delete_tagging_rule(self, test_client, seed_tagging_rules):
    def test_apply_all_rules(self, test_client, seed_tagging_rules, seed_untagged_transactions):
    def test_validate_rule_conflicts(self, test_client, seed_tagging_rules):
    def test_preview_rule(self, test_client, seed_untagged_transactions):
    def test_delete_nonexistent_rule(self, test_client):
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/routes/test_tagging_routes.py tests/backend/routes/test_tagging_rules_routes.py -v`

**Commit:** `git commit -m "test: add tagging and tagging rules route tests"`

---

## Task 22: Route Tests — Analytics

**Files:**
- Create: `tests/backend/routes/test_analytics_routes.py`
- Reference: `backend/routes/analytics.py`

**Tests to write (~8):**

```python
class TestAnalyticsRoutes:
    """Tests for analytics API endpoints."""

    def test_get_overview(self, test_client, seed_base_transactions):
    def test_get_overview_date_filter(self, test_client, seed_base_transactions):
    def test_get_net_balance_over_time(self, test_client, seed_base_transactions):
    def test_get_income_expenses_over_time(self, test_client, seed_base_transactions):
    def test_get_expenses_by_category(self, test_client, seed_base_transactions):
    def test_get_sankey_data(self, test_client, seed_base_transactions):
    def test_get_overview_empty(self, test_client):
    def test_get_sankey_empty(self, test_client):
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/routes/test_analytics_routes.py -v`

**Commit:** `git commit -m "test: add analytics route tests"`

---

## Task 23: Route Tests — Remaining (Scraping, Credentials, Investments, Bank Balances, Pending Refunds)

**Files:**
- Create: `tests/backend/routes/test_scraping_routes.py`
- Create: `tests/backend/routes/test_credentials_routes.py`
- Create: `tests/backend/routes/test_investments_routes.py`
- Create: `tests/backend/routes/test_bank_balance_routes.py`
- Create: `tests/backend/routes/test_pending_refunds_routes.py`

**Scraping routes (~5):**
```python
class TestScrapingRoutes:
    def test_start_scraping(self, test_client, monkeypatch):
    def test_get_scraping_status(self, test_client):
    def test_submit_2fa(self, test_client, monkeypatch):
    def test_abort_scraping(self, test_client, monkeypatch):
    def test_get_last_scrapes(self, test_client, monkeypatch):
```

**Credentials routes (~8):**
```python
class TestCredentialsRoutes:
    def test_get_credentials(self, test_client, monkeypatch):
    def test_get_accounts(self, test_client, monkeypatch):
    def test_create_credential(self, test_client, monkeypatch):
    def test_get_providers(self, test_client, monkeypatch):
    def test_get_provider_fields(self, test_client):
    def test_delete_credential(self, test_client, monkeypatch):
    def test_get_credential_details(self, test_client, monkeypatch):
    def test_delete_credential_not_found(self, test_client, monkeypatch):
```

**Investments routes (~8):**
```python
class TestInvestmentsRoutes:
    def test_get_investments(self, test_client, seed_investments):
    def test_create_investment(self, test_client):
    def test_get_investment_by_id(self, test_client, seed_investments):
    def test_update_investment(self, test_client, seed_investments):
    def test_close_investment(self, test_client, seed_investments):
    def test_reopen_investment(self, test_client, seed_investments):
    def test_delete_investment(self, test_client, seed_investments):
    def test_get_portfolio_analysis(self, test_client, seed_investments):
```

**Bank balance routes (~4):**
```python
class TestBankBalanceRoutes:
    def test_get_bank_balances(self, test_client):
    def test_set_bank_balance(self, test_client):
    def test_set_bank_balance_update_existing(self, test_client):
    def test_get_bank_balances_empty(self, test_client):
```

**Pending refunds routes (~7):**
```python
class TestPendingRefundsRoutes:
    def test_create_pending_refund(self, test_client):
    def test_get_all_pending_refunds(self, test_client):
    def test_get_pending_refund_by_id(self, test_client):
    def test_cancel_pending_refund(self, test_client):
    def test_link_refund(self, test_client):
    def test_get_budget_adjustment(self, test_client):
    def test_unlink_refund(self, test_client):
```

**Important note for scraping and credentials routes:** These services use module-level singletons and global state. Use `monkeypatch` to mock:
- `ScrapingService.start_scraping_single` — mock to avoid real subprocess
- `CredentialsRepository._instance` — reset singleton between tests
- `_credentials_cache` and `_categories_cache` — clear between tests

**Note for pending refunds routes:** These use `get_db` directly (not `get_database`). Override both:
```python
from backend.database import get_db
app.dependency_overrides[get_db] = override_get_database
```

**Run:** `source .venv/bin/activate && python -m pytest tests/backend/routes/ -v`

**Commit:** `git commit -m "test: add remaining route tests (scraping, credentials, investments, bank balances, pending refunds)"`

---

## Task 24: Final Verification & Cleanup

**Step 1: Run entire test suite**
```bash
source .venv/bin/activate && python -m pytest tests/ -v --tb=short 2>&1 | tail -50
```

**Step 2: Check coverage report**
```bash
source .venv/bin/activate && python -m pytest tests/backend/ --cov=backend --cov-report=term-missing 2>&1 | tail -40
```

**Step 3: Fix any failures**

**Step 4: Final commit**
```bash
git add tests/
git commit -m "test: complete test suite — verify all tests pass"
```

---

## Execution Order

Tasks can be parallelized as follows:

**Sequential dependencies:**
- Task 1 (fixtures) MUST complete before all other tasks
- Tasks 19-23 (routes) depend on Task 19 (route conftest)

**Parallel groups after Task 1:**
- Group A (repositories): Tasks 2, 3, 4, 5, 6
- Group B (services): Tasks 7, 8, 9, 10, 11, 12, 13
- Group C (scrapers): Tasks 14, 15
- Group D (integration): Tasks 16, 17, 18
- Group E (routes): Tasks 19 → 20, 21, 22, 23

**Recommended order for single-threaded execution:**
1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23 → 24
