# Dashboard Charts Panel → Per-Chart Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the dashboard's single tabbed analytics panel into four independent, individually show/hide/reorderable dashboard cards (Income & Expenses, Net Worth, Cash Flow, Categories) using the existing `useDashboardLayout` system, dropping the tab bar.

**Architecture:** Each of the four tab bodies in `DashboardChartsPanel.tsx` is extracted verbatim into its own card component (own state + own React Query calls — shared keys are deduped by React Query). The single `charts` entry in the `DASHBOARD_CARDS` registry is replaced by four entries; a layout-version migration maps existing users' `charts` layout to the new cards. A new `defaultHidden` registry flag ships Cash Flow + Categories hidden-by-default without the experimental "Beta" pill.

**Tech Stack:** React 19 + TypeScript (strict), Vite, TanStack Query, Tailwind CSS 4, Plotly (via `LazyPlot`), i18next (en/he), Vitest + Testing Library, Playwright (e2e).

**Spec:** `docs/superpowers/specs/2026-06-20-dashboard-charts-split-design.md`

**Key facts the implementer must know:**
- `frontend/src/components/dashboard/DashboardChartsPanel.tsx` (744 lines) is the source. Tab bodies live at these line ranges:
  - Net Worth: `{insightTab === "net_worth" && (...)}` — lines **228–370**
  - Cash Flow: lines **373–383**
  - Income & Expenses: lines **386–636**
  - Category: lines **639–740**
  - Shared helpers used only by Net Worth: `netWorthDeltas` useMemo (105–116), `seriesConfig` (118–137), `getNetWorthTraces` (139–197), and the `NetWorthView` type (13).
- The dashboard grid wrapper in `Dashboard.tsx` (lines 308–321) already applies card height/scroll behavior via `[&>*]` selectors to each card's outer element, and `lg:col-span-2` for `full` cards. So a new card component only needs to render its own surface chrome; the grid handles sizing.
- Currency: always `formatCurrency`/`formatChange`/`formatPercentChange` from `utils/numberFormatting` (never inline `Intl.NumberFormat`).
- i18n: every user-visible string via `t()`, keys added to **both** `en.json` and `he.json`.
- Run a single vitest spec with: `cd frontend && npm test -- --run path/to/spec`.

---

## File Structure

**New files:**
- `frontend/src/components/dashboard/NetWorthCard.tsx` — Net Worth chart card (period chips + 5-way view toggle).
- `frontend/src/components/dashboard/IncomeExpensesCard.tsx` — Income & Expenses card (6 KPI mini-cards, 3 filter toggles, Totals/Income/Expenses sub-tabs).
- `frontend/src/components/dashboard/CashFlowCard.tsx` — Sankey card.
- `frontend/src/components/dashboard/CategoryBreakdownCard.tsx` — Category expenses/refunds lists card.
- `frontend/e2e/dashboard-chart-cards.spec.ts` — e2e coverage.

**Modified files:**
- `frontend/src/hooks/useDashboardLayout.ts` — registry swap, `defaultHidden` flag, migration to version 3, export `normalize`.
- `frontend/src/hooks/useDashboardLayout.test.ts` — migration + default-set + `defaultHidden` tests; update the `charts` reference.
- `frontend/src/pages/Dashboard.tsx` — `cardRenderers` map + imports.
- `frontend/src/components/settings/DashboardLayoutManager.test.tsx` — update mocked layout (remove `charts`).
- `frontend/src/locales/en.json`, `frontend/src/locales/he.json` — 4 new `dashboard.cards.*` keys; remove the now-unused `dashboard.cards.charts` key.

**Deleted files:**
- `frontend/src/components/dashboard/DashboardChartsPanel.tsx`.

---

## Card chrome convention (used by Tasks 1–4)

Each new card renders this wrapper, with its own title heading (the tab label
used to carry identity; now each card states its own). `CARD_TITLE_KEY` and the
extracted JSX differ per card:

