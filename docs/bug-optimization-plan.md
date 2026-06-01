# Bug & Optimization Remediation Plan

> Reference doc for the long-running `claude/bug-optimization-scan-HPHFm` session.
> Tracks every finding from the repo-wide scan, its verification status, the fix,
> and progress. Update the **Status** column as work lands.

Status legend: ⬜ not started · 🔧 in progress · ✅ done (committed) · ⏭️ deferred/skipped

## Working agreement
- Develop on branch `claude/bug-optimization-scan-HPHFm`.
- Conventional Commits, small batches, one logical change set per commit.
- Backend gate: `poetry run pytest`. Frontend gate: `npm run lint && npm run build && npm test`.
- UI patches additionally require a Playwright e2e spec under `frontend/e2e/` (per CLAUDE.md). If the sandbox can't fetch a Chromium binary, the spec is still added and the limitation is noted in the commit/PR.
- Subagents do disjoint-file edits; the orchestrator runs the full test gate and commits centrally per batch to avoid git races.
- Alembic head at start of this work: `b2c4d6e8f0a1`.

---

## Phase 1 — Safe, high-value, low-risk

| ID | Status | Area | Location | Issue | Fix |
|----|--------|------|----------|-------|-----|
| B1 | ✅ | scraper | `scraper/utils/fetch.py:44-45` | `fetch_post()` returns `resp.json()` with no `raise_for_status()`; GET (l.27) has it. 4xx/5xx masked. | Added `resp.raise_for_status()` before return. |
| B6 | ✅ | scraper | `scraper/utils/fetch.py:62` + within-page fetchers (l.83/94/128/139) | Bare `Exception` on GraphQL/fetch errors; callers can't classify. | Replaced 5 bare raises with `ScraperError(msg, ErrorType.GENERIC)` (class exists in `scraper/exceptions.py`). |
| B3 | ✅ | backend | `backend/services/insights_service.py:~110` | `avg = sum(prior_vals)/len(prior_vals)` can divide by zero. | Added `if not prior_vals: continue` guard. |
| P1 | ✅ | db | `backend/models/transaction.py`, `scraping.py`, `investment_balance_snapshot.py` | No indexes on filtered/grouped columns. | Added 25 indexes via `__table_args__` + idempotent Alembic migration `c3d5e7f9a1b3` (index-existence-guarded — `create_all` runs before alembic on startup). Verified up/down round-trip on throwaway DB. |
| B5 | ✅ | frontend | `components/dashboard/GoalsSection.tsx:102` | `{goal.is_achieved && ...}` renders literal `0` for SQLite `0/1`. | `!!goal.is_achieved &&`. |
| F2 | ✅ | frontend | `components/modals/SplitTransactionModal.tsx:116` | `key={index}` on dynamic editable split list. | Stable `makeSplitId()` counter; `key={split.id}`. |
| F1 | ✅ | frontend | `components/common/InfoTooltip.tsx:55` | Hardcoded `aria-label="More info"`. | `t("common.moreInfo")` + en/he keys. |

## Phase 2 — Backend correctness / concurrency

| ID | Status | Area | Location | Issue | Fix |
|----|--------|------|----------|-------|-----|
| B4 | ⬜ | repo | `backend/repositories/investment_snapshots_repository.py:57` | Non-atomic check-then-write upsert; NullPool race on `(investment_id,date)`. | UPDATE then INSERT-if-rowcount-0 in one txn; rely on unique constraint. |
| B2 | ⬜ | scraper | `scraper/base/browser_scraper.py:126-132,210-217` | Context/page leak on `initialize()` error; `terminate()` bare `except: pass`. | try/finally cleanup; log instead of silent pass. |
| P8 | ⬜ | scraper | `backend/scraper/adapter.py:162` | No top-level 5-min `asyncio.wait_for`; sync DB writes block event loop in `async run()`. | Wrap scrape in `wait_for(...,300)`; offload sync DB work via `run_in_executor`. |
| P2 | ⬜ | backend | `backend/main.py:145-158, 174-175` | Startup N+1: per-investment `iterrows()`+UPDATE, per-row DELETE. | Bulk UPDATE / `delete(...).where(uid.in_(ids))`. |
| P7 | ⬜ | repo | tagging_rules / budget / pending_refunds repos | N+1 delete/update loops. | Bulk `delete()/update().where()`. |

## Phase 3 — Analytics performance refactor

| ID | Status | Area | Location | Issue | Fix |
|----|--------|------|----------|-------|-----|
| P3 | ⬜ | analytics | `analysis_service.py:513-516` | Sankey `nodes.index()` O(N) in loop → O(N²). | dict index map. |
| P4 | ⬜ | analytics | `analysis_service.py:578` | `income_df.apply(..., axis=1)` row-wise label. | Vectorize (`np.where`/str concat). |
| P5 | ⬜ | analytics | `analysis_service.py:323, 583` | `for month: df[df.month==month]` re-scans frame. | `groupby("month")`. |
| P6 | ⬜ | analytics | `investments_service.py:~495, ~671` | `iterrows()` daily agg; per-investment `calculate_profit_loss()` N+1. | `groupby().sum()`; fetch txns once. |

All Phase 3 changes must keep KPI regression tests green (snapshot/CC-dedup/prior-wealth semantics unchanged).

## Phase 4 — Cleanup

| ID | Status | Area | Location | Issue | Fix |
|----|--------|------|----------|-------|-----|
| Q1 | ⬜ | routes | `routes/scraping.py` | `scraping_period_days` unvalidated (negative allowed); validate-in-background. | Pydantic `field_validator > 0`; fail fast. |
| Q2 | ⬜ | routes | scraping/credentials/transactions | Missing `response_model` on several endpoints. | Add Pydantic response models. |
| Q3 | ⬜ | routes | `routes/onboarding.py:36` | Sync `def` route among async routes. | `async def`. |
| Q4 | ⬜ | backend | analysis/insights services | Duplicated category-exclusion lists. | Shared module constant. |
| Q5 | ⬜ | backend | `analysis_service.py` | Cosmetic: `trend .append` spacing, `expensses_mask` typo. | Rename/clean. |
| F3 | ⬜ | frontend | `DashboardChartsPanel.tsx:107` | Net-worth projection recomputed each render. | `useMemo`. |
| F4 | ⬜ | frontend | `DashboardChartsPanel.tsx:686` | `pr-1` physical padding. | logical `pe-1`. |
| F5 | ⬜ | frontend | `RuleEditorModal.tsx:270`, `DataSources.tsx` | `slide-in-from-left/right` not RTL-flipped. | conditional direction on `i18n.language`. |
| F6 | ⬜ | frontend | `TransactionsTable.tsx`, charts, rule preview | Large lists unvirtualized (500+ rows). | Backlog: virtualization/pagination. May defer. |

## Dropped (false positives from scan)
- `analysis_service.py:315` "syntax error" — `trend .append` is valid Python; compiles.
- ~9 `key={index}` flags on **skeletons / fixed label arrays** — never reorder, not bugs.
- `queryClient.clear()` misuse — none found.
- Suggested `findIndex(s => s === split)` key fix — O(n²) and breaks on dupes; use a stable id.
