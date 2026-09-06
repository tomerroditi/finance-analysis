# Dashboard Budget Card Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard budget card's 240px `SemiGauge` with a compact
shared progress bar, add the missing Yearly tab, and split `BudgetSection.tsx`
into a shell plus one component per tab.

**Architecture:** A new `common/BudgetTotalBar` owns the "spent / total + pill +
bar" treatment and is consumed by both the Budget page's `BudgetStatusBand` and
the dashboard card. The dashboard card becomes a `flex flex-col h-full` shell
that renders a three-button tab strip and delegates to `MonthlyBudgetTab`,
`YearlyBudgetTab` or `ProjectBudgetTab`; each tab owns its own TanStack Query
call, so the `enabled: viewMode === …` gating and the `activeAnalysis` ternary
chain disappear. The rule-tile grid becomes `flex-1 min-h-[16rem] overflow-y-auto`
so it absorbs whatever height the dashboard grid row gives the card.

**Tech Stack:** React 19, TypeScript (strict), TanStack Query, Tailwind CSS 4,
`react-i18next`, vitest + `@testing-library/react`, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-06-dashboard-budget-card-redesign-design.md`

## Global Constraints

- **No backend changes.** Every endpoint already exists.
- **No new i18n keys.** All strings exist in `en.json` and `he.json` already:
  `budget.title`, `budget.monthlyBudget`, `budget.yearly.tab`,
  `budget.projectBudgets`, `budget.yearly.empty`, `budget.remainingAmount`
  (`"{{amount}} remaining"`), `budget.overByAmount` (`"{{amount}} over"`),
  `budget.remaining`, `budget.overBudget`, `budget.selectProject`,
  `budget.addProject`, `budget.addRule`, `dashboard.daysRemaining`,
  `dashboard.viewAllBudgetRules`, `dashboard.noBudgetRulesForMonth`,
  `dashboard.noProjectBudgets`, `common.previous`, `common.next`,
  `tooltips.addNewProject`.
- **Tailwind logical properties only** — `ps-*`/`pe-*`/`ms-*`/`me-*`/`start-*`/
  `end-*`/`text-start`. Never `left`/`right`. Never `inset-inline-start-*` (it
  emits no CSS and fails silently).
- **Currency figures get `dir="ltr"`** when they sit inside translated text.
- **TypeScript strict:** no unused locals or parameters; the build fails on them.
- **No obvious comments, no dead code.** Comments explain *why*, not *what*.
- Run frontend commands from `frontend/`.
- Every task ends green and committed. Conventional Commits subjects.

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| create | `frontend/src/components/common/BudgetTotalBar.tsx` | Spent/total figure, remaining-or-over pill, thin progress bar, threshold colours. Two consumers, hence `common/`. |
| create | `frontend/src/components/common/BudgetTotalBar.test.tsx` | Threshold and pill unit tests. |
| modify | `frontend/src/components/budget/BudgetStatusBand.tsx` | Left column renders `BudgetTotalBar` instead of inline markup. |
| create | `frontend/src/components/dashboard/budget/BudgetRuleGrid.tsx` | The scrollable two-column tile grid, flex-fill. |
| create | `frontend/src/components/dashboard/budget/MonthlyBudgetTab.tsx` | Month nav + monthly analysis query + grid. |
| create | `frontend/src/components/dashboard/budget/ProjectBudgetTab.tsx` | Project selector + project details query + grid. |
| create | `frontend/src/components/dashboard/budget/YearlyBudgetTab.tsx` | Year nav + yearly analysis query + grid. |
| create | `frontend/src/components/dashboard/budget/types.ts` | The `BudgetRule` shape all three tabs normalize to. |
| create | `frontend/src/components/dashboard/budget/normalizeAnalysis.ts` | Folds a monthly/project analysis payload into rules + totals. |
| create | `frontend/src/components/dashboard/budget/normalizeAnalysis.test.ts` | Total-Budget-row and fallback unit tests. |
| modify | `frontend/src/components/dashboard/BudgetSection.tsx` | Shell: card chrome, tab strip, tab state, period cursors. 425 → ~110 lines. |
| delete | `frontend/src/components/common/SemiGauge.tsx` | Sole consumer removed. |
| modify | `frontend/e2e/dashboard.spec.ts` | Extend the existing journey test with a tab block. |

## Task Sequence Rationale

Each task leaves the app working and visually coherent, so a reviewer can reject
one without unpicking its neighbours:

1. `BudgetTotalBar` lands with no consumers.
2. `BudgetStatusBand` adopts it — Budget page unchanged.
3. Tile grid extracted — dashboard unchanged.
4. Gauge swapped for the bar + flex-fill — **the visible redesign**, still two tabs.
5. Shell/tab split — pure refactor, behaviour identical.
6. Yearly tab added — **feature complete**.
7. e2e coverage + full pre-PR verification.

---

### Task 1: BudgetTotalBar

**Files:**
- Create: `frontend/src/components/common/BudgetTotalBar.tsx`
- Test: `frontend/src/components/common/BudgetTotalBar.test.tsx`

**Interfaces:**
- Consumes: `formatCurrency` from `frontend/src/utils/numberFormatting.ts`.
- Produces:
  ```ts
  interface BudgetTotalBarProps {
    spent: number;
    total: number;
    /** Dims the figures when the underlying scrape is stale. */
    muted?: boolean;
  }
  export const BudgetTotalBar: React.FC<BudgetTotalBarProps>
  ```
  Renders `data-testid="budget-total-bar"` on the root and
  `data-testid="budget-total-bar-fill"` on the filled element.

**Behaviour note — one deliberate change.** This is a near-verbatim extraction of
`BudgetStatusBand.tsx:54-131`, with one fix. Today, `total === 0` with
`spent > 0` yields `percent = 100` but `over === false` (because `over` requires
`total > 0`), so the bar renders **full and emerald** — "no budget set, money
spent" looks perfectly healthy. `BudgetTotalBar` treats `total <= 0 && spent > 0`
as over, matching how the rule tiles already handle `isUnbudgetedSpend`. This
changes `BudgetStatusBand` in that one edge case; it is intentional and covered
by a test.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/common/BudgetTotalBar.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BudgetTotalBar } from "./BudgetTotalBar";

function fill(container: HTMLElement) {
  return container.querySelector('[data-testid="budget-total-bar-fill"]')!;
}

describe("BudgetTotalBar", () => {
  it("renders spent out of total with the remaining pill", () => {
    render(<BudgetTotalBar spent={66} total={12000} />);
    expect(screen.getByText(/66/)).toBeInTheDocument();
    expect(screen.getByText(/12,000/)).toBeInTheDocument();
    expect(screen.getByText(/11,934 . remaining/)).toBeInTheDocument();
  });

  it("is emerald and proportionally filled while comfortably under budget", () => {
    const { container } = render(<BudgetTotalBar spent={250} total={1000} />);
    expect(fill(container).className).toContain("bg-emerald-500");
    expect(fill(container).getAttribute("style")).toContain("width: 25%");
  });

  it("turns amber past 90% without being over", () => {
    const { container } = render(<BudgetTotalBar spent={950} total={1000} />);
    expect(fill(container).className).toContain("bg-amber-500");
  });

  it("turns rose and reports the overage once spend exceeds the total", () => {
    const { container } = render(<BudgetTotalBar spent={1200} total={1000} />);
    expect(fill(container).className).toContain("bg-rose-500");
    expect(screen.getByText(/200 . over/)).toBeInTheDocument();
  });

  it("caps the bar at 100% so an overspend cannot overflow its track", () => {
    const { container } = render(<BudgetTotalBar spent={5000} total={1000} />);
    expect(fill(container).getAttribute("style")).toContain("width: 100%");
  });

  // Regression: a zero budget with spend against it used to render a full
  // emerald bar, reading as healthy when nothing was budgeted at all.
  it("treats spend against a zero budget as fully over", () => {
    const { container } = render(<BudgetTotalBar spent={80} total={0} />);
    expect(fill(container).className).toContain("bg-rose-500");
    expect(fill(container).getAttribute("style")).toContain("width: 100%");
    expect(screen.getByText(/80 . over/)).toBeInTheDocument();
  });

  it("shows an empty bar and no pill when nothing is budgeted or spent", () => {
    const { container } = render(<BudgetTotalBar spent={0} total={0} />);
    expect(fill(container).getAttribute("style")).toContain("width: 0%");
    expect(screen.queryByText(/remaining|over/)).not.toBeInTheDocument();
  });

  it("clamps a negative spend (net refund) to zero", () => {
    const { container } = render(<BudgetTotalBar spent={-40} total={1000} />);
    expect(fill(container).getAttribute("style")).toContain("width: 0%");
    expect(fill(container).className).toContain("bg-emerald-500");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/common/BudgetTotalBar.test.tsx
```

