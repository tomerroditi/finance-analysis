# UI/UX Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the Finance Analysis Dashboard from a power-user analytics tool into a daily-glance app accessible to non-technical users, with a dashboard-first approach.

**Architecture:** Frontend-only changes. The dashboard page gets a full rewrite with new sub-components (gauge, sparkline, mini budget cards, recent transactions feed). Other pages get targeted improvements. New shared utility functions for label humanization. No backend API changes.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, TanStack Query, Plotly.js (existing charts), inline SVG (new sparklines/gauge)

**Design doc:** `docs/plans/2026-02-25-ui-ux-redesign-design.md`

---

## Task 1: Service Name Humanization Utility

Add a shared utility for converting technical service/provider names to human-readable labels throughout the app.

**Files:**
- Modify: `frontend/src/utils/textFormatting.ts`

**Step 1: Add humanization maps and functions**

Add to `frontend/src/utils/textFormatting.ts`:

```typescript
/** Maps internal service identifiers to human-readable labels */
const SERVICE_LABELS: Record<string, string> = {
  credit_cards: "Credit Card",
  credit_card_transactions: "Credit Card",
  banks: "Bank",
  bank_transactions: "Bank",
  cash: "Cash",
  cash_transactions: "Cash",
  manual_investments: "Investment",
  manual_investment_transactions: "Investment",
};

/** Maps internal provider identifiers to display names */
const PROVIDER_LABELS: Record<string, string> = {
  hapoalim: "Hapoalim",
  leumi: "Leumi",
  discount: "Discount",
  mizrahi: "Mizrahi",
  onezero: "One Zero",
  isracard: "Isracard",
  max: "Max",
  cal: "Cal",
  amex: "Amex",
  beyahad: "Beyahad Bishvilha",
  behatsdaa: "Behatsdaa",
  beinleumi: "Beinleumi",
  massad: "Massad",
  yahav: "Yahav",
  fibi: "First International",
};

export function humanizeService(service: string): string {
  return SERVICE_LABELS[service] ?? toTitleCase(service.replace(/_/g, " "));
}

export function humanizeProvider(provider: string): string {
  return PROVIDER_LABELS[provider] ?? toTitleCase(provider);
}

export function humanizeAccountType(service: string): string {
  const base = humanizeService(service);
  return `${base} Account`;
}
```

**Step 2: Verify no regressions**

Run: `cd frontend && npx tsc --noEmit`
Expected: No TypeScript errors

**Step 3: Commit**

```bash
git add frontend/src/utils/textFormatting.ts
git commit -m "feat(ui): add service and provider name humanization utilities"
```

---

## Task 2: Skeleton Loading Component

Replace "Loading..." text throughout the app with animated skeleton placeholders.

**Files:**
- Create: `frontend/src/components/common/Skeleton.tsx`

**Step 1: Create Skeleton component**

```tsx
import React from "react";

interface SkeletonProps {
  className?: string;
  /** Preset shape */
  variant?: "text" | "card" | "chart" | "circle";
  /** Number of text lines to render */
  lines?: number;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  className = "",
  variant = "text",
  lines = 1,
}) => {
  if (variant === "circle") {
    return (
      <div
        className={`rounded-full bg-[var(--surface-light)] animate-pulse ${className}`}
      />
    );
  }

  if (variant === "card") {
    return (
      <div
        className={`rounded-xl bg-[var(--surface-light)] animate-pulse ${className}`}
      />
    );
  }

  if (variant === "chart") {
    return (
      <div
        className={`rounded-xl bg-[var(--surface-light)] animate-pulse h-64 ${className}`}
      />
    );
  }

  // Text variant - renders multiple lines
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={`h-4 rounded bg-[var(--surface-light)] animate-pulse ${
            i === lines - 1 && lines > 1 ? "w-3/4" : "w-full"
          }`}
        />
      ))}
    </div>
  );
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/common/Skeleton.tsx
git commit -m "feat(ui): add Skeleton loading placeholder component"
```

---