```tsx
<div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
  <div className="px-3 md:px-6 pt-4 md:pt-5">
    <h2 className="text-sm md:text-base font-bold" dir="auto">{t(CARD_TITLE_KEY)}</h2>
  </div>
  <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
    {/* extracted tab body — the inner content of the matching `insightTab === ...` block */}
  </div>
</div>
```

When extracting, copy the JSX **inside** the matching `{insightTab === "X" && ( ... )}`
block (i.e. the `<div className="flex flex-col flex-1 min-h-0"> ... </div>` or the
IIFE for Category) into the second wrapper div. Move only the state/queries/helpers
that block uses (listed per task). Keep all class names, `dir=` attributes, and
`formatCurrency` usage identical.

---

### Task 1: Extract `NetWorthCard`

**Files:**
- Create: `frontend/src/components/dashboard/NetWorthCard.tsx`

This card has no automated unit test (it is a thin render extraction; behavior is
covered by the e2e spec in Task 7 and the Playwright smoke). Verification for this
task is a clean type-check/build.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/dashboard/NetWorthCard.tsx`. Use this scaffold,
then move the Net Worth JSX (DashboardChartsPanel lines **228–370**, the inner
content of the `insightTab === "net_worth"` block) into the marked slot:

```tsx
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Plot from "../common/LazyPlot";
import { analyticsApi } from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatChange, formatPercentChange } from "../../utils/numberFormatting";
import { chartTheme, plotlyConfig } from "../../utils/plotlyLocale";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";