Expected: FAIL — `Failed to resolve import "./BudgetTotalBar"`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/components/common/BudgetTotalBar.tsx`:

```tsx
import React from "react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

interface BudgetTotalBarProps {
  spent: number;
  total: number;
  /** Dims the figures when the underlying scrape is stale. */
  muted?: boolean;
}

/**
 * "How am I doing" in one line: the figure, the gap, and a bar.
 *
 * Shared by the Budget page's status band and the dashboard's budget card so
 * the two cannot drift apart on where amber starts or on how an overspend is
 * worded.
 */
export const BudgetTotalBar: React.FC<BudgetTotalBarProps> = ({
  spent,
  total,
  muted = false,
}) => {
  const { t } = useTranslation();

  // A net refund can push a category negative; the bar floors at empty.
  const clamped = Math.max(spent, 0);
  // A zero total with spend against it is fully over, not healthy — nothing
  // was budgeted, so every shekel is unbudgeted.
  const over = clamped > total || (total <= 0 && clamped > 0);
  const percent = total > 0 ? Math.min((clamped / total) * 100, 100) : over ? 100 : 0;
  const near = !over && total > 0 && clamped > total * 0.9;
  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const remaining = total - clamped;
  const dimmed = muted ? "opacity-60" : "";

  return (
    <div data-testid="budget-total-bar">
      <div className={`flex items-baseline flex-wrap gap-2 mb-2 ${dimmed}`}>
        <span className="text-xl md:text-2xl font-bold font-mono" dir="ltr">
          {formatCurrency(clamped)}
        </span>
        <span className="text-xs md:text-sm text-[var(--text-muted)] font-mono" dir="ltr">
          / {formatCurrency(total)}
        </span>
        {(total > 0 || over) && (
          <span
            className={`text-[10px] sm:text-xs font-medium px-2 py-0.5 rounded-full ${
              over ? "bg-rose-500/10 text-rose-400" : "bg-emerald-500/10 text-emerald-400"
            }`}
            dir="ltr"
          >
            {over
              ? t("budget.overByAmount", { amount: formatCurrency(Math.abs(remaining)) })
              : t("budget.remainingAmount", { amount: formatCurrency(remaining) })}
          </span>
        )}
      </div>

      <div className="relative h-2 rounded-full bg-[var(--surface-light)] overflow-hidden">
        <div
          data-testid="budget-total-bar-fill"
          className={`absolute inset-y-0 start-0 rounded-full ${barColor} transition-all duration-500 ease-out`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/common/BudgetTotalBar.test.tsx
```

Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/common/BudgetTotalBar.tsx frontend/src/components/common/BudgetTotalBar.test.tsx
git commit -m "feat(budget): add shared BudgetTotalBar"
```

---

### Task 2: BudgetStatusBand adopts BudgetTotalBar

**Files:**
- Modify: `frontend/src/components/budget/BudgetStatusBand.tsx:54-131`

**Interfaces:**
- Consumes: `BudgetTotalBar` from Task 1.
- Produces: no public API change. `BudgetStatusBandProps` keeps every prop it
  has today (`label`, `spent`, `total`, `stats`, `footer`, `isStale`,
  `children`) and `data-testid="budget-status-band"` stays on the root.

- [ ] **Step 1: Delete the now-duplicated derivation block**

In `BudgetStatusBand.tsx`, remove these lines (currently 54-61) — the whole
`clamped`/`percent`/`over`/`near`/`barColor`/`remaining` group. Keep
`const staleValue = isStale ? "opacity-60" : "";` — the stats column still uses
it:

```tsx
  const clamped = Math.max(spent, 0);
  const percent =
    total > 0 ? Math.min((clamped / total) * 100, 100) : clamped > 0 ? 100 : 0;
  const over = clamped > total && total > 0;
  const near = !over && total > 0 && clamped > total * 0.9;
  const barColor = over ? "bg-rose-500" : near ? "bg-amber-500" : "bg-emerald-500";
  const remaining = total - clamped;
```

- [ ] **Step 2: Replace the figure + bar markup with the component**

Replace the whole block that starts with `<div className={`flex items-baseline
flex-wrap gap-2 mt-1.5 mb-2 ${staleValue}`}>` and ends with the closing `</div>`
of the `relative h-2 rounded-full` track. Match on content, not line numbers —
Step 1 already shifted them. With:

```tsx
          <div className="mt-1.5">
            <BudgetTotalBar spent={spent} total={total} muted={isStale} />
          </div>
```

- [ ] **Step 3: Add the import**

Add below the existing `formatCurrency` import at the top of the file:

```tsx
import { BudgetTotalBar } from "../common/BudgetTotalBar";
```

- [ ] **Step 4: Confirm `formatCurrency` is still used**

```bash
cd frontend && grep -n "formatCurrency" src/components/budget/BudgetStatusBand.tsx
```

Expected: no matches. If so, delete the now-unused import — strict mode fails
the build on it:

```bash
cd frontend && sed -i '' '/import { formatCurrency } from "..\/..\/utils\/numberFormatting";/d' src/components/budget/BudgetStatusBand.tsx
```

- [ ] **Step 5: Type-check and run the Budget page's unit tests**

```bash
cd frontend && npm run build && npx vitest run src/components/budget src/pages/Budget.test.tsx
```

Expected: build succeeds, tests PASS.

- [ ] **Step 6: Run the Budget page e2e specs that exercise the band**

```bash
cd frontend && npm run test:e2e:isolated -- budget.spec.ts yearly-budget.spec.ts budget-freshness.spec.ts
```

Expected: PASS. `budget-freshness.spec.ts` is the one that covers the `isStale`
path now routed through `muted`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/budget/BudgetStatusBand.tsx
git commit -m "refactor(budget): render BudgetStatusBand's figure through BudgetTotalBar"
```

---

### Task 3: Extract BudgetRuleGrid

**Files:**
- Create: `frontend/src/components/dashboard/budget/types.ts`
- Create: `frontend/src/components/dashboard/budget/BudgetRuleGrid.tsx`
- Modify: `frontend/src/components/dashboard/BudgetSection.tsx` (delete the local
  `BudgetRuleCards` + `getProgressColor`, import the new component)

**Interfaces:**
- Produces:
  ```ts
  // types.ts
  export interface BudgetRule {
    id: number;
    name: string;
    category: string;
    budget_amount: number;
    spent_amount: number;
  }

  // BudgetRuleGrid.tsx
  interface BudgetRuleGridProps {
    rules: BudgetRule[];
    categoryIcons: Record<string, string> | undefined;
  }
  export const BudgetRuleGrid: React.FC<BudgetRuleGridProps>
  ```

Note the `tags` field present on today's local `BudgetRule` interface is
**dropped** — the grid never reads it, and keeping it would force the yearly tab
(whose rules carry `tags: string[]`, not `string | null`) to fake a shape nobody
uses.

**This task is behaviour-preserving apart from the height rule:** the fixed
`h-[260px] mb-4` wrapper becomes `flex-1 min-h-[16rem] mb-4`. The card
is not yet a flex column, so `flex-1` is inert here; Task 4 completes the chain.

- [ ] **Step 1: Create the shared rule type**

Create `frontend/src/components/dashboard/budget/types.ts`:

```ts
/**
 * The single shape the dashboard's rule grid renders. Monthly, yearly and
 * project analyses each return a different rule payload; every tab normalizes
 * to this before handing rows to the grid.
 */
export interface BudgetRule {
  id: number;
  name: string;
  category: string;
  budget_amount: number;
  spent_amount: number;
}
```

- [ ] **Step 2: Create the grid component**

Create `frontend/src/components/dashboard/budget/BudgetRuleGrid.tsx`. This is
the current `BudgetRuleCards` body verbatim, with the wrapper's height rule
changed and the `rules.length > 0` guard dropped (an empty grid renders nothing
either way, and every caller already branches on its own empty state):

```tsx
import React from "react";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../../utils/numberFormatting";
import type { BudgetRule } from "./types";

interface BudgetRuleGridProps {
  rules: BudgetRule[];
  categoryIcons: Record<string, string> | undefined;
}

function getProgressColor(pct: number, isUnbudgetedSpend: boolean): string {
  if (isUnbudgetedSpend || pct > 100) return "bg-rose-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

/**
 * Per-category tiles, scrolling inside whatever height the card's row allows.
 *
 * `flex-1` rather than a fixed height: the dashboard grid stretches half-cards
 * to their row-mate, so a pinned height turns reclaimed space into padding on
 * desktop. The explicit `min-h-[16rem]` does double duty — it overrides a flex
 * child's default `min-height: auto` (without which the grid refuses to shrink
 * below its content and never scrolls) and sets the four-tile floor that keeps
 * a short row, or the content-sized single-column mobile grid, from crushing
 * it. Do not add `min-h-0` alongside it: both compile to `min-height` and the
 * winner would come down to stylesheet order.
 */
export const BudgetRuleGrid: React.FC<BudgetRuleGridProps> = ({
  rules,
  categoryIcons,
}) => {
  const { t } = useTranslation();
  return (
    <div
      data-testid="budget-rule-grid"
      className="flex-1 min-h-[16rem] overflow-y-auto scrollbar-auto-hide mb-4"
    >
      <div className="grid grid-cols-2 gap-3">
        {rules.map((rule) => {
          // budget_amount can be 0 (e.g., "Other Expenses" when the user has
          // allocated their full Total Budget across explicit rules). Treat any
          // spend in a zero-budget rule as fully over budget so the bar fills
          // rose instead of staying empty.
          const isUnbudgetedSpend = rule.budget_amount <= 0 && rule.spent_amount > 0;
          const pct =
            rule.budget_amount > 0
              ? (rule.spent_amount / rule.budget_amount) * 100
              : isUnbudgetedSpend
                ? 100
                : 0;
          const remaining = rule.budget_amount - rule.spent_amount;
          const icon = categoryIcons?.[rule.category] ?? "";
          return (
            <div
              key={rule.id}
              className="bg-[var(--surface-light)] rounded-xl p-3.5 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 min-w-0">
                  {icon && <span className="text-sm flex-shrink-0">{icon}</span>}
                  <span className="text-xs font-semibold truncate" dir="auto">
                    {rule.name}
                  </span>
                </div>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                    isUnbudgetedSpend || pct > 100
                      ? "bg-rose-500/20 text-rose-400"
                      : pct >= 75
                        ? "bg-amber-500/20 text-amber-400"
                        : "bg-emerald-500/20 text-emerald-400"
                  }`}
                >
                  {Math.round(pct)}%
                </span>
              </div>
              <p className="text-sm font-bold">
                {formatCurrency(rule.spent_amount)}
                <span className="text-xs font-normal text-[var(--text-muted)]">
                  {" "}
                  / {formatCurrency(rule.budget_amount)}
                </span>
              </p>
              <div className="h-1.5 w-full rounded-full bg-[var(--surface)] overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${getProgressColor(pct, isUnbudgetedSpend)}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <p
                className={`text-[10px] font-medium ${
                  remaining >= 0 ? "text-[var(--text-muted)]" : "text-rose-400"
                }`}
              >
                {remaining >= 0
                  ? `${formatCurrency(remaining)} ${t("budget.remaining").toLowerCase()}`
                  : `${formatCurrency(Math.abs(remaining))} ${t("budget.overBudget").toLowerCase()}`}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Point BudgetSection at it**

In `BudgetSection.tsx`:
1. Delete the local `getProgressColor` function, the local `BudgetRule`
   interface, and the whole `BudgetRuleCards` component.
2. Replace `<BudgetRuleCards rules={miniRules} categoryIcons={categoryIcons} />`
   with `<BudgetRuleGrid rules={miniRules} categoryIcons={categoryIcons} />`.
3. Add the imports:

```tsx
import { BudgetRuleGrid } from "./budget/BudgetRuleGrid";
import type { BudgetRule } from "./budget/types";
```

- [ ] **Step 4: Type-check**

```bash
cd frontend && npm run build
```

Expected: succeeds. If it flags an unused `formatCurrency` or `useTranslation`
in `BudgetSection.tsx`, remove them — `t` is still used by the tab labels and
empty states, so `useTranslation` stays.

- [ ] **Step 5: Verify the dashboard still renders**

```bash
cd frontend && npm run test:e2e:isolated -- dashboard.spec.ts
```

Expected: PASS — this task changes no behaviour the spec observes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dashboard/budget/ frontend/src/components/dashboard/BudgetSection.tsx
git commit -m "refactor(dashboard): extract BudgetRuleGrid from BudgetSection"
```

---

### Task 4: Swap the gauge for the bar, complete the flex chain

**Files:**
- Modify: `frontend/src/components/dashboard/BudgetSection.tsx`
- Delete: `frontend/src/components/common/SemiGauge.tsx`

**Interfaces:**
- Consumes: `BudgetTotalBar` (Task 1), `BudgetRuleGrid` (Task 3).
- Produces: no API change — `BudgetSpendingGauge` keeps its name and its
  `{ categoryIcons }` prop for now. Task 5 renames it.

**This is the visible redesign.** Still two tabs; Yearly arrives in Task 6.

- [ ] **Step 1: Make the card root a flex column**

Change the root element's className from:

```tsx
      className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]"
```

to:

```tsx
      className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)] flex flex-col h-full"
```

- [ ] **Step 2: Make the non-empty branch a flex column too**

The `<>…</>` fragment holding the gauge, grid and footer link cannot pass
`flex-1` through a fragment. Replace the opening `<>` of that branch (the one
after `) : (` following the `hasNoMonthlyRules` empty state) with
`<div className="flex flex-1 flex-col min-h-0">`, and its closing `</>` with
`</div>`.

- [ ] **Step 3: Replace the gauge with the bar**

Replace:

```tsx
              {/* Gauge */}
              <div className="flex justify-center mb-6">
                <SemiGauge spent={totalSpent} budget={totalBudget} size={240} />
              </div>
```

with:

```tsx
              <div className="mb-4">
                <BudgetTotalBar spent={totalSpent} total={totalBudget} />
              </div>
```

- [ ] **Step 4: Swap the imports**

Remove `import { SemiGauge } from "../common/SemiGauge";` and add:

```tsx
import { BudgetTotalBar } from "../common/BudgetTotalBar";
```

- [ ] **Step 5: Shrink the loading skeleton to match**

The skeleton still reserves gauge-sized space. Replace:

```tsx
          <Skeleton variant="chart" className="h-40" />
```

with:

```tsx
          <Skeleton variant="chart" className="h-16" />
```

- [ ] **Step 6: Delete SemiGauge and prove nothing else used it**

```bash
cd frontend && grep -rn "SemiGauge" src/ e2e/ ; rm src/components/common/SemiGauge.tsx
```

Expected: the grep prints nothing before the delete. If it prints a hit, stop
and resolve that consumer first.

- [ ] **Step 7: Build and run the height-sensitive specs**

```bash
cd frontend && npm run build && npm run test:e2e:isolated -- dashboard.spec.ts dashboard-block-sizes.spec.ts
```

Expected: PASS. `dashboard-block-sizes.spec.ts:100` asserts `budget` and
`recent` are within 2px of each other and that no block exceeds the 39rem cap —
this is the main risk in the whole change.

- [ ] **Step 8: Look at it**

Start the dev servers and open the dashboard in Demo Mode. Confirm with your own
eyes, at desktop width and at 375px:
- the tile grid fills the card down to the footer link with no dead space below it;
- the card does **not** grow a second scrollbar (the dashboard grid puts
  `overflow-y-auto` on the card root at `Dashboard.tsx:470`, and the inner
  scroller should be the only one that engages);
- at 375px the card is visibly shorter than before.

Take a screenshot of each width and attach it to the task's review.

- [ ] **Step 9: Commit**

```bash
git add -A frontend/src/components
git commit -m "feat(dashboard): replace the budget gauge with a compact total bar"
```

---

### Task 5: Split the shell from the tabs

**Files:**
- Create: `frontend/src/components/dashboard/budget/normalizeAnalysis.ts`
- Test: `frontend/src/components/dashboard/budget/normalizeAnalysis.test.ts`
- Create: `frontend/src/components/dashboard/budget/MonthlyBudgetTab.tsx`
- Create: `frontend/src/components/dashboard/budget/ProjectBudgetTab.tsx`
- Modify: `frontend/src/components/dashboard/BudgetSection.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx:16,416`

**Interfaces:**
- Produces:
  ```ts
  // normalizeAnalysis.ts
  export interface AnalysisEntry {
    rule: { id: number; name: string; category: string; amount: number };
    current_amount: number;
  }
  export interface NormalizedAnalysis {
    rules: BudgetRule[];
    totalBudget: number;
    totalSpent: number;
  }
  export function normalizeAnalysis(
    entries: AnalysisEntry[],
    spentFallback?: number,
  ): NormalizedAnalysis

  // MonthlyBudgetTab.tsx
  interface MonthlyBudgetTabProps {
    year: number;
    month: number;
    onYearChange: (year: number) => void;
    onMonthChange: (month: number) => void;
    categoryIcons: Record<string, string> | undefined;
  }
  export const MonthlyBudgetTab: React.FC<MonthlyBudgetTabProps>

  // ProjectBudgetTab.tsx
  interface ProjectBudgetTabProps {
    selectedProject: string | null;
    onSelectProject: (project: string | null) => void;
    categoryIcons: Record<string, string> | undefined;
  }
  export const ProjectBudgetTab: React.FC<ProjectBudgetTabProps>

  // BudgetSection.tsx
  export function BudgetSection({ categoryIcons }: { categoryIcons: Record<string, string> | undefined }): JSX.Element
  ```

`BudgetSpendingGauge` is renamed to `BudgetSection` — the old name describes a
component that no longer exists. `Dashboard.tsx` is the only importer.

Period cursors live in the shell and come down as props so switching tabs does
not discard a month the user navigated to.

- [ ] **Step 1: Write the failing test for the shared normalizer**

Monthly and project analyses both carry a synthetic `"Total Budget"` row that
supplies the card's totals and must never render as a tile. Extracting the fold
keeps that rule in one place. Create
`frontend/src/components/dashboard/budget/normalizeAnalysis.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { normalizeAnalysis, type AnalysisEntry } from "./normalizeAnalysis";

function entry(
  id: number,
  name: string,
  amount: number,
  spent: number,
): AnalysisEntry {
  return {
    rule: { id, name, category: `cat-${id}`, amount },
    current_amount: spent,
  };
}

describe("normalizeAnalysis", () => {
  it("takes the totals from the Total Budget row and keeps it out of the tiles", () => {
    const result = normalizeAnalysis([
      entry(1, "Total Budget", 12000, 66),
      entry(2, "Groceries", 2000, 500),
    ]);
    expect(result.totalBudget).toBe(12000);
    expect(result.totalSpent).toBe(66);
    expect(result.rules.map((r) => r.name)).toEqual(["Groceries"]);
  });

  it("orders the remaining rules by spend, descending", () => {
    const result = normalizeAnalysis([
      entry(1, "Total Budget", 100, 0),
      entry(2, "Small", 50, 10),
      entry(3, "Big", 50, 40),
      entry(4, "Middle", 50, 25),
    ]);
    expect(result.rules.map((r) => r.name)).toEqual(["Big", "Middle", "Small"]);
  });

  it("maps a rule onto the grid's shape", () => {
    const { rules } = normalizeAnalysis([entry(7, "Groceries", 2000, 500)]);
    expect(rules[0]).toEqual({
      id: 7,
      name: "Groceries",
      category: "cat-7",
      budget_amount: 2000,
      spent_amount: 500,
    });
  });

  it("sums the rules when there is no Total Budget row", () => {
    const result = normalizeAnalysis([
      entry(1, "Groceries", 2000, 500),
      entry(2, "Bills", 3000, 1200),
    ]);
    expect(result.totalBudget).toBe(5000);
    expect(result.totalSpent).toBe(1700);
  });

  it("prefers an explicit spent fallback over the sum", () => {
    const result = normalizeAnalysis(
      [entry(1, "Groceries", 2000, 500)],
      9999,
    );
    expect(result.totalSpent).toBe(9999);
  });

  it("still prefers the Total Budget row over an explicit fallback", () => {
    const result = normalizeAnalysis(
      [entry(1, "Total Budget", 2000, 42), entry(2, "Groceries", 2000, 500)],
      9999,
    );
    expect(result.totalSpent).toBe(42);
  });

  it("returns zeroed totals and no rules for an empty payload", () => {
    expect(normalizeAnalysis([])).toEqual({
      rules: [],
      totalBudget: 0,
      totalSpent: 0,
    });
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npx vitest run src/components/dashboard/budget/normalizeAnalysis.test.ts
```

Expected: FAIL — `Failed to resolve import "./normalizeAnalysis"`.

- [ ] **Step 3: Implement the normalizer**

Create `frontend/src/components/dashboard/budget/normalizeAnalysis.ts`:

```ts
import type { BudgetRule } from "./types";

export interface AnalysisEntry {
  rule: { id: number; name: string; category: string; amount: number };
  current_amount: number;
}

export interface NormalizedAnalysis {
  rules: BudgetRule[];
  totalBudget: number;
  totalSpent: number;
}

const TOTAL_BUDGET_RULE = "Total Budget";

/**
 * Fold a monthly or project analysis payload into what the card renders.
 *
 * Both carry a synthetic "Total Budget" row that supplies the totals and must
 * not appear as a tile. Yearly analysis has no such row and does not use this —
 * its totals come from the server's roll-up instead.
 */
export function normalizeAnalysis(
  entries: AnalysisEntry[],
  spentFallback?: number,
): NormalizedAnalysis {
  const rules: BudgetRule[] = entries.map((item) => ({
    id: item.rule.id,
    name: item.rule.name,
    category: item.rule.category,
    budget_amount: item.rule.amount,
    spent_amount: item.current_amount,
  }));
  const totalRule = rules.find((r) => r.name === TOTAL_BUDGET_RULE);
  return {
    rules: rules
      .filter((r) => r.name !== TOTAL_BUDGET_RULE)
      .sort((a, b) => b.spent_amount - a.spent_amount),
    totalBudget:
      totalRule?.budget_amount ?? rules.reduce((sum, r) => sum + r.budget_amount, 0),
    totalSpent:
      totalRule?.spent_amount ??
      spentFallback ??
      rules.reduce((sum, r) => sum + r.spent_amount, 0),
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npx vitest run src/components/dashboard/budget/normalizeAnalysis.test.ts
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Create MonthlyBudgetTab**

Create `frontend/src/components/dashboard/budget/MonthlyBudgetTab.tsx`. Move the
monthly query, the prefetch effect, the month-nav handlers and the monthly empty
state out of `BudgetSection` verbatim; drop `enabled:` (an unmounted tab does
not fetch) and read the period from props:

```tsx
import React, { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { formatMonthYear } from "../../../utils/dateFormatting";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import { normalizeAnalysis } from "./normalizeAnalysis";

interface MonthlyBudgetTabProps {
  year: number;
  month: number;
  onYearChange: (year: number) => void;
  onMonthChange: (month: number) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const MonthlyBudgetTab: React.FC<MonthlyBudgetTabProps> = ({
  year,
  month,
  onYearChange,
  onMonthChange,
  categoryIcons,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const qk = useQueryKeys();
  const queryClient = useQueryClient();

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const isCurrentMonth = year === currentYear && month === currentMonth;
  const monthName = formatMonthYear(new Date(year, month - 1));
  const daysRemaining = new Date(year, month, 0).getDate() - now.getDate();

  const handlePrevious = () => {
    if (month === 1) {
      onMonthChange(12);
      onYearChange(year - 1);
    } else {
      onMonthChange(month - 1);
    }
  };

  const handleNext = () => {
    if (month === 12) {
      onMonthChange(1);
      onYearChange(year + 1);
    } else {
      onMonthChange(month + 1);
    }
  };

  // Prefetch the surrounding 11 months so navigation is instant.
  useEffect(() => {
    for (let i = 1; i <= 11; i++) {
      const d = new Date(currentYear, currentMonth - 1 - i);
      const prefetchYear = d.getFullYear();
      const prefetchMonth = d.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: qk.budget.analysis(prefetchYear, prefetchMonth, false),
        queryFn: async () => {
          const res = await budgetApi.getAnalysis(prefetchYear, prefetchMonth, false);
          return res.data;
        },
      });
    }
  }, [qk, currentYear, currentMonth, queryClient]);

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.analysis(year, month, false),
    queryFn: async () => {
      const res = await budgetApi.getAnalysis(year, month, false);
      return res.data;
    },
  });

  const analysis = useMemo(
    () => (data?.rules ? normalizeAnalysis(data.rules) : undefined),
    [data],
  );

  const nav = (
    <div className="h-9 flex items-center justify-between w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrevious}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center">
          {monthName}
        </p>
        <button
          onClick={handleNext}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
      {isCurrentMonth && (
        <span className="text-xs text-[var(--text-muted)]">
          ⏳ {t("dashboard.daysRemaining", { count: daysRemaining })}
        </span>
      )}
    </div>
  );

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <Skeleton variant="chart" className="h-16" />
      </div>
    );
  }

  if (!analysis || analysis.rules.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">
            {t("dashboard.noBudgetRulesForMonth")}
          </p>
          <Link
            to="/budget"
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.addRule")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}
      <div className="mb-4">
        <BudgetTotalBar spent={analysis.totalSpent} total={analysis.totalBudget} />
      </div>
      <BudgetRuleGrid rules={analysis.rules} categoryIcons={categoryIcons} />
      <div className="text-end">
        <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
    </div>
  );
};
```

- [ ] **Step 6: Create ProjectBudgetTab**

Create `frontend/src/components/dashboard/budget/ProjectBudgetTab.tsx`, moving
the project query, the auto-select effect, the create mutation, the selector row
and the projects empty state across:

```tsx
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { Plus } from "lucide-react";
import { budgetApi } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { SelectDropdown } from "../../common/SelectDropdown";
import { Skeleton } from "../../common/Skeleton";
import { ProjectModal } from "../../modals/ProjectModal";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { qkPrefix } from "../../../services/queryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import { normalizeAnalysis } from "./normalizeAnalysis";

interface ProjectBudgetTabProps {
  selectedProject: string | null;
  onSelectProject: (project: string | null) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const ProjectBudgetTab: React.FC<ProjectBudgetTabProps> = ({
  selectedProject,
  onSelectProject,
  categoryIcons,
}) => {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { data: projects } = useQuery({
    queryKey: qk.budget.projects(),
    queryFn: async () => {
      const res = await budgetApi.getProjects();
      return res.data as string[];
    },
  });

  const createProject = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      onSelectProject(variables.category);
      setIsModalOpen(false);
    },
  });

  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProject) {
      onSelectProject(projects[0]);
    }
  }, [projects, selectedProject, onSelectProject]);

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.projectDetails(selectedProject ?? "", false),
    queryFn: async () => {
      const res = await budgetApi.getProjectDetails(selectedProject!, false);
      return res.data;
    },
    enabled: !!selectedProject,
  });

  // Projects fall back to the payload's own total_spent, which covers spend
  // that predates any rule; monthly has no such field and sums its rules.
  const analysis = useMemo(
    () => (data?.rules ? normalizeAnalysis(data.rules, data.total_spent) : undefined),
    [data],
  );

  const modal = (
    <ProjectModal
      isOpen={isModalOpen}
      onClose={() => setIsModalOpen(false)}
      onSubmit={(payload) => createProject.mutate(payload)}
    />
  );

  if (!projects || projects.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">
            {t("dashboard.noProjectBudgets")}
          </p>
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.addProject")}
          </button>
        </div>
        {modal}
      </div>
    );
  }

  const selector = (
    <div className="h-9 flex items-center w-full gap-2 mb-4">
      <div className="flex-1">
        <SelectDropdown
          options={projects.map((p) => ({ label: p, value: p }))}
          value={selectedProject ?? ""}
          onChange={onSelectProject}
          placeholder={t("budget.selectProject")}
          size="sm"
        />
      </div>
      <button
        onClick={() => setIsModalOpen(true)}
        className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--primary)] transition-colors shrink-0"
        title={t("tooltips.addNewProject")}
      >
        <Plus size={16} />
      </button>
    </div>
  );

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {selector}
      {isLoading || !analysis ? (
        <Skeleton variant="chart" className="h-16" />
      ) : (
        <>
          <div className="mb-4">
            <BudgetTotalBar spent={analysis.totalSpent} total={analysis.totalBudget} />
          </div>
          <BudgetRuleGrid rules={analysis.rules} categoryIcons={categoryIcons} />
          <div className="text-end">
            <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
              {t("dashboard.viewAllBudgetRules")} &rarr;
            </Link>
          </div>
        </>
      )}
      {modal}
    </div>
  );
};
```

Note the `useEffect` auto-select no longer needs the
`eslint-disable react-hooks/set-state-in-effect` comment the original carried —
it calls a prop callback, not a local setter. If ESLint still flags it, keep the
disable comment with the original's wording.

- [ ] **Step 7: Reduce BudgetSection to a shell**

Replace the entire contents of
`frontend/src/components/dashboard/BudgetSection.tsx` with:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MonthlyBudgetTab } from "./budget/MonthlyBudgetTab";
import { ProjectBudgetTab } from "./budget/ProjectBudgetTab";

type BudgetTab = "monthly" | "projects";

interface BudgetSectionProps {
  categoryIcons: Record<string, string> | undefined;
}

/**
 * Dashboard budget card: chrome, tab strip and the period cursors.
 *
 * Cursors live here rather than in the tabs so switching tabs does not discard
 * a month the user had navigated to. Each tab owns its own query, so an
 * unmounted tab simply does not fetch.
 */
export function BudgetSection({ categoryIcons }: BudgetSectionProps) {
  const { t } = useTranslation();
  const now = new Date();
  const [activeTab, setActiveTab] = useState<BudgetTab>("monthly");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  const tabClass = (tab: BudgetTab) =>
    `shrink-0 whitespace-nowrap px-3 py-1 rounded-md text-xs font-semibold transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text)]"
    }`;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)] flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {t("budget.title")}
        </p>
        <div className="flex bg-[var(--surface-light)] p-0.5 rounded-lg">
          <button
            onClick={() => setActiveTab("monthly")}
            className={tabClass("monthly")}
            aria-pressed={activeTab === "monthly"}
          >
            {t("budget.monthlyBudget")}
          </button>
          <button
            onClick={() => setActiveTab("projects")}
            className={tabClass("projects")}
            aria-pressed={activeTab === "projects"}
          >
            {t("budget.projectBudgets")}
          </button>
        </div>
      </div>

      {activeTab === "monthly" && (
        <MonthlyBudgetTab
          year={year}
          month={month}
          onYearChange={setYear}
          onMonthChange={setMonth}
          categoryIcons={categoryIcons}
        />
      )}
      {activeTab === "projects" && (
        <ProjectBudgetTab
          selectedProject={selectedProject}
          onSelectProject={setSelectedProject}
          categoryIcons={categoryIcons}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 8: Update the Dashboard import**

In `frontend/src/pages/Dashboard.tsx`, change line 16 from
`import { BudgetSpendingGauge } from "../components/dashboard/BudgetSection";`
to:

```tsx
import { BudgetSection } from "../components/dashboard/BudgetSection";
```

and line 416 from `budget: () => <BudgetSpendingGauge categoryIcons={categoryIcons} />,` to:

```tsx
    budget: () => <BudgetSection categoryIcons={categoryIcons} />,
