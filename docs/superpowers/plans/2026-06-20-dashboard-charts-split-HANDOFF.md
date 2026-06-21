# Handoff — Dashboard Charts Split (finish Task 7 verification)

**Branch:** `claude/youthful-maxwell-9c062a`
**Spec:** `docs/superpowers/specs/2026-06-20-dashboard-charts-split-design.md`
**Plan:** `docs/superpowers/plans/2026-06-20-dashboard-charts-split.md`

## What this branch does

Splits the dashboard's single tabbed "Charts & analytics" panel into four
independent dashboard cards (Income & Expenses, Net Worth, Cash Flow,
Categories), wired into the existing `useDashboardLayout` show/hide/reorder
system. Income & Expenses + Net Worth ship visible; Cash Flow + Categories
ship hidden (opt-in) via a new `defaultHidden` registry flag that does NOT
show the "Beta" pill. Existing users' stored `charts` layout is migrated
(layout version 2 → 3).

## Status: implementation DONE, static verification DONE, live verification NOT done

### Completed & committed (Tasks 1–6 of the plan, + Task 7 spec authoring)

- `NetWorthCard.tsx`, `IncomeExpensesCard.tsx`, `CashFlowCard.tsx`,
  `CategoryBreakdownCard.tsx` extracted from `DashboardChartsPanel.tsx`
  (which is deleted). Each spec-reviewed AND code-quality-reviewed (approved).
- `useDashboardLayout.ts`: registry swap, `defaultHidden` flag (distinct from
  `beta`), `LAYOUT_VERSION=3`, exported `normalize`, v2→v3 migration.
- `Dashboard.tsx`: `cardRenderers` wired to the four cards.
- i18n keys `dashboard.cards.{incomeExpenses,netWorth,cashFlow,category}` added
  to `en.json` + `he.json`; `dashboard.cards.charts` removed.
- Vitest: `useDashboardLayout.test.ts` covers default set + both migration
  branches + the beta-vs-defaultHidden distinction.
  `DashboardLayoutManager.test.tsx` mock updated.
- e2e: new `frontend/e2e/dashboard-chart-cards.spec.ts`; updated
  `dashboard-block-sizes`, `dashboard-forecast`, `dashboard-insights-strip`,
  `dashboard-layout` specs (they referenced the removed `charts` card id and/or
  seeded `v:2` layouts that now migrate).

### Green locally (run from `frontend/`)

- `npm run lint` — clean
- `npm run build` — clean
- `npm test -- --run` — 28 files, **202 tests pass**

### NOT done (the remaining work for you)

The Playwright **e2e run** and the **Playwright MCP manual smoke** could not be
completed in the previous sandbox: the backend dev server would not stay up
there (port-8000 supervision/contention + a first-run startup hang). Everything
else is verified. Your job is to close that gap, then finish the branch.

## Your tasks

1. **Bring up both servers.** Backend on :8000, frontend on :5173. Prefer the
   project's own flow:
   - Backend venv may be missing in a fresh worktree — it auto-bootstraps on
     first `npm run backend` (~90s) via `.claude/scripts/bootstrap_venv.sh`, or
     run that script directly. (CLAUDE.md → "Environment Setup".)
   - To run both + a command in one shot:
     `python .claude/scripts/with_server.py -- npx playwright test` (this uses
     `poetry run uvicorn` + `npm run dev`; ensure poetry/venv resolve).
   - Confirm the backend is actually serving: `curl -s http://localhost:8000/api/version`
     should return JSON (not empty). If it hangs after the alembic log lines,
     check `~/.finance-analysis/logs/` and the startup for a first-run seed hang.

2. **Run the affected e2e specs** (Demo Mode is toggled by the specs via the
   testing API). From `frontend/`:
   ```
   npx playwright test \
     e2e/dashboard-chart-cards.spec.ts \
     e2e/dashboard-block-sizes.spec.ts \
     e2e/dashboard-layout.spec.ts \
     e2e/dashboard-forecast.spec.ts \
     e2e/dashboard-insights-strip.spec.ts \
     --project=chromium
   ```
   If `npx playwright install` can't fetch a browser, set
   `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` (CLAUDE.md → "UI Testing"). Fix any
   real failures. Likely-affected assertions to watch:
   - `dashboard-block-sizes`: now uses `data-card-id="income_expenses"` as the
     full-width card; default visible order is
     `budget, recent, heatmap, income_by_source, income_expenses, net_worth`
     (budget+recent pair row 1, heatmap+income_by_source pair row 2).
   - `dashboard-chart-cards`: the opt-in test clicks the "Cash Flow" row's
     "Show card" button in Settings → Dashboard, then expects
     `[data-card-id="cash_flow"]` visible. Confirm the Settings label text
     matches (`dashboard.cards.cashFlow` = "Cash Flow").
   Then run the **full** e2e suite once to catch any spec I didn't anticipate
   that touched the old panel: `npx playwright test --project=chromium`.