/** Net Worth analytics dashboard card (period chips + bank/investments/net-worth/debt toggle). */
export function NetWorthCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");

  const { data: debtPaymentsData } = useQuery({
    queryKey: ["debt-payments", isDemoMode],
    queryFn: async () => (await analyticsApi.getDebtPaymentsOverTime()).data,
  });

  const { data: netWorthData } = useQuery({
    queryKey: ["net-worth-over-time", isDemoMode],
    queryFn: async () => (await analyticsApi.getNetWorthOverTime()).data,
  });

  // Copy verbatim from DashboardChartsPanel: netWorthDeltas (105-116),
  // seriesConfig (118-137), getNetWorthTraces (139-197).

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold" dir="auto">{t("dashboard.netWorth")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        {/* PASTE: inner content of the `insightTab === "net_worth"` block (lines 229-369),
            i.e. the `<div className="flex flex-col flex-1 min-h-0"> ... </div>`. */}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors. (The old `DashboardChartsPanel` still exists and compiles; the new file is valid and self-contained.)

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors for `NetWorthCard.tsx` (no unused imports — drop any scaffold import the pasted block doesn't use).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/NetWorthCard.tsx
git commit -m "refactor(dashboard): extract NetWorthCard from charts panel"
```

---

### Task 2: Extract `IncomeExpensesCard`

**Files:**
- Create: `frontend/src/components/dashboard/IncomeExpensesCard.tsx`

- [ ] **Step 1: Create the component**

Create the file with this scaffold, then move the Income & Expenses JSX
(DashboardChartsPanel lines **386–636**, inner content of the
`insightTab === "income_expenses"` block) into the marked slot:

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calculator } from "lucide-react";
import Plot from "../common/LazyPlot";
import { analyticsApi, taggingApi } from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";
import { chartTheme, plotlyConfig, isTouchDevice, barMarker, CHART_COLORS } from "../../utils/plotlyLocale";

/** Income & Expenses dashboard card (KPI averages, refund/project filters, Totals/Income/Expenses sub-views). */
export function IncomeExpensesCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  const [excludeRefunds, setExcludeRefunds] = useState(false);

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", includeProjects, excludeRefunds, isDemoMode],
    queryFn: async () => (await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludeRefunds)).data,
  });
  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: ["expenses-by-category-over-time", isDemoMode],
    queryFn: async () => (await analyticsApi.getExpensesByCategoryOverTime()).data,
  });
  const { data: incomeBySourceData } = useQuery({
    queryKey: ["income-by-source", isDemoMode],
    queryFn: async () => (await analyticsApi.getIncomeBySourceOverTime()).data,
  });
  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, includeProjects, isDemoMode],
    queryFn: async () => (await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects)).data,
  });
  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons", isDemoMode],
    queryFn: async () => (await taggingApi.getIcons()).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold" dir="auto">{t("dashboard.incomeAndExpenses")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        {/* PASTE: inner content of the `insightTab === "income_expenses"` block (lines 387-635). */}
      </div>
    </div>
  );
}
```

Note: `categoryIcons` is used by the Income & Expenses block only if the pasted
JSX references it — verify against the source; if the block doesn't use it, drop
that query and the `taggingApi` import. (As of the source, the Income & Expenses
block does **not** use `categoryIcons`; the Category block does. Remove it here.)

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: no unused-import/var errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/IncomeExpensesCard.tsx
git commit -m "refactor(dashboard): extract IncomeExpensesCard from charts panel"
```

---

### Task 3: Extract `CashFlowCard`

**Files:**
- Create: `frontend/src/components/dashboard/CashFlowCard.tsx`

- [ ] **Step 1: Create the component**

Create the file. Move the Cash Flow JSX (DashboardChartsPanel lines **373–383**,
inner content of the `insightTab === "cash_flow"` block) into the slot:

```tsx
import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "../../services/api";
import { SankeyChart } from "../SankeyChart";
import { Skeleton } from "../common/Skeleton";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";

/** Cash Flow (Sankey) dashboard card. */
export function CashFlowCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", isDemoMode],
    queryFn: async () => (await analyticsApi.getSankeyData()).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold" dir="auto">{t("dashboard.cashFlow")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        {/* PASTE: inner content of the `insightTab === "cash_flow"` block (lines 374-382). */}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/CashFlowCard.tsx
git commit -m "refactor(dashboard): extract CashFlowCard from charts panel"
```

---

### Task 4: Extract `CategoryBreakdownCard`

**Files:**
- Create: `frontend/src/components/dashboard/CategoryBreakdownCard.tsx`

- [ ] **Step 1: Create the component**

Create the file. Move the Category JSX (DashboardChartsPanel lines **639–740**,
the IIFE body inside the `insightTab === "category"` block) into the slot:

```tsx
import { useQuery } from "@tanstack/react-query";
import { TrendingDown, Tag } from "lucide-react";
import { analyticsApi, taggingApi } from "../../services/api";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

/** Category breakdown dashboard card (expenses + refunds, sorted, with share %). */
export function CategoryBreakdownCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();

  const { data: categoryData } = useQuery({
    queryKey: ["analytics-category", isDemoMode],
    queryFn: async () => (await analyticsApi.getByCategory()).data,
  });
  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons", isDemoMode],
    queryFn: async () => (await taggingApi.getIcons()).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold" dir="auto">{t("dashboard.categories")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        {/* PASTE: the body of the `insightTab === "category"` IIFE (lines 640-739),
            i.e. the `const expenses = ...` declarations through the returned JSX. */}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/CategoryBreakdownCard.tsx
git commit -m "refactor(dashboard): extract CategoryBreakdownCard from charts panel"
```

---

### Task 5: Add the four card-label i18n keys

**Files:**
- Modify: `frontend/src/locales/en.json` (the `dashboard.cards` object, around line 257–267)
- Modify: `frontend/src/locales/he.json` (the matching `dashboard.cards` object)

This task is additive (and removes one now-dead key); it does not change behavior
yet. Doing it before Task 6 means the Settings labels resolve the moment the new
cards register.

- [ ] **Step 1: Edit `en.json`**

In `dashboard.cards`, remove the `"charts": "Charts & analytics",` line and add
the four keys (keep valid JSON — watch trailing commas):

```json
    "cards": {
      "forecast": "This Month (forecast)",
      "insights": "Insights",
      "budget": "Budget spending",
      "recent": "Recent transactions",
      "recurring": "Subscriptions & recurring",
      "goals": "Savings goals",
      "heatmap": "Spending calendar",
      "incomeBySource": "Income by source",
      "incomeExpenses": "Income & Expenses",
      "netWorth": "Net Worth",
      "cashFlow": "Cash Flow",
      "category": "Categories"
    },