```

- [ ] **Step 9: Prove the old name is gone**

```bash
cd frontend && grep -rn "BudgetSpendingGauge" src/ e2e/
```

Expected: no output.

- [ ] **Step 10: Lint, build, unit tests**

```bash
cd frontend && npm run lint && npm run build && npm test
```

Expected: all PASS.

- [ ] **Step 11: e2e — behaviour must be unchanged by this refactor**

```bash
cd frontend && npm run test:e2e:isolated -- dashboard.spec.ts dashboard-block-sizes.spec.ts dashboard-layout.spec.ts rtl-chevrons.spec.ts
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add -A frontend/src
git commit -m "refactor(dashboard): split the budget card into a shell and per-tab components"
```

---

### Task 6: Add the Yearly tab

**Files:**
- Create: `frontend/src/components/dashboard/budget/YearlyBudgetTab.tsx`
- Modify: `frontend/src/components/dashboard/BudgetSection.tsx`

**Interfaces:**
- Consumes: `budgetApi.getYearlyAnalysis`, `YearlyAnalysis` (both already in
  `frontend/src/services/api.ts`), `qk.budget.yearly(year)`, `BudgetRuleGrid`,
  `BudgetTotalBar`.
- Produces:
  ```ts
  interface YearlyBudgetTabProps {
    year: number;
    onYearChange: (year: number) => void;
    categoryIcons: Record<string, string> | undefined;
  }
  export const YearlyBudgetTab: React.FC<YearlyBudgetTabProps>
  ```

**The one thing that differs from the other tabs.** Yearly analysis has **no**
`"Total Budget"` pseudo-rule — `backend/services/budget/yearly.py:221` computes
`total_allocated` as a plain sum over the view. So the band reads
`summary.total_spent` / `summary.total_allocated` and the grid renders **all**
rules unfiltered. Filtering for a `"Total Budget"` row here would silently drop
a real user rule if someone happened to name one that; reading a pseudo-rule
that does not exist would give a zero denominator.

Yearly rules also carry `tags: string[]` rather than `string | null`. The grid's
`BudgetRule` has no `tags` field at all (Task 3), so nothing needs converting —
just do not add one.

- [ ] **Step 1: Create the tab**

Create `frontend/src/components/dashboard/budget/YearlyBudgetTab.tsx`:

```tsx
import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import type { BudgetRule } from "./types";

