# Code Review — Improvement Plan

A full-codebase review (backend, frontend, scraper framework, tests, and cross-cutting
concerns) conducted on 2026-07-18. Findings are grouped into phases by priority; each
item lists the affected files and a concrete fix. Line numbers refer to the tree at the
time of review.

## Status: EXECUTED (2026-07-18, this branch)

All six phases were implemented on `claude/app-code-review-plan-uxxi18`. Deliberate
scope adjustments from the original plan:

- **2.4 (exception standardization):** done at the repository layer (budget repo 404s,
  transactions repo re-raises); the service-wide ValueError → ValidationException
  migration across budget/transactions services was deferred — the ~20 route-level
  `except ValueError` blocks still stand and can be removed opportunistically.
- **3.2 (split-merge consolidation):** the repo-side N+1 was batched and the duplicated
  service→table map removed, but the two read-side merge implementations were kept —
  they serve different contracts (`split_id` column vs synthetic `unique_id`) with
  different consumers (budget refund exclusion vs analytics).
- **3.4 (budget composition):** decomposed into a package with one shared `_copy_rules`
  helper; the inheritance → composition conversion and the `_auto_fill_skipped` /
  `_last_copy_skipped` side channels were left for a future pass (tests read them).
- **3.5:** `transactions_service.py` was left whole (~990 lines after dead-code
  removal); the other three modules were decomposed into packages with shims.
- **3.8 (unit-of-work commits):** not done — repositories still commit eagerly; only
  bulk tagging was made single-commit (4.3).
- **3.9/5.1 (scraper):** the genuinely shareable helpers were consolidated
  (~230 lines); the 10 per-provider login-result tables and 8 provider-specific
  converters were left as-is (different field vocabularies). 163 parsing tests added.
- **6.3:** Investments, Liabilities, and DataSources decomposed; TransactionsTable was
  partially addressed (SortIcon/SortableHeader hoist, delete mutations) — the
  RowActionsCell/useTableSort extraction remains open, as do the
  RetirementGoalForm/Insurances/IncomeExpensesCard splits.
- **DI-2/DI-3 (money rounding, timezone conventions):** documented, not changed.

**Suggested execution:** each phase is a natural PR (or small PR series) into `dev`.
Phases 1–2 are quick, high-value fixes. Phases 3–5 are structural and can proceed
incrementally. Phase 6 is opportunistic cleanup to fold into whichever PR touches the
file next.

---

## Phase 1 — Security & user-visible bugs (do first, small diffs)

### 1.1 Stop serving plaintext passwords from the credentials API — HIGH
`backend/routes/credentials.py:60-72` — `GET /api/credentials/{service}/{provider}/{account_name}`
returns the full credential dict **including the keyring password** as plaintext JSON on an
unauthenticated API. In `./start.sh remote` / `prod` modes uvicorn binds `0.0.0.0`, so any
device on the network can dump every bank password with one curl.

**Fix:** mask `_SENSITIVE_FIELDS` values with a sentinel (e.g. `"__unchanged__"`) in the
response; on update, skip fields carrying the sentinel so the stored value is kept. The
frontend edit form (`DataSources.tsx:206-235`) only prefetches to prefill, so it adapts
cleanly.

### 1.2 Vercel demo fails open — MED
`index.py` never sets `ENVIRONMENT`, so `backend/main.py:225-226,385-393` defaults to
`"development"` and the public deployment mounts `/docs`, `/openapi.json`, **and**
`/api/testing/*` — anyone can `POST /api/testing/toggle_demo_mode {"enabled": false}` on the
shared instance.

**Fix:** add `os.environ.setdefault("ENVIRONMENT", "production")` in `index.py` next to
`VERCEL=1` (and/or treat `VERCEL` as production in the gates in `main.py`).

### 1.3 Broken i18n key paths render raw keys to users — HIGH (3-line fix)
- `frontend/src/components/TransactionsTable.tsx:991,994` — `t("tooltips.partiallyRefunded")` /
  `t("tooltips.clickToCancel")` don't exist at top level; keys live under
  `transactions.refunds.*`. The partial-refund tooltip and confirm dialog show literal key text.