## Task 3: Sparkline SVG Component

Create a minimal inline sparkline for showing trends in the dashboard header cards.

**Files:**
- Create: `frontend/src/components/common/Sparkline.tsx`

**Step 1: Create Sparkline component**

```tsx
import React from "react";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  className?: string;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 80,
  height = 24,
  color = "var(--primary)",
  className = "",
}) => {
  if (!data || data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const padding = 2;
  const plotWidth = width - padding * 2;
  const plotHeight = height - padding * 2;

  const points = data.map((value, i) => {
    const x = padding + (i / (data.length - 1)) * plotWidth;
    const y = padding + plotHeight - ((value - min) / range) * plotHeight;
    return `${x},${y}`;
  });

  const pathD = `M ${points.join(" L ")}`;

  // Gradient fill area
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const areaD = `${pathD} L ${lastPoint.split(",")[0]},${height - padding} L ${firstPoint.split(",")[0]},${height - padding} Z`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
    >
      <defs>
        <linearGradient id={`sparkline-grad-${color.replace(/[^a-z0-9]/gi, "")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d={areaD}
        fill={`url(#sparkline-grad-${color.replace(/[^a-z0-9]/gi, "")})`}
      />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/common/Sparkline.tsx
git commit -m "feat(ui): add Sparkline SVG component for trend indicators"
```

---

## Task 4: Semicircular Budget Gauge Component

Create the hero gauge component for the dashboard's "am I on track?" section.

**Files:**
- Create: `frontend/src/components/common/SemiGauge.tsx`

**Step 1: Create SemiGauge component**

```tsx
import React from "react";

interface SemiGaugeProps {
  spent: number;
  budget: number;
  size?: number;
  className?: string;
}

export const SemiGauge: React.FC<SemiGaugeProps> = ({
  spent,
  budget,
  size = 200,
  className = "",
}) => {
  const percentage = budget > 0 ? Math.min((spent / budget) * 100, 120) : 0;
  const displayPercentage = budget > 0 ? (spent / budget) * 100 : 0;

  // Color based on percentage
  const getColor = () => {
    if (displayPercentage >= 100) return "#ef4444"; // red
    if (displayPercentage >= 75) return "#f59e0b"; // amber
    return "#22c55e"; // green
  };

  // SVG arc calculation
  const cx = size / 2;
  const cy = size / 2 + 10;
  const radius = (size / 2) - 16;
  const startAngle = Math.PI;
  const endAngle = 0;
  const filledAngle = startAngle - (percentage / 120) * Math.PI;

  const bgArcStart = {
    x: cx + radius * Math.cos(startAngle),
    y: cy - radius * Math.sin(startAngle),
  };
  const bgArcEnd = {
    x: cx + radius * Math.cos(endAngle),
    y: cy - radius * Math.sin(endAngle),
  };
  const filledArcEnd = {
    x: cx + radius * Math.cos(filledAngle),
    y: cy - radius * Math.sin(filledAngle),
  };

  const bgPath = `M ${bgArcStart.x} ${bgArcStart.y} A ${radius} ${radius} 0 0 1 ${bgArcEnd.x} ${bgArcEnd.y}`;
  const filledPath = `M ${bgArcStart.x} ${bgArcStart.y} A ${radius} ${radius} 0 ${percentage > 60 ? 1 : 0} 1 ${filledArcEnd.x} ${filledArcEnd.y}`;

  const color = getColor();

  const formatCurrency = (n: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
      maximumFractionDigits: 0,
    }).format(n);

  return (
    <div className={`flex flex-col items-center ${className}`}>
      <svg width={size} height={size / 2 + 24} viewBox={`0 0 ${size} ${size / 2 + 24}`}>
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="var(--surface-light)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Filled arc */}
        {percentage > 0 && (
          <path
            d={filledPath}
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            style={{
              transition: "stroke-dashoffset 0.5s ease-out",
            }}
          />
        )}
        {/* Center text */}
        <text
          x={cx}
          y={cy - 12}
          textAnchor="middle"
          className="text-2xl font-bold"
          fill="var(--text)"
          fontSize="22"
          fontWeight="700"
        >
          {formatCurrency(spent)}
        </text>
        <text
          x={cx}
          y={cy + 8}
          textAnchor="middle"
          fill="var(--text-muted)"
          fontSize="13"
        >
          of {formatCurrency(budget)}
        </text>
      </svg>
      <div
        className="text-sm font-semibold -mt-2"
        style={{ color }}
      >
        {displayPercentage.toFixed(0)}% used
      </div>
    </div>
  );
};
```

**Step 2: Verify build**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/common/SemiGauge.tsx
git commit -m "feat(ui): add SemiGauge component for budget visualization"
```

