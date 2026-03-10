# Test Suite Design — Finance Analysis Backend

## Approach

Bottom-up layer testing: repositories first, then services, then routes. Each layer mocks the layer below it for unit tests. Integration tests verify cross-layer behavior with a real in-memory SQLite database.

## Test Infrastructure

### Database Fixtures (in `tests/conftest.py`)

- `db_engine` — In-memory SQLite with all tables, function-scoped
- `db_session` — SQLAlchemy session with rollback on teardown

### Composable Transaction Seed Fixtures (~60-80 transactions)

Located in `tests/backend/conftest.py`:

| Fixture | Transactions | Purpose |
|---------|-------------|---------|
| `seed_base_transactions` | ~30 | 3 months of CC + bank + cash txns across Food, Transport, Entertainment, Salary, Ignore categories |
| `seed_split_transactions` | ~6 | Parent txns + splits across categories |
| `seed_prior_wealth_transactions` | ~4 | Offset transactions for cash/manual_investments |
| `seed_untagged_transactions` | ~8 | Transactions with no category/tag for tagging rule tests |
| `seed_cc_bank_matching_transactions` | ~6 | Duplicate-looking CC and bank transactions |
| `seed_project_transactions` | ~10 | Tagged for Wedding/Renovation projects |

Each fixture inserts ORM records into the in-memory DB via `db_session`. Tests compose what they need:

```python
def test_monthly_summary(self, db_session, seed_base_transactions, seed_split_transactions):
    ...
```

### YAML Fixtures

- `sample_categories_yaml` — Categories/tags hierarchy dict
- `sample_credentials_yaml` — Fake provider credentials (no real passwords)

## Directory Structure

```
tests/
├── conftest.py                          # db_engine, db_session
├── backend/
│   ├── conftest.py                      # Seed fixtures, YAML fixtures
│   ├── unit/
│   │   ├── models/                      # ORM model tests
│   │   ├── repositories/               # Repository tests (mock DB or in-memory)
│   │   │   ├── test_transactions_repository.py
│   │   │   ├── test_budget_repository.py
│   │   │   ├── test_split_transactions_repository.py
│   │   │   ├── test_tagging_rules_repository.py
│   │   │   ├── test_investments_repository.py
│   │   │   ├── test_scraping_history_repository.py
│   │   │   ├── test_bank_balance_repository.py
│   │   │   └── test_pending_refunds_repository.py
│   │   ├── services/                    # Service tests (mock repos)
│   │   │   ├── test_transactions_service.py
│   │   │   ├── test_budget_service.py
│   │   │   ├── test_tagging_rules_service.py
│   │   │   ├── test_categories_tags_service.py
│   │   │   ├── test_analysis_service.py
│   │   │   ├── test_scraping_service.py
│   │   │   ├── test_credentials_service.py
│   │   │   ├── test_investments_service.py
│   │   │   ├── test_bank_balance_service.py
│   │   │   └── test_pending_refunds_service.py
│   │   └── scraper/                     # Scraper unit tests (mock subprocess)
│   │       ├── test_scraper_base.py
│   │       ├── test_scraper_parsing.py
│   │       └── test_scraper_2fa.py
│   ├── integration/                     # Cross-layer with real in-memory DB
│   │   ├── test_tagging_pipeline.py
│   │   ├── test_budget_pipeline.py
│   │   ├── test_split_transactions_pipeline.py
│   │   └── test_scraper_integration.py
│   └── routes/                          # FastAPI TestClient tests
│       ├── test_transactions_routes.py
│       ├── test_budget_routes.py
│       ├── test_tagging_routes.py
│       ├── test_analysis_routes.py
│       ├── test_scraping_routes.py
│       ├── test_credentials_routes.py
│       ├── test_investments_routes.py
│       ├── test_bank_balance_routes.py
│       ├── test_pending_refunds_routes.py
│       ├── test_categories_routes.py
│       └── test_split_transactions_routes.py
```

## Test Counts (Estimated)

| Layer | Files | Tests |
|-------|-------|-------|
| Unit — Repositories | 8 | ~80 |
| Unit — Services | 10 | ~150 |
| Unit — Scrapers | 3 | ~30 |
| Integration | 4 | ~32 |
| Routes | 11 | ~91 |
| **Total** | **~36 new files** | **~383 new tests** |

Plus ~97 existing tests that already pass.

## Unit Tests — Repositories (~80 tests)

Each repository gets CRUD coverage plus edge cases.

**TransactionsRepository** (~15 tests): delegation to sub-repos (CC, bank, cash, manual_investments), get_all merging, date filtering, category/tag operations.

**BudgetRepository** (~12 tests): CRUD for monthly and project rules, get by category, tags semicolon storage/retrieval, update amounts.

**SplitTransactionsRepository** (~10 tests): create splits, get by parent, delete cascading, total validation.