```

- [ ] **Step 2: Edit `he.json`**

In the matching `dashboard.cards` object, remove the `charts` key and add the
four keys with hand Hebrew translations:

```json
      "incomeExpenses": "הכנסות והוצאות",
      "netWorth": "שווי נקי",
      "cashFlow": "תזרים מזומנים",
      "category": "קטגוריות"
```

(Place them inside `dashboard.cards`, mirroring the en.json structure and removing
the `charts` entry. Confirm both files remain valid JSON.)

- [ ] **Step 3: Validate JSON**

Run: `cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/en.json')); JSON.parse(require('fs').readFileSync('src/locales/he.json')); console.log('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "i18n(dashboard): add per-chart card labels, drop charts label"
```

---

### Task 6: Registry swap, `defaultHidden`, migration, wiring, delete panel

This is the integration task: it must land as one green commit because the
`DashboardCardId` type is consumed by `Dashboard.tsx`'s `cardRenderers` record and
by tests. Do the TDD logic steps first (vitest type-checks are skipped by vitest's
esbuild, so the migration tests can be written/run before the whole project
type-checks), then wire consumers, then verify the full build.

**Files:**
- Modify: `frontend/src/hooks/useDashboardLayout.ts`
- Modify: `frontend/src/hooks/useDashboardLayout.test.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/components/settings/DashboardLayoutManager.test.tsx`
- Delete: `frontend/src/components/dashboard/DashboardChartsPanel.tsx`

- [ ] **Step 1: Write the failing migration + default-set tests**

Replace the body of `frontend/src/hooks/useDashboardLayout.test.ts` with:

```ts
import { describe, it, expect } from "vitest";
import { cardSize, normalize, DASHBOARD_CARDS, isBetaCard } from "./useDashboardLayout";

describe("cardSize", () => {
  it("returns 'half' for the compact cards", () => {
    expect(cardSize("budget")).toBe("half");
    expect(cardSize("recent")).toBe("half");
    expect(cardSize("heatmap")).toBe("half");
  });

  it("returns 'full' for the chart cards", () => {
    expect(cardSize("income_expenses")).toBe("full");
    expect(cardSize("net_worth")).toBe("full");
    expect(cardSize("cash_flow")).toBe("full");
    expect(cardSize("category")).toBe("full");
  });

  it("every declared card has a size", () => {
    for (const card of DASHBOARD_CARDS) {
      expect(cardSize(card.id)).toMatch(/^(half|full)$/);
    }
  });
});

describe("default visibility", () => {
  it("ships income_expenses + net_worth visible and cash_flow + category hidden", () => {
    const { order, hidden } = normalize({});
    expect(order).toContain("income_expenses");
    expect(order).toContain("net_worth");
    expect(hidden).toContain("cash_flow");
    expect(hidden).toContain("category");
  });

  it("default-hidden chart cards are NOT flagged beta", () => {
    expect(isBetaCard("cash_flow")).toBe(false);
    expect(isBetaCard("category")).toBe(false);
  });
});