interface YearlyBudgetTabProps {
  year: number;
  onYearChange: (year: number) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const YearlyBudgetTab: React.FC<YearlyBudgetTabProps> = ({
  year,
  onYearChange,
  categoryIcons,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const qk = useQueryKeys();

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.yearly(year),
    queryFn: () => budgetApi.getYearlyAnalysis(year).then((r) => r.data as YearlyAnalysis),
  });

  // Yearly analysis emits no "Total Budget" pseudo-rule — the roll-up sums the
  // view — so every row here is a real rule and the totals come from summary.
  const rules: BudgetRule[] = useMemo(
    () =>
      (data?.rules ?? [])
        .map((item) => ({
          id: item.rule.id,
          name: item.rule.name,
          category: item.rule.category,
          budget_amount: item.rule.amount,
          spent_amount: item.current_amount,
        }))
        .sort((a, b) => b.spent_amount - a.spent_amount),
    [data],
  );

  const nav = (
    <div className="h-9 flex items-center w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onYearChange(year - 1)}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p
          className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center"
          dir="ltr"
        >
          {year}
        </p>
        <button
          onClick={() => onYearChange(year + 1)}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <Skeleton variant="chart" className="h-16" />
      </div>
    );
  }

  if (rules.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">{t("budget.yearly.empty")}</p>
          <Link
            to="/budget"
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.addRule")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}
      <div className="mb-4">
        <BudgetTotalBar
          spent={data?.summary.total_spent ?? 0}
          total={data?.summary.total_allocated ?? 0}
        />
      </div>
      <BudgetRuleGrid rules={rules} categoryIcons={categoryIcons} />
      <div className="text-end">
        <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Add the third tab to the shell**

In `BudgetSection.tsx`:

1. Widen the union: `type BudgetTab = "monthly" | "yearly" | "projects";`
2. Add the year cursor beside the others:
   ```tsx
   const [yearlyYear, setYearlyYear] = useState(now.getFullYear());
   ```
3. Add the button between Monthly and Projects:
   ```tsx
          <button
            onClick={() => setActiveTab("yearly")}
            className={tabClass("yearly")}
            aria-pressed={activeTab === "yearly"}
          >
            {t("budget.yearly.tab")}
          </button>
   ```
4. Add the branch between the two existing ones:
   ```tsx
      {activeTab === "yearly" && (
        <YearlyBudgetTab
          year={yearlyYear}
          onYearChange={setYearlyYear}
          categoryIcons={categoryIcons}
        />
      )}
   ```
5. Import it: `import { YearlyBudgetTab } from "./budget/YearlyBudgetTab";`

- [ ] **Step 3: Lint, build, unit tests**

```bash
cd frontend && npm run lint && npm run build && npm test
```

Expected: all PASS.

- [ ] **Step 4: Drive it in the browser**

With the dev servers up and Demo Mode on, open the dashboard and confirm by hand:
- three tabs render side by side without wrapping or overflowing the card, at
  desktop width and at 375px;
- Yearly shows the demo DB's yearly rules with a sane total (compare against the
  Budget page's Yearly tab — the figures must agree);
- navigate Monthly to a different month, switch to Yearly and back: the month is
  still where you left it;
- switch the language to Hebrew and confirm the year-nav chevrons point the
  other way and the layout does not break.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src
git commit -m "feat(dashboard): add the yearly budget tab to the dashboard card"
```

---

### Task 7: e2e coverage and full verification

**Files:**
- Modify: `frontend/e2e/dashboard.spec.ts`

**Amended after browser verification:** the demo database contains **no yearly
budget rules in any year** (verified against `/api/budget/yearly/{2023..2027}/analysis`
— every year returns zero rules). The Yearly tab therefore renders
`budget.yearly.empty` in Demo Mode, and an assertion on `budget-rule-grid`
would fail. The spec below asserts on the year nav instead, which renders in
both the empty and populated states.

Per CLAUDE.md, these are read-only checks, so they extend the existing journey
test as a labeled block rather than adding a `test()` that would pay another
~30 s cold dashboard boot. `dashboard.spec.ts` is not in `READ_ONLY_SPECS`, so
no parallel-safety constraint applies.

- [ ] **Step 1: Extend the journey test**

In `frontend/e2e/dashboard.spec.ts`, replace the single budget assertion at
line 51:

```ts
    await expect(page.getByText(/Monthly Budget/i).first()).toBeVisible();
```

with:

```ts
    // --- Budget card: three tabs, each rendering its own period view ---
    // The section's "Budget" header is too generic to locate uniquely (the
    // sidebar nav link has the same text), so anchor on the tab labels, which
    // live only in BudgetSection.
    const budgetCard = page.locator('[data-card-id="budget"]');
    await budgetCard.scrollIntoViewIfNeeded();
    const monthlyTab = budgetCard.getByRole("button", { name: /Monthly Budget/i });
    const yearlyTab = budgetCard.getByRole("button", { name: /^Yearly$/i });
    const projectsTab = budgetCard.getByRole("button", { name: /Project Budgets/i });
    await expect(monthlyTab).toBeVisible();
    await expect(yearlyTab).toBeVisible();
    await expect(projectsTab).toBeVisible();

    // Monthly is the default and shows the compact total bar, not a gauge.
    await expect(monthlyTab).toHaveAttribute("aria-pressed", "true");
    await expect(budgetCard.getByTestId("budget-total-bar")).toBeVisible({
      timeout: 20_000,
    });

    // The demo DB ships no yearly rules, so this tab renders its empty state:
    // assert on the year nav, which is present either way, rather than on the
    // rule grid, which only exists once rules do.
    await yearlyTab.click();
    await expect(yearlyTab).toHaveAttribute("aria-pressed", "true");
    await expect(
      budgetCard.getByText(String(new Date().getFullYear()), { exact: true }),
    ).toBeVisible({ timeout: 20_000 });

    await projectsTab.click();
    await expect(projectsTab).toHaveAttribute("aria-pressed", "true");

    // Back to monthly so the rest of the journey sees the default view.
    await monthlyTab.click();
    await expect(budgetCard.getByTestId("budget-total-bar")).toBeVisible();
```

- [ ] **Step 2: Run the dashboard e2e specs**

```bash
cd frontend && npm run test:e2e:isolated -- dashboard.spec.ts dashboard-block-sizes.spec.ts dashboard-layout.spec.ts dashboard-lazy-cards.spec.ts rtl-chevrons.spec.ts
```

Expected: PASS. If `dashboard-block-sizes.spec.ts` fails on the equal-height
assertion, the flex chain is broken somewhere between `Dashboard.tsx`'s grid
child and `BudgetRuleGrid` — check that every link in
`h-full → flex flex-col h-full → flex flex-1 flex-col min-h-0 → flex-1 min-h-[16rem]`
is present.

- [ ] **Step 3: Full pre-PR checklist**

Run every gate from CLAUDE.md, from the repo root:

```bash
poetry run pytest
```

```bash
cd frontend && npm run lint && npm run build && npm test
```

```bash
cd frontend && npm run test:e2e:isolated
```

Expected: all green. Backend is untouched, so `pytest` is a regression check
only — it must still be run, not assumed.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/dashboard.spec.ts
git commit -m "test(dashboard): cover the budget card's three tabs in the journey spec"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: card structure → 4, 5, 6;
flex-fill rationale → 3, 4; tab strip → 5, 6; data table → 5 (monthly,
projects), 6 (yearly); file table → 1-6; i18n → constraints (no new keys, both
locales verified); out-of-scope items → not implemented anywhere (no pace stat,
no tab persistence, tile threshold left in `BudgetRuleGrid`); testing → 1, 7;
risks → Task 4 Step 7/8, Task 2 Step 6, Task 6's yearly-totals note.

**One deliberate deviation from the spec.** The spec called `BudgetTotalBar` a
pure extraction. Task 1 additionally fixes the `total === 0 && spent > 0` case,
which today renders a full emerald bar in `BudgetStatusBand`. Flagged in Task 1,
covered by a regression test, and it makes the shared component agree with how
the rule tiles already treat unbudgeted spend.

**Type consistency.** `BudgetRule` is defined once in
`dashboard/budget/types.ts` (Task 3) and imported by Tasks 5 and 6; it has no
`tags` field in any task. `BudgetTotalBar` takes `spent`/`total`/`muted`
everywhere it is used (Tasks 1, 2, 4, 5, 6). `BudgetRuleGrid` takes
`rules`/`categoryIcons` in every call site. Test ids `budget-total-bar`,
`budget-total-bar-fill` and `budget-rule-grid` are defined in Tasks 1 and 3 and
used in Tasks 1 and 7.

**Amendment (pre-flight, agreed before execution).** Task 5 originally inlined
a ~15-line `analysis` memo in both `MonthlyBudgetTab` and `ProjectBudgetTab`,
identical apart from the `totalSpent` fallback. They now share
`normalizeAnalysis(entries, spentFallback?)`, covered by its own unit test.
`YearlyBudgetTab` (Task 6) deliberately does **not** use it — yearly analysis
has no `"Total Budget"` row and its totals come from the server roll-up.

**Sequencing.** Tasks 4 and 5 both touch `BudgetSection.tsx`; 4 lands the visual
change on the two-tab structure and 5 restructures it, so they must run in
order. Task 5 renames `BudgetSpendingGauge` → `BudgetSection` and is the only
task touching `Dashboard.tsx`.