- `frontend/src/components/dashboard/NetWorthCard.tsx:115` — `t("dashboard.noData")` should be
  `common.noData`.

**Fix:** correct the three key paths. **Follow-up:** add a small CI script diffing `t("...")`
literals against flattened `en.json` (this exact class of bug is machine-detectable).

### 1.4 Delete flows bypass mutation cache invalidation — HIGH
`frontend/src/components/TransactionsTable.tsx:471-481` (`confirmDelete`) and `:525-550`
(`handleBulkDelete`) call `transactionsApi.delete()` directly with `await`, skipping
`useMutation` — so the global `MutationCache.onSuccess` debounced invalidator never fires and
analytics/budget/dashboard caches go stale after deletes. Bulk delete is also serial
(`for…await`) with no partial-failure reporting.

**Fix:** wrap both in `useMutation` (bulk via `Promise.allSettled`), mirroring the existing
`bulkClearMutation` pattern at line 310.

### 1.5 Retirement queries bypass the query-key registry → demo/real cache bleed — HIGH
`services/queryKeys.ts` exists so every key ends with the demo-mode flag. The retirement
family ignores it: `pages/EarlyRetirement.tsx:22,27,37,43`,
`components/retirement/RetirementGoalForm.tsx:164,201,235,251` use raw `["retirement", …]`
keys; `components/transactions/RuleEditorModal.tsx:108` uses `["rule-preview", …]`. Toggling
Demo Mode can serve stale real-data projections from cache/IndexedDB (or vice versa).

**Fix:** add `retirement` and `rule-preview` sections to `makeQueryKeys()` and route these
call sites through `useQueryKeys()`; verify the persister exclusion still matches
`rule-preview` after renaming.

### 1.6 Cross-table `unique_id` lookup — the exact CLAUDE.md footgun — HIGH
`backend/repositories/transactions_repository.py:1299-1324` (`get_transaction_by_id`), exposed
via `GET /api/transactions/{transaction_id}` (`backend/routes/transactions.py:242-252`): scans
the merged multi-table frame by bare integer `unique_id`. When the same id exists in two tables
(near-certain — every table auto-increments from 1) it raises → 404; with one match it can
return the wrong table's row.

**Fix:** require a `source` param and query that single table by PK
(`db.get(repo.model, unique_id)`); delete the merged-frame scan. Also delete the dead-but-armed
`TransactionsService.update_transaction_by_id` (`transactions_service.py:404-429`), which
writes to up to three tables sharing an id.

### 1.7 Scraper adapter can permanently lock out an account — HIGH
`backend/scraper/adapter.py:275-277` — in `run()`'s `finally`, `_record_scraping_attempt()`
(an unguarded DB write) executes **before** `_unregister_from_2fa_waiting()`. If that write
raises, the adapter is never popped from `_active_scrapers` and
`ScrapingService.start_scraping_single` treats the account as "already running" until process
restart.

**Fix:** unregister first, or wrap the history write in `try/except` with a logged warning.

### 1.8 Playwright driver leak on launch failure — HIGH
`scraper/base/browser_scraper.py:107-117` — a launch exception that isn't a
"channel not installed" message re-raises without stopping the already-started Playwright
driver (`self._playwright.stop()` only runs in the for-`else`), leaking a driver process;
`scrape()` never calls `terminate` when `initialize()` raises.

**Fix:** wrap the channel loop so `self._playwright.stop()` runs before re-raising (mirror the
post-launch cleanup at lines 135-154).

---

## Phase 2 — Error handling & API consistency (backend)

### 2.1 Register a `BadRequestException` global handler — MED (one-liner)
`backend/main.py:396-425` registers handlers for the other three custom exceptions but not
`BadRequestException` (`errors.py:31-35`); raised outside a route-local `except`, it becomes a
500. Then delete the per-route wrappers in `scraping.py` / `tagging_rules.py`.