---

## Task 5: Dashboard Rewrite - Financial Health Header

Rewrite the top section of the dashboard with the new hero layout.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Rewrite the Dashboard component**

This is a major rewrite. Replace the current Dashboard.tsx content with the new layout. The key structural changes:

1. **Remove** the old `StatCard` sub-component (lines 12-36)
2. **Add** a `FinancialHealthHeader` section at the top with:
   - Net worth hero number with month-over-month delta
   - Three sub-cards (Bank Balance, Investments, Cash) with sparklines
3. **Keep** all existing API queries (they're all still needed)
4. **Move** chart sections into a collapsible "More Insights" accordion

The new Dashboard should be structured as:
```
<FinancialHealthHeader>  (net worth + sub-cards)
<MonthlySpendingGauge>   (gauge + mini budget cards)
<RecentTransactions>     (last 7 transactions feed)
<InsightsAccordion>      (all existing charts, collapsed by default)
<DataStatus>             (moved to smaller footer)
```

**Implementation approach:** Build each section as a local sub-component within Dashboard.tsx first. Can be extracted to separate files later if they become too large.

Start with the header section. Replace the 4 stat cards with:
- Fetch `analyticsApi.getNetWorthOverTime()` (already fetched)
- Calculate month-over-month net worth change from the last 2 data points
- Use `bankBalancesApi.getAll()` (already fetched) for per-account breakdown
- Use `investmentsApi.getPortfolioAnalysis()` (already fetched) for investment totals
- Use `Sparkline` component with the last 6 months of net worth data for each sub-card

**Key data sources already available in the component:**
- `netWorthData` -> array of `{month, bank_balance, investment_value, net_worth}`
- `bankBalances` -> array of `{account_name, provider, balance}`
- `portfolioAnalysis` -> `{investments: [{name, current_balance}], total_value}`
- `overview` -> `{total_income, total_expenses, total_investments}`

**Step 2: Verify the page renders**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

**Step 3: Visual verification**

Start dev server, navigate to `/`, enable Demo Mode, verify:
- Net worth number displayed prominently
- Month-over-month change shown with arrow + percentage
- Three sub-cards showing Bank Balance, Investments, Cash
- Sparklines rendering in each sub-card

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(ui): rewrite dashboard header with net worth hero and sparklines"
```

---

## Task 6: Dashboard - Monthly Spending Gauge Section

Add the "This Month" spending gauge and mini budget cards below the header.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add budget data query**

The dashboard currently doesn't fetch budget data. Add:
```typescript
const today = new Date();
const { data: budgetAnalysis } = useQuery({
  queryKey: ["budgetAnalysis", today.getFullYear(), today.getMonth() + 1, false],
  queryFn: () =>
    budgetApi.getAnalysis(today.getFullYear(), today.getMonth() + 1, false).then((res) => res.data),
});
```

Import `budgetApi` from `../../services/api`.

**Step 2: Build the Monthly Spending Gauge section**

Using the budget analysis data:
- `budgetAnalysis.total_budget` -> total budget limit
- `budgetAnalysis.total_spent` -> total spent amount
- `budgetAnalysis.rules` -> array of budget rules with `{name, category, tags, budget_amount, spent_amount}`

Render:
1. Section header: "This Month - [Month Name Year]" + days remaining
2. `SemiGauge` component with total spent vs total budget
3. Grid of mini budget cards (2-4 columns responsive) showing each rule's progress
   - Each card: emoji icon (from `taggingApi.getIcons()`), rule name, spent/budget, thin progress bar
   - Color coding: green (<75%), amber (75-100%), red (>100%)
   - Skip "Other Expenses" catch-all (it's the last rule, name contains "Other")
   - "View All" link that navigates to `/budget`

Also add an `taggingApi.getIcons()` query to get category emoji icons:
```typescript
const { data: categoryIcons } = useQuery({
  queryKey: ["category-icons"],
  queryFn: () => taggingApi.getIcons().then((res) => res.data),
});
```

**Step 3: Verify rendering**

Run: `cd frontend && npm run build`
Start dev server, verify gauge and budget cards render with demo data.

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(ui): add monthly spending gauge and mini budget cards to dashboard"
```

---

## Task 7: Dashboard - Recent Transactions Feed

Add a compact bank-app-style transaction feed below the gauge section.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Add transactions query**

Add a query for recent transactions (already available via API):
```typescript
const { data: recentTransactions } = useQuery({
  queryKey: ["transactions", "all", false],
  queryFn: () => transactionsApi.getAll("all", false).then((res) => res.data),
});
```

Import `transactionsApi` from `../../services/api`.

**Step 2: Build the Recent Transactions section**

Process the transactions:
1. Sort by date descending, take first 7
2. Group by date using relative labels: "Today", "Yesterday", or formatted date (e.g., "Feb 15")
3. For each transaction, show:
   - Category emoji icon (from `categoryIcons`)
   - Description text (truncated to ~40 chars)
   - Category name as colored pill
   - Amount with color (green for positive, red for negative)

Use `date-fns` for relative date formatting (already a dependency):
```typescript
import { isToday, isYesterday, format } from "date-fns";
```

Add "View All Transactions" link at bottom that navigates to `/transactions`:
```tsx
<Link to="/transactions" className="text-sm text-[var(--primary)] hover:underline">
  View All Transactions →
</Link>
```

Import `Link` from `react-router-dom`.

**Step 3: Verify rendering**

Build and visually check that:
- Transactions grouped by date
- Category icons display
- Amounts colored correctly
- "View All" link works

**Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(ui): add recent transactions feed to dashboard"
```

---

## Task 8: Dashboard - Collapsible Insights Section

Move all existing charts into a collapsible "More Insights" accordion at the bottom.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

**Step 1: Wrap existing charts in collapsible sections**

Create a local `InsightSection` component:
```tsx
const InsightSection: React.FC<{
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ title, defaultOpen = false, children }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)]">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 text-left"
      >
        <h3 className="text-lg font-bold">{title}</h3>
        <ChevronDown className={`w-5 h-5 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>
      {isOpen && <div className="px-4 pb-4">{children}</div>}
    </div>
  );
};
```

Move all existing chart sections into `InsightSection` wrappers:
1. "Monthly Expenses" (bar chart + averages) - `defaultOpen={false}`
2. "Net Worth Over Time" (line chart with view toggles) - `defaultOpen={false}`
3. "Cash Flow" (Sankey) - `defaultOpen={false}`
4. "Monthly Income vs Expenses" (grouped bar) - `defaultOpen={false}`
5. "Income by Source" (stacked bar) - `defaultOpen={false}`
6. "Category Breakdown" (pie charts) - `defaultOpen={false}`

Wrap all sections in a container with a header:
```tsx
<div className="space-y-3">
  <h2 className="text-lg font-bold text-[var(--text-muted)]">
    More Insights
  </h2>
  <InsightSection title="Monthly Expenses">...</InsightSection>
  <InsightSection title="Net Worth Over Time">...</InsightSection>
  {/* ... */}
</div>
```

Move "Data Status" and "Live Updates" to a small footer bar or integrate into the header area.

**Step 2: Verify the full dashboard renders**

Run: `cd frontend && npm run build`
Start dev server, verify:
- New header, gauge, and feed render at top
- Charts are collapsed by default
- Expanding each chart shows the original visualization
- No data regressions

**Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(ui): move dashboard charts into collapsible insights sections"
```

---

## Task 9: Transactions Page - Simplify Default View

Reduce information overload in the transactions table.

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx`
- Modify: `frontend/src/pages/Transactions.tsx`

**Step 1: Add column visibility state to TransactionsTable**

In `TransactionsTable.tsx`, add state for visible columns:
```typescript
const [visibleColumns, setVisibleColumns] = useState<Set<string>>(
  new Set(["date", "description", "category", "amount"])
);
```

The "account" column should be hidden by default but toggleable. Add a small gear icon button next to the search bar that opens a dropdown to toggle column visibility.

**Step 2: Style category as colored pill**

In the category column cell rendering, replace the plain text with a styled pill:
```tsx
<span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs">
  {categoryIcon && <span>{categoryIcon}</span>}
  {transaction.category}
  {transaction.tag && <span className="text-[var(--text-muted)]">/ {transaction.tag}</span>}
</span>
```

Fetch category icons in TransactionsTable:
```typescript
const { data: categoryIcons } = useQuery({
  queryKey: ["category-icons"],
  queryFn: () => taggingApi.getIcons().then((res) => res.data),
});
```

**Step 3: Add uncategorized transactions banner to Transactions.tsx**

At the top of the transactions area (above the table), check for uncategorized transactions and show a banner:
```tsx
const uncategorizedCount = transactions?.filter(
  (t: any) => !t.category || t.category === "Uncategorized"
).length ?? 0;

{uncategorizedCount > 0 && (
  <button
    onClick={() => {/* enable Only Untagged filter */}}
    className="w-full bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2 text-sm text-amber-400 hover:bg-amber-500/20 transition-colors"
  >
    <strong>{uncategorizedCount} uncategorized transactions</strong> — click to filter
  </button>
)}
```

**Step 4: Default auto-tagging panel to collapsed**

In `frontend/src/stores/appStore.ts`, change the default:
```typescript
autoTaggingPanelOpen: false,  // was: true
```

**Step 5: Verify**

Run: `cd frontend && npm run build`
Verify: Account column hidden by default, category pills render, uncategorized banner shows, auto-tagging panel collapsed.

**Step 6: Commit**

```bash
git add frontend/src/components/TransactionsTable.tsx frontend/src/pages/Transactions.tsx frontend/src/stores/appStore.ts
git commit -m "feat(ui): simplify transactions default view with column toggle and category pills"
```

---

## Task 10: Budget Page - Summary Header and Compact Progress

Add a big-picture summary strip and make budget rules more scannable.

**Files:**
- Modify: `frontend/src/components/budget/MonthlyBudgetView.tsx`
- Modify: `frontend/src/components/BudgetProgressBar.tsx`

**Step 1: Add summary header strip to MonthlyBudgetView**

After the month navigation and before the rules list, add a metrics strip:

```tsx
const totalSpent = analysis?.rules?.reduce(
  (sum: number, r: any) => sum + Math.abs(r.spent_amount || 0), 0
) ?? 0;
const totalBudget = analysis?.rules?.reduce(
  (sum: number, r: any) => sum + (r.budget_amount || 0), 0
) ?? 0;
const onTrackCount = analysis?.rules?.filter(
  (r: any) => Math.abs(r.spent_amount || 0) <= (r.budget_amount || 0)
).length ?? 0;
const overCount = (analysis?.rules?.length ?? 0) - onTrackCount;
const biggestOverspend = analysis?.rules
  ?.filter((r: any) => Math.abs(r.spent_amount || 0) > (r.budget_amount || 0))
  ?.sort((a: any, b: any) =>
    (Math.abs(b.spent_amount) / b.budget_amount) - (Math.abs(a.spent_amount) / a.budget_amount)
  )?.[0];
const daysLeft = new Date(year, month, 0).getDate() - new Date().getDate();
```

Render as a 4-card horizontal strip:
```
| Total Spent      | Budget Health    | Biggest Overspend | Time Left  |
| ₪11,014/₪12,000 | 4 on track, 2 over | Eating Out (114%) | 6 days   |
```

**Step 2: Make BudgetProgressBar more compact**

In `BudgetProgressBar.tsx`, add a `compact` prop:
```typescript
interface BudgetProgressBarProps {
  // ... existing props
  compact?: boolean;
}
```

When `compact={true}`:
- Render everything on one line: icon + label + progress bar + numbers + status dot
- Remove the sub-label row
- Reduce padding from `p-4` to `py-2 px-4`
- Edit/delete buttons only appear on hover

Use `compact={true}` for the monthly budget rules list by default.

**Step 3: Add status dots**

Add a small colored circle (green/amber/red) next to each rule name in the compact view:
```tsx
<span
  className={`w-2 h-2 rounded-full inline-block ${
    percentage >= 100 ? "bg-rose-500" :
    percentage >= 90 ? "bg-amber-500" : "bg-emerald-500"
  }`}
/>
```

**Step 4: Soften "Other Expenses" styling**

In `MonthlyBudgetView.tsx`, when rendering the "Other Expenses" rule, add a special class:
```tsx
<BudgetProgressBar
  {...props}
  className={rule.name === "Other Expenses" ? "opacity-60 border-dashed" : ""}
/>
```

**Step 5: Verify**

Run: `cd frontend && npm run build`
Verify: Summary strip shows at top of budget page, rules are compact with status dots, "Other Expenses" has softer styling.

**Step 6: Commit**

```bash
git add frontend/src/components/budget/MonthlyBudgetView.tsx frontend/src/components/BudgetProgressBar.tsx
git commit -m "feat(ui): add budget summary header and compact progress bars"
```

---

## Task 11: Data Sources Page - Humanize Labels and Group

Clean up technical jargon and improve organization.

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx`

**Step 1: Import and apply humanization**

At top of DataSources.tsx:
```typescript
import { humanizeService, humanizeProvider } from "../utils/textFormatting";
```

Replace all instances of raw service/provider display:
- `account.service + " Account"` -> `humanizeAccountType(account.service)`
- Raw provider badges -> `humanizeProvider(account.provider)`
- "Credit_cards Account" -> "Credit Card"
- "banks Account" -> "Bank Account"

Search for these patterns in the file and replace:
- `` `${account.service} Account` `` or similar -> `humanizeAccountType(account.service)`
- Provider name display -> `humanizeProvider(account.provider)`

**Step 2: Group accounts by type**

Sort the accounts list into two groups:
```typescript
const bankAccounts = accounts?.filter((a: any) => a.service === "banks") ?? [];
const creditCardAccounts = accounts?.filter((a: any) => a.service === "credit_cards") ?? [];
```

Render with section headers:
```tsx
{bankAccounts.length > 0 && (
  <>
    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2">
      Bank Accounts
    </h3>
    {bankAccounts.map(account => /* existing card */)}
  </>
)}
{creditCardAccounts.length > 0 && (
  <>
    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-4">
      Credit Cards
    </h3>
    {creditCardAccounts.map(account => /* existing card */)}
  </>
)}
```

**Step 3: Add tooltips or text labels to action buttons**

For the icon-only action buttons (Scrape, View, Edit, Delete), add `title` attributes:
```tsx
<button title="Scrape This Source" ...>
<button title="View Details" ...>
<button title="Edit Account" ...>
<button title="Disconnect Account" ...>
```

**Step 4: Verify**

Run: `cd frontend && npm run build`
Verify: "Bank Account" and "Credit Card" labels, grouped sections, tooltips on hover.

**Step 5: Commit**

```bash
git add frontend/src/pages/DataSources.tsx
git commit -m "feat(ui): humanize data sources labels, group by type, add button tooltips"
```

---

## Task 12: Investments Page - Show Balance and Gain/Loss Per Card

Add key financial metrics directly on each investment card.

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

**Step 1: Add balance and gain/loss to InvestmentCard**

The `InvestmentCard` component (around lines 47-207) currently shows interest rate and created date. Add:

1. **Current Balance** - large number at the top of the card, below the title. Source: the investment analysis data or portfolio analysis.
2. **Gain/Loss** - colored amount + percentage below the balance.

The portfolio analysis already provides per-investment data. Pass it down to InvestmentCard:
```typescript
// In the parent, find this investment in portfolio data
const investmentAnalysis = portfolioAnalysis?.investments?.find(
  (i: any) => i.name === investment.name
);
```

Then in the card:
```tsx
{investmentAnalysis && (
  <div className="mt-2">
    <p className="text-2xl font-bold font-mono">
      {formatCurrency(investmentAnalysis.current_balance)}
    </p>
    <p className={`text-sm font-medium ${
      investmentAnalysis.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"
    }`}>
      {investmentAnalysis.profit_loss >= 0 ? "+" : ""}
      {formatCurrency(investmentAnalysis.profit_loss)}
      {investmentAnalysis.roi != null && ` (${investmentAnalysis.roi.toFixed(1)}%)`}
    </p>
  </div>
)}
```

**Step 2: Verify**

Run: `cd frontend && npm run build`
Verify: Each investment card shows current balance and gain/loss.

**Step 3: Commit**

```bash
git add frontend/src/pages/Investments.tsx
git commit -m "feat(ui): show balance and gain/loss on investment cards"
```

---

## Task 13: Categories Page - Alphabetical Sort

Sort category cards alphabetically for easier scanning.

**Files:**
- Modify: `frontend/src/pages/Categories.tsx`

**Step 1: Sort categories**

In Categories.tsx, find where categories are mapped to render cards. Add sorting:
```typescript
const sortedCategories = Object.entries(categories ?? {}).sort(([a], [b]) =>
  a.localeCompare(b)
);
```

Use `sortedCategories` in the map instead of `Object.entries(categories)`.

**Step 2: Verify**

Run: `cd frontend && npm run build`
Verify: Categories render in alphabetical order.

**Step 3: Commit**

```bash
git add frontend/src/pages/Categories.tsx
git commit -m "feat(ui): sort categories alphabetically"
```

---

## Task 14: Sidebar - Notification Badges

Add attention indicators to sidebar nav items.

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Step 1: Add API queries for badge data**

In Sidebar.tsx, add queries for uncategorized transaction count and stale data sources:

```typescript
import { useQuery } from "@tanstack/react-query";
import { transactionsApi, scrapingApi } from "../../services/api";

// Count uncategorized transactions
const { data: allTransactions } = useQuery({
  queryKey: ["transactions", "all", false],
  queryFn: () => transactionsApi.getAll("all", false).then((res) => res.data),
  staleTime: 5 * 60 * 1000,
});

const uncategorizedCount = allTransactions?.filter(
  (t: any) => !t.category || t.category === "Uncategorized"
).length ?? 0;

// Check for stale data sources (>7 days since scrape)
const { data: lastScrapes } = useQuery({
  queryKey: ["last-scrapes"],
  queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
  staleTime: 5 * 60 * 1000,
});

const staleSourceCount = lastScrapes?.filter((s: any) => {
  if (!s.last_scrape_date) return true;
  const daysSince = (Date.now() - new Date(s.last_scrape_date).getTime()) / (1000 * 60 * 60 * 24);
  return daysSince > 7;
}).length ?? 0;
```

**Step 2: Add badge rendering to nav items**

Modify the nav item rendering to support a badge:
```tsx
const getBadge = (path: string): number | null => {
  if (path === "/transactions" && uncategorizedCount > 0) return uncategorizedCount;
  if (path === "/data-sources" && staleSourceCount > 0) return staleSourceCount;
  return null;
};
```

In the nav item JSX:
```tsx
{badge != null && (
  <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold px-1">
    {badge > 99 ? "99+" : badge}
  </span>
)}
```

Make each nav item `relative` positioned to support absolute badge positioning.

**Step 3: Verify**

Run: `cd frontend && npm run build`
Verify: Badge appears on Transactions nav item when uncategorized transactions exist. Badge on Data Sources when sources are stale.

**Step 4: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(ui): add notification badges to sidebar nav items"
```

---

## Task 15: Global - Apply Humanization Throughout

Apply the humanization utility across all remaining files that display raw service/provider names.

**Files:**
- Modify: `frontend/src/components/TransactionsTable.tsx` (account column, provider display)
- Modify: `frontend/src/pages/Transactions.tsx` (service filter buttons)
- Modify: `frontend/src/components/budget/TransactionCollapsibleList.tsx` (if it shows account/provider)
- Modify: `frontend/src/pages/Investments.tsx` (provider badges)

**Step 1: Update TransactionsTable account column**

Import `humanizeProvider` and use it wherever `transaction.provider` is displayed in the table cells.

**Step 2: Update Transactions.tsx service filter buttons**

The service filter buttons currently show: "Credit Card", "Bank", "Cash", "Investments", "Refunds". These are already human-readable text - verify they're consistent with our humanization.

**Step 3: Update any other raw provider/service displays**

Search the codebase for raw provider names and apply `humanizeProvider()`:
- `transaction.provider` displays
- `account.provider` displays
- `account.service` displays

**Step 4: Verify**

Run: `cd frontend && npm run build`
Spot-check across pages that no raw identifiers like `credit_cards`, `hapoalim`, `onezero` appear in the UI.

**Step 5: Commit**

```bash
git add -A frontend/src/
git commit -m "feat(ui): apply label humanization across all components"
```

---

## Task 16: Global - Replace Loading Text with Skeletons

Replace "Loading..." text throughout the app with the Skeleton component.

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Transactions.tsx`
- Modify: `frontend/src/pages/DataSources.tsx`
- Modify: `frontend/src/components/budget/MonthlyBudgetView.tsx`
- Modify: `frontend/src/pages/Investments.tsx`
- Modify: `frontend/src/pages/Categories.tsx`

**Step 1: Find all loading states**

Search for `Loading...`, `isLoading`, and loading conditional renders across all page components.

**Step 2: Replace with Skeleton component**

Import and use `Skeleton` where appropriate:
```tsx
import { Skeleton } from "../components/common/Skeleton";

// Where you see: {isLoading && <p>Loading...</p>}
// Replace with: {isLoading && <Skeleton variant="card" className="h-32" />}

// For chart loading:
// {isLoading && <Skeleton variant="chart" />}

// For text loading:
// {isLoading && <Skeleton variant="text" lines={3} />}
```

**Step 3: Verify**

Run: `cd frontend && npm run build`
Verify: Animated skeleton placeholders appear during loading instead of "Loading..." text.

**Step 4: Commit**

```bash
git add -A frontend/src/
git commit -m "feat(ui): replace loading text with skeleton placeholders"
```

---

## Task 17: Final Polish and Verification

End-to-end visual verification of all changes.

**Step 1: Full build**

Run: `cd frontend && npm run build`
Expected: Clean build with no errors or warnings.

**Step 2: Lint check**

Run: `cd frontend && npm run lint`
Expected: No new lint errors.

**Step 3: Visual walkthrough**

Start both servers, enable Demo Mode, and verify each page:

1. **Dashboard:** Net worth header, gauge, mini budget cards, recent transactions, collapsible insights
2. **Transactions:** Simplified columns, category pills, uncategorized banner, collapsed auto-tagging
3. **Budget:** Summary strip, compact progress bars, status dots, softened "Other Expenses"
4. **Data Sources:** Humanized labels, grouped by type, button tooltips
5. **Investments:** Balance and gain/loss on cards
6. **Categories:** Alphabetical sort
7. **Sidebar:** Notification badges

**Step 4: Final commit**

If any polish needed:
```bash
git add -A frontend/src/
git commit -m "fix(ui): final polish from visual walkthrough"
```
