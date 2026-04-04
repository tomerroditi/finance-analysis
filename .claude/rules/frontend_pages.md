---
paths:
  - "frontend/src/pages/**/*.{ts,tsx}"
---

# Frontend Pages - Route Views

## Purpose
Pages are top-level views mapped to routes. They orchestrate layout, compose feature components, and manage page-level data fetching. Pages should be thin — delegate complex UI to sub-components in `components/<feature>/`.

## Current Pages

| Page | Route | Description |
|------|-------|-------------|
| `Dashboard.tsx` | `/` | Overview with KPIs, charts, budget section, recent transactions feed |
| `Transactions.tsx` | `/transactions` | Full transaction table with filters, bulk actions, auto-tagging |
| `Budget.tsx` | `/budget` | Monthly + project budget views with rules and spending gauges |
| `Categories.tsx` | `/categories` | Category/tag management with drag-and-drop reordering |
| `Investments.tsx` | `/investments` | Investment portfolio with balance charts and profit/loss |
| `DataSources.tsx` | `/data-sources` | Bank/CC account management and scraping triggers |
| `Liabilities.tsx` | `/liabilities` | Loan/debt tracking |
| `Insurances.tsx` | `/insurances` | Insurance policy tracking |
| `EarlyRetirement.tsx` | `/retirement` | FIRE calculator |

Pages are registered in `App.tsx` with `react-router-dom` and rendered inside the `Layout` component.

## What Pages DO:
- Compose feature components from `components/<feature>/`
- Read route parameters (`useParams`, `useSearchParams`)
- Fetch page-level data with React Query hooks
- Manage page-level state (selected tab, date range, etc.)

## What Pages DO NOT DO:
- Complex UI rendering — delegate to components
- Direct axios calls — use `services/api.ts` or custom hooks
- Business logic — belongs in backend services

## Pattern: Extracting Page Sections

When a page grows beyond ~500 lines, extract self-contained sections into `components/<feature>/`:
```
Dashboard.tsx (~1000 lines) delegates to:
  ├── components/dashboard/BudgetSection.tsx (~400 lines)
  ├── components/dashboard/RecentTransactionsSection.tsx (~470 lines)
  └── components/dashboard/DashboardInsightsPanel.tsx
```
The page file becomes an orchestrator that wires sections together with shared state and data.