### 2.2 Remove catch-all 500s that leak internals — MED
`backend/routes/tagging_rules.py:77-78,107-108,143-144,172-173,213,248,272` —
`except Exception as e: raise HTTPException(500, detail=str(e))` defeats the sanitized global
500 handler (`main.py:442-459`) whose docstring warns `str(exc)` can leak SQL/paths. Delete the
catch-alls; let the global handler log and sanitize.

### 2.3 Stop swallowing exceptions in the transactions repository — MED-HIGH
`backend/repositories/transactions_repository.py:144-149, 178-180, 303-305, 861-862,
1019-1021, 1049-1051` — bare `except Exception: return False/None` turns real DB errors into
misleading "not found" 404s and silently drops split rows from every KPI
(`_build_split_child:861`). Catch `SQLAlchemyError` narrowly, `logger.exception`, rollback,
re-raise (or raise a domain error); distinguish rowcount-0 from failure. Hoist the two
function-local `import logging` statements (`:133, :145`) to module level.

### 2.4 Standardize on custom exceptions across services — MED
`BudgetRepository.update` raises `ValueError` (`budget_repository.py:182`); `delete`
(`:185-195`) silently succeeds on a missing id (no 404); budget/transactions services raise
plain `ValueError`, forcing ~20 `try/except ValueError → HTTPException(400)` blocks across
`routes/budget.py` / `routes/transactions.py`. Services should raise
`ValidationException` / `EntityNotFoundException` and routes should rely on the global
handlers. Also replace the `assert`-based input validation at `budget_service.py:154-156` and
`:1904-1907` (stripped under `python -O`) with `ValidationException`.

### 2.5 Guard the missing-Total-Budget `IndexError` — MED-HIGH
`backend/services/budget_service.py:481-483` (and `:454-456`) —
`…[AMOUNT].values[0]` assumes a Total Budget rule exists for the month/project; creating the
first non-total rule via `POST /budget/rules` raises `IndexError` → 500. Guard the empty case
with a validation message.

### 2.6 Scraper timeout misclassification — MED
`scraper/exceptions.py:41` + `scraper/base/base_scraper.py:100,125` — the custom
`TimeoutError` is not `asyncio.TimeoutError`, so every `wait_until`-driven timeout is reported
as `GENERAL_ERROR` instead of `TIMEOUT`. Catch it in `scrape()` (or subclass
`asyncio.TimeoutError`) and update `tests/backend/unit/test_scraper/test_scraper_utils.py:7`
to assert the mapping end-to-end. While here, decide the typed-error story: the
`CredentialsError` / `PasswordChangeError` / `AccountBlockedError` / `TwoFactorError` taxonomy
(`scraper/exceptions.py:25-38`) is never raised and `ScraperError.error_type` is never read —
either wire it into `ScrapingResult.error_type` or delete it.

### 2.7 NaN/Infinity accepted in money fields — LOW
Bare `float` Pydantic fields (e.g. `backend/routes/cash_balances.py:17-19`,
`bank_balances.py:17-20`) accept `NaN`/`Infinity`; one poisoned balance NaN-poisons every
pandas sum. Add a shared `Annotated[float, Field(allow_inf_nan=False)]` money type and use it
across route schemas.

---

## Phase 3 — De-duplication & architecture (backend)

### 3.1 Extract shared transaction classification — MED (do before 3.4)
The income/expense/non-expense mask logic exists in **four** places:
`analysis_service.py:274-338` (canonical), `transactions_service.py:1101-1127`, and the same
inline category list pasted twice in `budget_service.py:536-540` and `:1298-1302`. Extract
`backend/services/transaction_classification.py` exposing `income_mask(df)`,
`expense_mask(df)`, `EXPENSE_EXCLUDED_CATEGORIES`. This also breaks the
AnalysisService↔BudgetService lazy-import cycle (`analysis_service.py:114,553,945,1043-1046`).

### 3.2 Consolidate the two split-merge implementations — MED-HIGH
`transactions_repository.py:821-949` (row-dict based) vs
`transactions_service.py:907-1024` (`get_table_for_analysis`, DataFrame based, with its own
duplicate service→table map) implement the split read-side contract twice and can drift.
Keep one implementation (repo, batched per 4.1); make `get_table_for_analysis` consume it.