**TaggingRulesRepository** (~10 tests): CRUD, priority ordering, conditions JSON storage, bulk operations.

**InvestmentsRepository** (~8 tests): portfolio CRUD, balance updates, get by provider.

**ScrapingHistoryRepository** (~8 tests): log entries, daily rate limit check, status filtering.

**BankBalanceRepository** (~7 tests): Already exists. Keep as-is.

**PendingRefundsRepository** (~12 tests): Already migrated. Keep as-is.

## Unit Tests — Services (~150 tests)

Services are tested with mocked repositories. Focus on business logic.

**TransactionsService** (~25 tests): get_data_for_analysis (merges splits, filters dates), CRUD delegation, category/tag operations, non-expense filtering.

**BudgetService** (~20 tests): monthly budget vs actual, project budget view, unmatched tag handling, rule CRUD, total budget calculation.

**TaggingRulesService** (~15 tests): rule validation, conflict detection, recursive condition building, priority management, auto-tag application.

**CategoriesTagsService** (~15 tests): add/delete/rename categories and tags, cascading updates to transactions, icon mapping.

**AnalysisService** (~20 tests): monthly summaries, category breakdowns, trend calculations, date range filtering, Sankey diagram data.

**ScrapingService** (~15 tests): scrape orchestration (mock subprocess), credential retrieval, rate limit enforcement, history logging, 2FA flow.

**CredentialsService** (~10 tests): read/write YAML, keyring interactions (mocked), provider validation.

**InvestmentsService** (~10 tests): portfolio management, balance calculations, provider operations.

**BankBalanceService** (~8 tests): Already exists. Keep as-is.

**PendingRefundsService** (~12 tests): Already migrated. Keep as-is.

## Unit Tests — Scrapers (~30 tests)

**test_scraper_base.py** (~12 tests): abstract interface, credential building, error mapping from stderr, timeout handling, output parsing (stdout JSON → DataFrame).

**test_scraper_parsing.py** (~10 tests): parse credit card transactions, bank transactions, date normalization, amount sign handling, edge cases (empty output, malformed JSON).

**test_scraper_2fa.py** (~8 tests): OTP event flow (set_otp_code → event.set), cancellation ("cancel" input), timeout waiting for OTP, concurrent scraper tracking.

All scraper tests mock `subprocess.Popen` — no actual Node.js execution.

## Integration Tests (~32 tests)

Use real in-memory SQLite with seed fixtures. Test service-to-repository flow end-to-end.

**test_tagging_pipeline.py** (~10 tests): create rules → insert untagged transactions → run auto-tagging → verify categories/tags applied correctly, priority ordering respected.

**test_budget_pipeline.py** (~10 tests): create budget rules → insert transactions → verify budget vs actual calculations, project budget aggregation, unmatched tag auto-creation.

**test_split_transactions_pipeline.py** (~6 tests): create transaction → split it → verify original excluded from analysis → verify splits included → delete split → verify original restored.

**test_scraper_integration.py** (~6 tests): run dummy scraper subprocess (actual `dummy_regular.js`) → verify stdout parsed → verify transactions inserted into DB → verify scraping history logged.

## Route Tests (~91 tests)

Use FastAPI `TestClient` with `dependency_overrides` for mock DB sessions.

Each route file gets: success cases, validation errors (400), not found (404), conflict (409).

**test_transactions_routes.py** (~12 tests): GET/POST/PUT/DELETE for transactions, date filtering, pagination.

**test_budget_routes.py** (~10 tests): CRUD for monthly + project budgets, budget view endpoints.

**test_tagging_routes.py** (~8 tests): rule CRUD, auto-tag trigger, rule conflicts.

**test_analysis_routes.py** (~8 tests): dashboard data, monthly summary, category breakdown.

**test_scraping_routes.py** (~8 tests): trigger scrape, 2FA OTP submission, scrape status, rate limit response.

**test_credentials_routes.py** (~8 tests): provider CRUD, connection/disconnection.

**test_investments_routes.py** (~8 tests): portfolio CRUD, balance updates.

**test_bank_balance_routes.py** (~7 tests): balance CRUD, KPI data.

**test_pending_refunds_routes.py** (~8 tests): mark/link/cancel/list pending refunds.

**test_categories_routes.py** (~7 tests): category/tag CRUD, icon mapping.

**test_split_transactions_routes.py** (~7 tests): create/delete splits, get splits for transaction.

## Scraper Testing Strategy

- **Unit tests**: Mock `subprocess.Popen`, test Python-side logic (credential building, output parsing, error mapping, 2FA synchronization)
- **Integration tests**: Run actual `dummy_regular.js` Node.js script via subprocess, verify full pipeline from scrape trigger through DB insertion
- Assumes `israeli-bank-scrapers` npm package works correctly — only tests the Python wrapper