describe("v2 -> v3 migration of the old 'charts' card", () => {
  it("replaces a VISIBLE charts card with income_expenses + net_worth, hiding the rest", () => {
    const { order, hidden } = normalize({ v: 2, order: ["budget", "charts", "recent"], hidden: [] });
    expect(order).toContain("income_expenses");
    expect(order).toContain("net_worth");
    expect(order).not.toContain("charts");
    expect(hidden).toEqual(expect.arrayContaining(["cash_flow", "category"]));
    // original neighbours preserved
    expect(order).toContain("budget");
    expect(order).toContain("recent");
  });

  it("keeps all four new cards hidden when charts was hidden", () => {
    const { order, hidden } = normalize({ v: 2, order: ["budget", "recent"], hidden: ["charts"] });
    expect(hidden).toEqual(
      expect.arrayContaining(["income_expenses", "net_worth", "cash_flow", "category"]),
    );
    expect(order).not.toContain("income_expenses");
    expect(order).not.toContain("charts");
  });
});
```

- [ ] **Step 2: Run the tests, verify they fail**

Run: `cd frontend && npm test -- --run src/hooks/useDashboardLayout.test.ts`
Expected: FAIL — `normalize` is not exported, and the new card ids don't exist yet.

- [ ] **Step 3: Update the registry + flags in `useDashboardLayout.ts`**

In `frontend/src/hooks/useDashboardLayout.ts`:

(a) Replace the `DASHBOARD_CARDS` array's `charts` entry. Change the final entry
```ts
  { id: "charts", labelKey: "dashboard.cards.charts", size: "full" },
```
to the four entries:
```ts
  { id: "income_expenses", labelKey: "dashboard.cards.incomeExpenses", size: "full" },
  { id: "net_worth", labelKey: "dashboard.cards.netWorth", size: "full" },
  { id: "cash_flow", labelKey: "dashboard.cards.cashFlow", size: "full", defaultHidden: true },
  { id: "category", labelKey: "dashboard.cards.category", size: "full", defaultHidden: true },