### 3.3 Move the lifespan data migration into Alembic — MED
`backend/main.py:128-215` runs `PRAGMA table_info`, a manual `ALTER TABLE`, a pandas
prior-wealth backfill, and bulk update/delete **on every boot**, outside Alembic history —
overwriting any drifted prior-wealth value each startup. Fold it into an idempotent,
inspector-guarded Alembic revision (the existing nine are the template) and delete the block.
This also cuts packaged-app startup time (the ~2s first-paint budget).

### 3.4 Decompose `budget_service.py` (2,160 lines), inheritance → composition — MED
The subclass hierarchy fights itself: subclasses override `get_all_rules` to pre-filter, so
base methods must call `BudgetService.get_all_rules(self)` explicitly to escape polymorphism
(`:174-194,263,952,987`), and `MonthlyBudgetService.update_rule` secretly handles project
rules. Split into:
1. `budget_rules_core.py` — rule CRUD, tag parsing, `validate_rule_inputs`, conflict helpers,
   plus one extracted `_copy_rules()` replacing the four near-identical copy loops
   (`:669-694, :786-825, :2076-2088, :2127-2139`).
2. `budget_expenses.py` — `get_filtered_expenses` + month-override/yearly-claim filters (what
   `AnalysisService.get_monthly_expenses` actually needs — breaks that cycle too).
3. `monthly_budget_service.py`, 4. `yearly_budget_service.py`, 5. `project_budget_service.py`.
Replace the `self._auto_fill_skipped` / `self._last_copy_skipped` mutable side channels with
return values.

### 3.5 Decompose the other oversized backend files — MED (incremental)
- `transactions_repository.py` (1,324) → `service_repositories.py` (base + 5 per-table repos +
  DTO), `scrape_ingestion.py` (`add_scraped_transactions` + reconciliation), `split_read.py`
  (batched split builder), thin aggregator.
- `investments_service.py` (1,300) → snapshots service, pure `investment_valuation.py`
  (taking pre-fetched frames — fixes the re-query pattern in 4.4), `insurance_investment_sync.py`,
  core lifecycle.
- `transactions_service.py` (1,231) → first delete ~350 lines of dead code (see 6.1), then
  split CRUD vs `analysis_frame.py`.
- `analysis_service.py` (1,131) → classification (3.1), `cashflow_analytics.py`,
  `net_worth_service.py`, `forecast_service.py`.

### 3.6 Routes reaching into repositories — LOW
`backend/routes/transactions.py:90, :247` instantiate `TransactionsRepository` directly. Add
thin service passthroughs (the `:247` one is rewritten by 1.6 anyway).

### 3.7 GET endpoints that write — MED
`budget_service.py:1737-1746` — `GET /budget/projects/{name}` auto-creates zero-amount rules
per unmatched tag, re-reading the whole budget table per tag inside the loop (`:1757`). Batch
the creation into one pass + one re-read, and move it out of the view builder (ideally an
explicit POST).

### 3.8 Single-commit multi-step writes — MED (medium-term)
Every repo method commits immediately, so composed operations aren't atomic:
`create_project` (`budget_service.py:1514-1528`) commits N+1 times; the five-way fan-out
writes commit 5× (`transactions_repository.py:1218-1297`); bulk tagging commits per row.
Short-term: make `create_project`, fan-outs, and bulk tagging single-commit. Medium-term:
repos `flush()`, services own `commit()`.

### 3.9 Scraper provider de-duplication — MED
10 copies of `_get_possible_login_results`, 8 of `_convert_transactions`, 4 each of
`_get_amount_data`/`_get_account_transactions`/`_fetch_accounts` across
`scraper/providers/`. `beinleumi_group.py` (one shared module + 25-line subclasses) is the
model — extract a shared `possible_results` builder and a generic raw-dict→`Transaction`
converter with per-provider field maps into `scraper/base/` or `scraper/utils/transactions.py`.

---

## Phase 4 — Performance

### 4.1 Batch the split-children N+1 (hottest path) — HIGH
`transactions_repository.py:883-920` does one `SELECT` per split row inside `get_table()` —
i.e. on essentially every analytics/budget/transactions request. Group splits by `source`, one
`WHERE unique_id IN (...)` per table. (Pairs with 2.3: stop swallowing exceptions there.)