3. **Playwright MCP manual smoke (Demo Mode)** — per CLAUDE.md UI-patch rule.
   Enable Demo Mode (Settings → Demo Mode, or the testing API), then drive the
   real flow: dashboard shows Income & Expenses + Net Worth as separate cards;
   Net Worth view toggle switches series; Income & Expenses sub-tabs
   (Totals / Income breakdown / Expenses breakdown) switch charts; open
   Settings → Dashboard, opt in Cash Flow and Categories, confirm they render;
   reorder a card and confirm persistence across reload; check Hebrew/RTL on the
   card titles. Disable Demo Mode when done.

4. **Re-run static pre-flight** to be safe (from `frontend/`):
   `npm run lint && npm run build && npm test -- --run`. Backend is untouched by
   this change, so backend pytest is out of the changed area, but you may run
   `poetry run pytest` if you want belt-and-suspenders.

5. **Final review + finish the branch.** Do a final code review of the whole
   diff (`git diff main...HEAD`), then follow
   `superpowers:finishing-a-development-branch`. **Open the PR against `dev`,
   not `main`** (CLAUDE.md → "Branch & PR Workflow"). Conventional-commit PR
   title, e.g. `feat: split dashboard charts panel into per-chart cards`.

## Gotchas / context

- **PR target is `dev`.** Never open feature PRs to `main`.
- **Demo Mode re-copies a frozen snapshot** on toggle (CLAUDE.md "Gotchas") —
  fine for these specs; just don't hand-add demo data expecting it to persist.
- **Migration safety** was reviewed: `normalize` runs the v<3 block before the
  unknown-id filter; both charts-visible and charts-hidden cases covered; no
  duplicate/both-list corruption. Don't regress this if you touch the hook.
- **Do not** re-introduce `dir="auto"` on the translated card `<h2>` headings
  (i18n convention: translated chrome stays untagged). User-data spans inside
  the Category lists DO keep `dir="auto"`.
- **Lockfile hygiene:** never regenerate `frontend/package-lock.json` from
  scratch in a sandbox (CLAUDE.md / frontend_pwa.md → "Lockfile hygiene").

## Commits on this branch (newest first)

```
test(dashboard): add per-chart card e2e + fix specs referencing removed charts card
docs(dashboard): clarify default-hidden vs beta comments in layout hook
feat(dashboard): split charts panel into per-chart cards with migration
i18n(dashboard): add per-chart card labels, drop charts label
refactor(dashboard): extract CategoryBreakdownCard from charts panel
refactor(dashboard): extract CashFlowCard from charts panel
refactor(dashboard): extract IncomeExpensesCard from charts panel
style(dashboard): drop dir=auto from translated card heading per i18n convention
refactor(dashboard): extract NetWorthCard from charts panel
docs: implementation plan for dashboard charts panel split
docs: design spec for splitting dashboard charts panel into per-chart cards
```

---

## Ready-to-paste prompt for the cloud agent

> You are picking up an in-progress branch, `claude/youthful-maxwell-9c062a`,
> in the finance-analysis repo. The implementation of "split the dashboard
> charts panel into four per-chart cards" is complete and committed; lint,
> build, and the 202-test vitest suite all pass. What's left is live UI
> verification, which the previous environment couldn't run.
>
> Read `docs/superpowers/plans/2026-06-20-dashboard-charts-split-HANDOFF.md`
> first — it has full status, the exact commands, and gotchas. Then:
> 1. Start the backend (:8000) and frontend (:5173) — bootstrap the venv if
>    needed; confirm `curl http://localhost:8000/api/version` returns JSON.
> 2. Run the five affected e2e specs listed in the handoff, then the full
>    Playwright suite (`--project=chromium`); fix any real failures.
> 3. Do the Playwright manual smoke in Demo Mode (per the handoff + CLAUDE.md).
> 4. Re-run `npm run lint && npm run build && npm test -- --run`.
> 5. Final code review of `git diff main...HEAD`, then use
>    `superpowers:finishing-a-development-branch` to open a PR **against `dev`**
>    (not main), titled `feat: split dashboard charts panel into per-chart cards`.
>
> Do not regress the layout-migration logic or re-add `dir="auto"` to the
> translated card headings. Report e2e results honestly — if a spec fails,
> show the output and fix the root cause rather than weakening the assertion.