```

(b) Add a `DEFAULT_HIDDEN_IDS` set alongside `BETA_IDS` (after the `BETA_IDS`
definition near line 49):
```ts
const DEFAULT_HIDDEN_IDS = new Set<DashboardCardId>(
  DASHBOARD_CARDS.filter((c) => ("defaultHidden" in c && c.defaultHidden) || ("beta" in c && c.beta)).map((c) => c.id),
);
```

(c) Change `DEFAULT_ORDER` / `DEFAULT_HIDDEN` (lines 66–67) to use the combined set:
```ts
const DEFAULT_ORDER: DashboardCardId[] = ALL_IDS.filter((id) => !DEFAULT_HIDDEN_IDS.has(id));
const DEFAULT_HIDDEN: DashboardCardId[] = ALL_IDS.filter((id) => DEFAULT_HIDDEN_IDS.has(id));
```
Leave `isBetaCard` / `BETA_IDS` unchanged so only `beta` cards get the Beta pill.

- [ ] **Step 4: Add the v3 migration and export `normalize`**

Bump the version constant (line 18):
```ts
const LAYOUT_VERSION = 3;
```

Change `function normalize(` to `export function normalize(` (line 82).

Inside `normalize`, **after** the existing `version < 2` block and **before** the
`const hidden = Array.from(` line (around line 95), insert the v3 migration. It
must run before the unknown-id filter drops the no-longer-known `charts` id:
```ts
  // v3: the single "charts" panel became four per-chart cards. Map the user's
  // old layout: a visible charts card becomes the two default-visible chart
  // cards (rest hidden); a hidden charts card hides all four.
  if (version < 3) {
    const NEW_VISIBLE = ["income_expenses", "net_worth"] as DashboardCardId[];
    const NEW_HIDDEN = ["cash_flow", "category"] as DashboardCardId[];
    const chartsIdx = rawOrder.indexOf("charts");
    if (chartsIdx !== -1) {
      rawOrder.splice(chartsIdx, 1, ...NEW_VISIBLE);
      rawHidden = [...rawHidden, ...NEW_HIDDEN];
    } else if (rawHidden.includes("charts")) {
      rawHidden = [...rawHidden, ...NEW_VISIBLE, ...NEW_HIDDEN];
    }
    rawOrder = rawOrder.filter((id) => id !== "charts");
    rawHidden = rawHidden.filter((id) => id !== "charts");
  }
```

Also extend the `DashboardLayout`-building `write` path: it already calls
`normalize`, and the `useSyncExternalStore` default uses `DEFAULT_LAYOUT`, which
now reflects the new default set — no further change needed there.

- [ ] **Step 5: Run the tests, verify they pass**

Run: `cd frontend && npm test -- --run src/hooks/useDashboardLayout.test.ts`
Expected: PASS (all `cardSize`, default-visibility, and migration cases).

- [ ] **Step 6: Wire `Dashboard.tsx`**

In `frontend/src/pages/Dashboard.tsx`:

(a) Replace the import (line 21)
```ts
import { DashboardChartsPanel } from "../components/dashboard/DashboardChartsPanel";
```
with:
```ts
import { IncomeExpensesCard } from "../components/dashboard/IncomeExpensesCard";
import { NetWorthCard } from "../components/dashboard/NetWorthCard";
import { CashFlowCard } from "../components/dashboard/CashFlowCard";
import { CategoryBreakdownCard } from "../components/dashboard/CategoryBreakdownCard";
```

(b) In the `cardRenderers` record (lines 263–279), replace the `charts` entry
```ts
    charts: () => <DashboardChartsPanel />,
```
with:
```ts
    income_expenses: () => <IncomeExpensesCard />,
    net_worth: () => <NetWorthCard />,
    cash_flow: () => <CashFlowCard />,
    category: () => <CategoryBreakdownCard />,
```

- [ ] **Step 7: Update the `DashboardLayoutManager` test mock**

In `frontend/src/components/settings/DashboardLayoutManager.test.tsx`, update the
mocked `order` (lines 16–25) to drop `charts` and keep a half+full mix:
```ts
        // budget, recent, heatmap are half-width; income_expenses, net_worth,
        // cash_flow are full-width — so both badge labels appear at least twice.
        order: [
          "budget",
          "recent",
          "heatmap",
          "income_expenses",
          "net_worth",
          "cash_flow",
        ] as DashboardCardId[],
```

- [ ] **Step 8: Delete the old panel**

Run: `git rm frontend/src/components/dashboard/DashboardChartsPanel.tsx`

- [ ] **Step 9: Full type-check, lint, and test**

Run: `cd frontend && npx tsc -b && npm run lint && npm test -- --run`
Expected: type-check clean (no missing `cardRenderers` keys, no dangling
`DashboardChartsPanel` import), lint clean, all vitest suites pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/hooks/useDashboardLayout.ts frontend/src/hooks/useDashboardLayout.test.ts frontend/src/pages/Dashboard.tsx frontend/src/components/settings/DashboardLayoutManager.test.tsx
git commit -m "feat(dashboard): split charts panel into per-chart cards with migration"
```

---

### Task 7: e2e coverage, Playwright smoke, and pre-flight

**Files:**
- Create: `frontend/e2e/dashboard-chart-cards.spec.ts`

Look at an existing spec in `frontend/e2e/` first to match the project's harness
(selectors, demo-mode setup, how the dev servers are started). Mirror that file's
imports and setup helpers exactly rather than inventing new ones.

- [ ] **Step 1: Write the e2e spec**

Create `frontend/e2e/dashboard-chart-cards.spec.ts`. Adapt the boilerplate
(test fixture import, base URL, demo-mode enablement) from a sibling spec; the
assertions to include:

```ts
// NOTE: import the project's test fixture + helpers exactly as the sibling
// specs do (e.g. `import { test, expect } from "@playwright/test";` plus any
// demo-mode helper). Replace the locators below if the repo uses data-testids.

test.describe("dashboard chart cards", () => {
  test("Income & Expenses and Net Worth render as separate cards by default", async ({ page }) => {
    await page.goto("/");
    // Both default-visible chart cards present, by their card headings:
    await expect(page.getByRole("heading", { name: "Income & Expenses" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Net Worth" })).toBeVisible();
    // The old single tabbed panel's tab bar is gone: there is no Cash Flow tab
    // button on the dashboard by default (cash flow is opt-in).
    await expect(page.getByRole("heading", { name: "Cash Flow" })).toHaveCount(0);
  });

  test("opting Cash Flow in via Settings shows it on the dashboard", async ({ page }) => {
    await page.goto("/settings"); // adjust to the real settings route + Dashboard tab
    // Open the Dashboard customization tab, find Cash Flow in the hidden list,
    // click its show (Eye) button. Match the real accessible names/labels.
    await page.getByRole("button", { name: /show/i }).first().click();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Cash Flow" })).toBeVisible();
  });
});
```

If the repo's e2e harness or routes differ, adjust locators/navigation to match —
the required assertions are: (1) the two default cards render as separate cards,
(2) the tab bar is gone, (3) a hidden chart card can be opted in and then appears.

- [ ] **Step 2: Run the e2e spec**

Run the e2e the way the repo documents it (see `.claude/rules/testing.md` →
"Verifying UI patches with Playwright", which covers running e2e via
`with_server.py` and the Chromium executable-path override). Typical:
`python .claude/scripts/with_server.py -- npx playwright test e2e/dashboard-chart-cards.spec.ts`
Expected: both tests PASS. Fix locators/setup until green.

- [ ] **Step 3: Playwright MCP manual smoke (Demo Mode)**

Enable Demo Mode (Settings → Demo Mode), then with the Playwright MCP drive the
real flow: load the dashboard, confirm Income & Expenses + Net Worth cards render
with working sub-controls (Net Worth view toggle switches series; Income & Expenses
sub-tabs switch charts), open Settings → Dashboard, opt in Cash Flow and Categories,
confirm they appear and render, reorder a card and confirm the order persists on
reload. Check both LTR and RTL (switch language to Hebrew) for the card titles.
Disable Demo Mode when done.

- [ ] **Step 4: Full pre-flight**

Run:
```bash
cd frontend && npm run lint && npm run build && npm test -- --run
```
Then from repo root:
```bash
poetry run pytest
```
Expected: all green. (Backend is unaffected but the workflow runs the full suite
that touches the changed area before pushing.)

- [ ] **Step 5: Commit**

```bash
git add frontend/e2e/dashboard-chart-cards.spec.ts
git commit -m "test(dashboard): e2e for per-chart cards and opt-in flow"
```

---

## Self-Review

**Spec coverage:**
- Four new card components → Tasks 1–4. ✔
- Delete `DashboardChartsPanel` → Task 6 Step 8. ✔
- Registry swap (remove `charts`, add 4, all `full`) → Task 6 Step 3. ✔
- `defaultHidden` flag distinct from `beta` (no Beta pill) → Task 6 Step 3 + test in Step 1. ✔
- v2→v3 migration (charts-visible and charts-hidden) → Task 6 Steps 1, 4. ✔
- Dashboard wiring → Task 6 Step 6. ✔
- i18n keys both locales → Task 5. ✔
- Default-visible = Income & Expenses + Net Worth; opt-in = Cash Flow + Categories → registry flags (Task 6) + tests. ✔
- Vitest migration/default tests → Task 6 Step 1; `DashboardLayoutManager.test` update → Task 6 Step 7. ✔
- e2e + Playwright smoke + pre-flight → Task 7. ✔
- Out-of-scope items (no resize control, no hybrid, no API changes) → respected; no task touches analytics endpoints or adds resize UI. ✔

**Placeholder scan:** Tasks 1–4 intentionally reference exact source line ranges to
move rather than re-pasting ~600 lines of existing, working JSX — the implementer
has the source file open. All logic-bearing new code (the hook registry, flags,
migration, tests, wiring) is given in full. No "TBD"/"handle edge cases" steps.

**Type consistency:** Card ids `income_expenses`, `net_worth`, `cash_flow`,
`category` are used identically in the registry (Task 6 Step 3), `cardRenderers`
(Step 6), tests (Step 1), and the Settings mock (Step 7). Label keys
`dashboard.cards.{incomeExpenses,netWorth,cashFlow,category}` match between Task 5
(json) and Task 6 (registry `labelKey`). `normalize` is exported in Task 6 Step 4
and imported in the test in Step 1. `DEFAULT_HIDDEN_IDS` defined once and used by
both `DEFAULT_ORDER` and `DEFAULT_HIDDEN`.