### 4.2 Budget per-category full-table re-reads — MED
- `budget_service.py:1620-1628` — `get_available_categories_for_new_project` re-reads the
  whole `budget_rules` table per candidate category. Read once, build a claimed-set, set-diff.
- `budget_service.py:1757` — `read_all()` inside the per-tag loop (fixed by 3.7).

### 4.3 Bulk tagging: per-row UPDATE+COMMIT — MED
`transactions_repository.py:1073-1092` + `transactions_service.py:810-811` — 100-row bulk-tag
= 100 commits + 100 cash-balance recalcs, non-atomic. Per-table `UPDATE … WHERE unique_id IN`,
one commit, one recalc per affected account.

### 4.4 Portfolio overview re-queries per investment — MED
`investments_service.py:679-737` — ~4-5 queries × N investments per request
(`calculate_profit_loss` + `calculate_balance_over_time` each re-fetch by id). Pass the
already-loaded row and pre-fetched snapshot frame down (falls out of the 3.5 valuation
extraction).

### 4.5 Pending refunds link N+1 — LOW
`pending_refunds_service.py:350` — per-pending `get_links_for_pending(p["id"])`; batch it.

### 4.6 Frontend render hygiene — MED
`TransactionsTable.tsx:576-621` — `SortIcon` / `SortableHeader` declared inside the component
body remount every header cell on each keystroke. Hoist to module scope. (Smaller unmemoized
computations listed in 6.5 are opportunistic.)

---

## Phase 5 — Testing gaps

### 5.1 Provider parsing layer: ~6,600 untested lines — HIGH
`scraper/providers/` minus onezero has zero tests — the single biggest untested surface and
the main drag on the 40% coverage gate. Unit-test the pure parsing/conversion helpers
(`_convert_transactions`, date/amount parsers, login-result tables) with recorded fixture
payloads — no browser needed; `test_onezero.py` is the template. (Do after 3.9 so tests target
the shared converter, not 18 copies.)

### 5.2 Untested backend modules — MED
- `budget_month_override_service.py` (235) + its repository (162) — route tests only; add
  service-level precedence/merge tests.
- `savings_goal_service.py` / `savings_goal_repository.py` / `retirement_goal_repository.py`
  (~230) — the retirement-goal repo has no test importing it at all.
- `insurance_account_repository.py` + `routes/insurance_accounts.py` (~200) — the newest data
  path (hafenix → `InsuranceScraperAdapter._post_save_hook`, incl. hishtalmut sync) is
  entirely unverified.
- `routes/backup.py` — add happy-path + failure route tests.

### 5.3 e2e conditional-skip pattern — MED
Specs wrap bodies in `if (await el.isVisible().catch(() => false)) { … }`
(e.g. `frontend/e2e/budget.spec.ts:54`, `investments.spec.ts:36-40`) — a renamed element makes
the test pass vacuously. Replace with `await expect(locator).toBeVisible()` + unconditional
interaction; audit the 17 `networkidle` waits and the `waitForTimeout(300/500)` sleeps
(`budget.spec.ts:45,56`, `investments.spec.ts:39`) in the same pass.

### 5.4 Assertion-free "must not raise" tests — LOW
27 tests (e.g. `test_budget_service.py:1979,2105`, `test_tagging_rules_service.py:43,86,…`)
pass vacuously if the code becomes a no-op. Add a closing state assertion to each.

### 5.5 i18n key CI check — LOW (from 1.3)
~15-line script diffing `t("…")` literals against flattened `en.json`; found all three Phase-1
key bugs. Note ~216 locale keys are unreferenced-by-literal — many are dynamic
(`sidebar.*`, `services.*`), so dead-key removal needs a manual audit, not bulk deletion.

---

## Phase 6 — Cleanup & polish (fold into whichever PR touches the file)

