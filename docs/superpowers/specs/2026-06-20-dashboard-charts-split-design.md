# Dashboard Charts Panel → Per-Chart Cards

**Date:** 2026-06-20
**Status:** Approved design, ready for implementation plan

## Problem

The dashboard's analytics live in a single full-width card
(`DashboardChartsPanel`) with a 4-tab bar: Income & Expenses, Net Worth,
Cash Flow (Sankey), and Categories. Only the active tab renders. This has
four UX weaknesses the user wants addressed:

1. **Discoverability** — users may never realize Net Worth / Cash Flow /
   Categories exist behind the tab bar.
2. **Comparison** — only one chart is visible at a time; you cannot see two
   side by side.
3. **Customization** — the panel is one monolithic card; users cannot choose
   which analytics they care about or where they sit.
4. **Clutter** — the single card concentrates a lot of controls and chrome.

## Goal

Split the tabbed panel into four **independent dashboard cards**, one per
chart, integrated into the existing dashboard customization system
(`useDashboardLayout`) so each chart can be independently reordered, shown,
hidden, and sized. Drop the tab bar entirely.

## Why this fits cleanly

The dashboard already has the machinery this needs:

- `useDashboardLayout` (localStorage-persisted, pub-sub synced with Settings)
  owns per-card **order** and **show/hide**, with a `half`/`full` **size** per
  card and a `beta` flag for cards that ship hidden-by-default.
- `DASHBOARD_CARDS` is the canonical registry; `Dashboard.tsx` renders only
  `layout.order` via a `cardRenderers` map.
- `DashboardLayoutManager` (Settings → Dashboard) renders the customization UI
  **purely from `DASHBOARD_CARDS`** — new cards appear automatically.
- Each of the four tab bodies in `DashboardChartsPanel` is already
  self-contained: its own view/filter `useState` and its own `useQuery` calls.
  Shared query keys (`net-worth-over-time`, `category-icons`) are deduped by
  React Query, so splitting does not double-fetch.

So this is a **recompose of existing rendering into separate cards**, not a new
subsystem.

## Decisions (locked)

| Decision | Choice |
|---|---|
| Approach | Full split into independent cards; remove the tab bar |
| Default-visible cards | Income & Expenses + Net Worth |
| Default-hidden (opt-in) cards | Cash Flow (Sankey) + Categories |
| Card sizes | All four `full` width, stacked one per row |
| User-facing resize | Out of scope (sizes stay code-defined) |
| "Pin out" hybrid (keep tabs too) | Out of scope |
| Analytics API / chart internals | Unchanged |

## Design

### 1. New components

Create four card components in `frontend/src/components/dashboard/`, each
extracted verbatim (logic-preserving) from the corresponding block in
`DashboardChartsPanel.tsx`. Each wraps the standard card chrome
(`bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)]`) and
adds a **title heading** at the top — previously the tab label carried the
identity; now each card needs its own title.

| Component | Extracted from (`insightTab`) | Owns state | Queries |
|---|---|---|---|
| `IncomeExpensesCard.tsx` | `income_expenses` | `incomeView` (Totals/Income/Expenses sub-tabs), `excludePendingRefunds`, `excludeRefunds`, `includeProjects` | `income-outcome`, `monthly-expenses`, `income-by-source`, `expenses-by-category-over-time`, `category-icons` |
| `NetWorthCard.tsx` | `net_worth` | `netWorthView` (5-way toggle) | `net-worth-over-time`, `debt-payments` |
| `CashFlowCard.tsx` | `cash_flow` | — | `sankey` |
| `CategoryBreakdownCard.tsx` | `category` | — | `analytics-category`, `category-icons` |

Each card keeps its existing sub-controls intact (Income & Expenses keeps the 6
KPI mini-cards + 3 filter toggles + sub-tabs; Net Worth keeps the period chips
+ view toggle). Internal chart sizing keeps the `min-h-[400px] md:h-[600px]`
pattern; the dashboard grid already caps card height at `--dash-card-h` (39rem)
with internal scroll.

Then **delete `DashboardChartsPanel.tsx`** and its import/usage in
`Dashboard.tsx`.

### 2. Card registry (`frontend/src/hooks/useDashboardLayout.ts`)

- Remove the `{ id: "charts", ... }` entry.
- Add four entries (declared order = default top-to-bottom order):
  ```
  { id: "income_expenses", labelKey: "dashboard.cards.incomeExpenses", size: "full" },
  { id: "net_worth",       labelKey: "dashboard.cards.netWorth",       size: "full" },
  { id: "cash_flow",       labelKey: "dashboard.cards.cashFlow",       size: "full", defaultHidden: true },
  { id: "category",        labelKey: "dashboard.cards.category",       size: "full", defaultHidden: true },
  ```
- Wire each id into the `cardRenderers` map in `Dashboard.tsx`.

