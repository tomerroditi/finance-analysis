# Expenses Category Breakdown Redesign

**Date:** 2026-03-02
**Scope:** Dashboard "Categories" insight tab

## Problem

The current expenses-by-category view uses two Plotly donut charts (expenses + refunds) with only 5 color shades each. With 15+ categories this is unreadable — tiny slices, overlapping labels, no amounts visible without hovering.

## Design

Replace the two Plotly donuts with a custom HTML/CSS horizontal bar chart that integrates with the existing Tailwind design system.

### Layout (top to bottom)

**1. Summary Strip** — 3 compact stat cards in a row:
- **Total Expenses** (rose accent): sum of all expense amounts, formatted ILS
- **Top Category**: icon + name + amount of the largest expense category
- **# Categories**: count of distinct expense categories

**2. Expenses Bar Chart** — sorted descending by amount:
- Each row: `[icon] [category name] [===colored bar===] [amount] [percentage]`
- Bar width proportional to the largest category (largest = 100%)
- Bar color: rose-500 gradient
- All categories shown (scrollable container if >12 rows)
- Amounts formatted as ILS currency, percentages in muted text

**3. Refunds Section** (conditional) — shown only when refunds exist:
- Green-themed (emerald) horizontal bars, same layout as expenses
- "Refunds" header with green accent
- Smaller/compact compared to expenses section

### Key Decisions

- **Custom HTML bars, not Plotly** — lighter, handles 15+ categories, integrates with Tailwind
- **Reuse `categoryIcons`** — emoji icons already fetched via `taggingApi.getIcons()`
- **Scrollable** — `max-h-[400px] overflow-y-auto` to contain long lists
- **Backend unchanged** — existing `get_expenses_by_category()` returns exactly the data needed

### Files to Modify

- `frontend/src/pages/Dashboard.tsx` — replace the `insightTab === "category"` section (lines 1407-1495)

### No Backend Changes

The existing API returns `{ expenses: [{category, amount}], refunds: [{category, amount}] }` which is sufficient.