### 6.1 Dead backend code (~400+ lines)
- `TransactionsService`: `add_transaction` (`:80-107`, broken — passes an ORM instance where a
  DTO is expected), `update_transaction_by_id` (`:404-429`, see 1.6),
  `sync_prior_wealth_offset` (`:109`), `get_kpis` (`:1026`), `get_liabilities_summary`
  (`:1129`, returns a DataFrame in a dict — unserializable, confirming no HTTP caller).
- `BudgetRepository.read_by_id/read_by_month/read_project_rules/read_by_period_type`
  (`budget_repository.py:97-159`); `_assure_table_exists` stubs.
- Commented-out sankey nodes (`analysis_service.py:565,570`).

### 6.2 Dead frontend endpoints & dependencies
- `services/api.ts` unreferenced: `transactionsApi.getById`, `budgetApi.getRulesByMonth`,
  `budgetApi.getYearAlerts`, `taggingApi.checkConflicts`,
  `retirementApi.getKerenHishtalmutBalance`, `retirementApi.solveForField` — delete or wire up.
- `pyproject.toml:13-14` — **`plotly` and `pyarrow` have zero imports anywhere**; remove from
  main deps, re-lock, run the suite (~100MB off every venv, faster worktree bootstrap).

### 6.3 Frontend decomposition map (incremental — when each file is next touched)
| File | Lines | Seams |
|---|---|---|
| `TransactionsTable.tsx` | 1306 | `RowActionsCell` (921-1157); replace hand-rolled delete modal with the imported `useConfirm()`; `useTableSort`/`useTableSelection` hooks; column-visibility dropdown; hoist `SortIcon` (4.6) |
| `pages/Liabilities.tsx` | 1298 | 4 modals → `components/liabilities/`; `DebtChartsSection` |
| `pages/Investments.tsx` | 1020 | `InvestmentCard` (79-312); 4 modals — 3 share a "one field + save" shape → one `SimpleFormModal` |
| `retirement/RetirementGoalForm.tsx` | 918 | `goalToForm`/`formToPayload` utils; one `usePreviewProjections()` hook replacing the thrice-duplicated preview fetch (191-209, 228-244, 275-288 — also fixes the render-phase `setTimeout` side effect at 216-245); 3 sections |
| `pages/DataSources.tsx` | 908 | `AccountCard` (311-605); `TwoFaInlineForm` (519-602); `ConnectAccountWizard` (640-892) |
| `pages/Insurances.tsx` | 719 | `AccountCardFull` + `StatCard` → `components/insurance/`; move the Hebrew payroll `parseMemo` (123-139) and monthly aggregation (567-578) out of the UI layer |
| `dashboard/IncomeExpensesCard.tsx` | 670 | Split `LedgerView`/`CompositionView`/`KpiCards` into sibling files |

While decomposing, migrate the 10+ hand-rolled modal overlays (Liabilities ×4, Investments ×4,
DataSources, TransactionsTable delete-confirm) onto the shared `components/common/Modal.tsx` —
they currently lack `aria-modal`/`aria-labelledby`/Escape handling.

### 6.4 Frontend convention fixes
- Inline `Intl.NumberFormat` (bidi-unsafe, per-call construction): `Insurances.tsx:71-77`,
  `RetirementGoalForm.tsx:49-53` → `formatCurrency()` from `utils/numberFormatting.ts`.
- `t`-shadowing callbacks (`Insurances.tsx:557,569,583`, `BudgetRuleModal.tsx:57-58,73`,
  `RuleEditorModal.tsx:470`) → rename to `tx`/`track`.
- `DataSources.tsx:816` — untranslated camelCase credential field labels → label map under
  `dataSources.fields.*`.
- `SettingsPopup.tsx:44,60-83` — backups via `useState`+`useEffect` → `useQuery`+invalidation;
  `GoalsSection.tsx:66` — `window.confirm()` → `useConfirm()`.
- Untyped API responses: add generics + shared interfaces for `investmentsApi`,
  `liabilitiesApi`, `credentialsApi`, `budgetApi` (deletes ~80 duplicated interface lines in
  pages).
- SQLite-boolean guards, `todayISO()` util, `p2p_lending` missing from the Investments "Add"
  type dropdown (`Investments.tsx:942-950`) — add or document as scraper-only.