> **Note on `net_worth` id:** there is no existing card with this id (the KPI
> header is pinned and not part of `DASHBOARD_CARDS`). `NetWorthView` in the
> component is an unrelated local-state type. No collision.

### 3. New `defaultHidden` flag (distinct from `beta`)

We need Cash Flow + Categories to **ship hidden** without being labeled
experimental. The existing `beta` flag does two things: (a) hide by default,
(b) show the amber "Beta" pill in Settings. We only want (a).

Introduce a separate `defaultHidden` flag:

- `DEFAULT_HIDDEN` = cards where `beta === true` **or** `defaultHidden === true`.
- `DEFAULT_ORDER` = the rest.
- The "Beta" pill (`isBetaCard`) stays driven by `beta` only — so
  `cash_flow`/`category` are hidden-by-default but carry no Beta badge.

This is an additive, backward-compatible change to the registry typing and the
default-set computation.

### 4. Migration (`normalize`, `LAYOUT_VERSION` 2 → 3)

Existing users have `charts` in their stored `order` or `hidden`. Since
`charts` is no longer a known id, the existing unknown-id filter would silently
drop it. Handle the `charts` → four-cards mapping in a `version < 3` block
**before** that filter runs:

- If `charts` is in `rawOrder` (was visible): replace it in place with
  `income_expenses` + `net_worth`; push `cash_flow` + `category` into
  `rawHidden`.
- If `charts` is in `rawHidden` (user hid the whole panel): push all four new
  ids into `rawHidden` (preserve the "I don't want charts" intent).
- Either way, drop the bare `charts` id.

After this, the existing "append any known card the stored layout never saw"
logic is a no-op for the four new ids (already placed). Net effect: a returning
user sees exactly the charts they had before, now as separate cards, with their
visible/hidden intent preserved.

### 5. Internationalization (`frontend/src/locales/en.json` + `he.json`)

Add four card-label keys (Settings list), to **both** files:
`dashboard.cards.incomeExpenses`, `dashboard.cards.netWorth`,
`dashboard.cards.cashFlow`, `dashboard.cards.category`.

In-card title headings reuse existing keys: `dashboard.incomeAndExpenses`,
`dashboard.netWorth`, `dashboard.cashFlow`, `dashboard.categories`. Hebrew is
hand-translated, not auto-generated.

### 6. Performance

Default load mounts **2** Plotly charts (Income & Expenses + Net Worth) instead
of the single full-width tabbed panel; the heavy Sankey and the Category card
do not mount unless opted in. `LazyPlot` continues to lazy-load the Plotly
bundle. Net default load is lighter than today, which respects the existing
Plotly-bundle engineering-debt note in `frontend_pwa.md`.

## Out of scope (YAGNI)

- User-facing per-card resize control (sizes remain code-defined in
  `DASHBOARD_CARDS`).
- "Pin out" hybrid that keeps the tabbed card alongside the split cards.
- Any change to analytics endpoints, chart data shaping, or chart internals.
- PWA cache changes — no new endpoints; the analytics GETs are already cached.

## Testing

- **Vitest**
  - Extend `useDashboardLayout` tests: v2→v3 migration for both
    charts-visible and charts-hidden stored layouts; assert the new default
    set (income_expenses + net_worth visible; cash_flow + category hidden);
    assert `defaultHidden` cards are hidden but **not** flagged beta.
  - Update `DashboardLayoutManager.test.tsx` for the new card list.
- **e2e** (`frontend/e2e/`, per CLAUDE.md UI-patch rule)
  - Demo mode: load dashboard, assert Income & Expenses and Net Worth render as
    separate cards (and the old single tab bar is gone); open Settings →
    Dashboard, opt in Cash Flow, assert the Cash Flow card appears on the
    dashboard.
- **Playwright MCP** manual smoke in Demo Mode before marking done (focus
  traps, query-invalidation remounts, RTL).
- **Pre-flight:** `poetry run pytest` (unaffected but run per workflow), and
  `cd frontend && npm run lint && npm run build && npm test`.

## Affected files

- `frontend/src/components/dashboard/IncomeExpensesCard.tsx` (new)
- `frontend/src/components/dashboard/NetWorthCard.tsx` (new)
- `frontend/src/components/dashboard/CashFlowCard.tsx` (new)
- `frontend/src/components/dashboard/CategoryBreakdownCard.tsx` (new)
- `frontend/src/components/dashboard/DashboardChartsPanel.tsx` (delete)
- `frontend/src/hooks/useDashboardLayout.ts` (registry + `defaultHidden` +
  migration + version bump)
- `frontend/src/pages/Dashboard.tsx` (cardRenderers map, imports)
- `frontend/src/locales/en.json`, `frontend/src/locales/he.json` (4 keys each)
- `frontend/src/hooks/useDashboardLayout.test.ts` (migration + default-set + `defaultHidden` tests)
- `frontend/src/components/settings/DashboardLayoutManager.test.tsx` (card list)
- `frontend/e2e/dashboard-chart-cards.spec.ts` (new e2e)