### 6.5 Ops & misc
- **Logging:** no logging config outside the packaged binary — `logger.info` is dropped in dev.
  `logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))` in `main.py` when not frozen;
  replace the two `print()`s (`main.py:85,219`).
- **PWA:** the one SW/persister asymmetry — `/api/version` is SW-runtime-cached but
  persister-excluded; add it to the SW `urlPattern` exclusions in `frontend/vite.config.ts`.
- **Restore + migrations:** `backend/utils/backup.py:116-190` — after restoring a DB, run
  `alembic upgrade head` (same path as startup) so pre-migration backups don't error until
  restart.
- **Config:** `backend/config.py:23-25` reads `FAD_USER_DIR` at class-definition time; read it
  inside `get_user_dir()` like the other `FAD_*` overrides.
- **Money rounding:** keep floats (Decimal is overkill here) but round consistently at the
  service→route boundary with one helper; timestamps: pick one convention
  (`TimestampMixin` is UTC, scraping history is naive local).
- **API polish:** shared `StatusResponse` (defined 3×); incremental `response_model` coverage
  starting with PWA-persisted endpoints (analytics/budget/transactions) — this is also what
  makes the Schemathesis fuzz job meaningful.
- **Scraper misc:** cap the unbounded pagination loops (`beinleumi_group.py:454`,
  `onezero.py:961`) + overall CLI timeout; silent-no-op JS click/fill helpers
  (`scraper/utils/browser.py:45-80`) should report missing selectors; empty-identifier
  `unique_id` collisions (`adapter.py:511-519`) need an occurrence counter; `test_*` 2FA
  providers aren't registered in `create_scraper` so the dummy OTP flow is unreachable
  (`backend/scraper/__init__.py:12-36` has drifted from `PROVIDER_CONFIGS`); stale hardcoded
  Mac/Chrome-131 UA (`browser_scraper.py:53-57`); `asyncio.get_event_loop()` →
  `get_running_loop()` (`waiting.py:21`); CLAUDE.md provider count is stale (actual: 12 banks +
  6 credit cards + 1 insurance).

---

## Verified clean (no action needed)

- **Backup path traversal:** strict filename regex + `resolve().relative_to()` containment +
  SQLite-magic validation. Solid.
- **SQL injection:** no user input reaches raw SQL; ORM/parameterized throughout.
- **Secret logging:** no credential values logged anywhere (one DEBUG phone-number log in
  onezero — mask to last 4).
- **Demo isolation:** frozen snapshot copy, `-demo` keyring namespace, `FAD_DB_PATH` ignored
  in demo mode.
- **Alembic hygiene:** single linear chain, every revision inspector-guarded, batch_alter used.
- **API trailing slashes:** every `api.ts` path audited against backend registrations
  (`redirect_slashes=False`) — all match.
- **Locale parity:** en/he structurally identical (1,136 keys each).
- **e2e READ_ONLY_SPECS:** no write violations; no hardcoded backend URLs.
- **Test conventions:** 1,401 backend tests, all in `Test*` classes, ~100% docstring
  compliance.
- **Session management:** per-request session closed in `finally`; background scraping uses
  `get_db_context()` correctly.
- **Frontend deps:** current major lines throughout; no unused runtime deps.

## Suggested PR sequence

1. **PR 1 — Security & bug fixes:** 1.1–1.8 (each small and independent; could be 2–3 PRs).
2. **PR 2 — Error handling:** 2.1–2.7.
3. **PR 3 — Classification extraction + split-merge consolidation + N+1 batch:** 3.1, 3.2, 4.1.
4. **PR 4 — Lifespan → Alembic + budget perf:** 3.3, 3.7, 4.2, 4.3.
5. **PR 5+ — Decompositions:** 3.4, then 3.5/6.3 one file at a time, each folding in its
   Phase-6 cleanup items.
6. **PR series — Scraper:** 3.9 then 5.1 (tests against the consolidated helpers), plus the
   Phase-6 scraper misc.
7. **Ongoing:** 5.2–5.5 test improvements alongside the code they cover.
