# UI/UX Redesign - Dashboard-First Approach

## Context

The Finance Analysis Dashboard is a personal finance tracking system designed for daily use. It currently serves as a power-user analytics tool, but the goal is to make it accessible to non-technical users (family, friends) who want a **daily quick glance** at their financial health.

### User Profile
- Non-technical users who open the app daily for a quick financial check
- Comfort level: similar to a banking app (Caspion, Max, One Zero)
- No interest in raw data tables or complex chart configurations

### Key Pain Points
1. **Transaction table is overwhelming** - too much raw data, technical labels, dense columns
2. **Budget lacks a "big picture"** - can't quickly answer "am I on track this month?" without scrolling through every rule
3. **Technical jargon** visible everywhere ("Credit_cards Account", "banks Account", raw tag syntax)
4. **Icon-only buttons** throughout the app with no labels or tooltips

### Constraints
- Dark theme stays (no light mode)
- All features remain accessible (nothing hidden permanently)
- Complete navigation rethink is welcome

---

## Design: Dashboard-First Redesign

The dashboard becomes the single page that answers "how am I doing?" at a glance. Other pages get targeted improvements to reduce friction. All changes are frontend-only (no backend API changes needed).

---

### 1. Dashboard Redesign (Major)

Replace the current chart-heavy dashboard with a "This Month" focused overview.

#### 1a. Financial Health Header

Top section with the big numbers users care about:

```
+------------------------------------------------------------------+
|  NET WORTH                        +/-  Month-over-Month Change   |
|  ₪513,071                         ↑ ₪12,340 (+2.5%)             |
+------------------------------------------------------------------+
|  Bank Balance    |  Investments     |  Cash                      |
|  ₪31,538         |  ₪481,534       |  ₪0                        |
|  ~~sparkline~~   |  ~~sparkline~~   |  ~~sparkline~~             |
+------------------------------------------------------------------+
```

- Net Worth is the hero number, large and prominent
- Month-over-month change shown as arrow + amount + percentage
- Three sub-cards for Bank, Investments, Cash with mini sparklines showing 6-month trend
- Bank Balance sub-card expands on hover to show per-account breakdown (existing behavior, preserved)

#### 1b. Monthly Spending Gauge (Hero Section)

A visual "am I on track?" indicator - the most important section for daily use:

```
+------------------------------------------------------------------+
|  THIS MONTH - February 2026                     6 days remaining |
|                                                                  |
|            [====== SEMICIRCULAR GAUGE ======]                    |
|                    ₪11,014 / ₪12,000                             |
|                      91.8% used                                  |
|                                                                  |
|  +----------+  +----------+  +----------+  +----------+         |
|  | Groceries|  | Eating   |  | Gas      |  | Bills    |         |
|  | ₪1,196   |  | Out      |  | ₪640     |  | ₪559     |         |
|  | /₪2,000  |  | ₪1,136   |  | /₪1,000  |  | /₪5,000  |         |
|  | [====  ] |  | /₪1,000  |  | [====  ] |  | [=     ] |         |
|  | 60% [G]  |  | [=======]|  | 64% [G]  |  | 11% [G]  |         |
|  +----------+  | 114% [R] |  +----------+  +----------+         |
|                 +----------+                                     |
+------------------------------------------------------------------+
```

- Large semicircular gauge showing total spent vs total budget
- Color transitions: green (<75%) -> amber (75-100%) -> red (>100%)
- "Days remaining" in the month provides urgency context
- Below the gauge: **mini budget cards** in a responsive 2-4 column grid
  - Each shows: category name, category icon (emoji), spent/limit, thin progress bar, status color
  - Only budget rules the user has set up are shown (not "Other Expenses")
  - Cards are clickable - navigate to Budget page with that rule expanded
  - Max 8 cards visible without scrolling; if more rules exist, show "View All Budget Rules" link

#### 1c. Recent Transactions Feed

A compact list of the last 7 transactions, styled like a bank app statement:

```
+------------------------------------------------------------------+
|  RECENT TRANSACTIONS                        View All →           |
|                                                                  |
|  Today                                                           |
|  🏠 הברה מהפועלים/ארגמן שיר    Ignore     +₪2,500  green       |
|  💰 מ.משרבט תגמולי              Other Inc   +₪687   green       |
|                                                                  |
|  Yesterday                                                       |
|  🍕 נונמימי כיכר המושבה          Food       -₪50    red         |
|  💅 PAYBOX                       Beauty     -₪120   red         |
|  🍻 לומה חומוס בר יין בע        Food       -₪115   red         |
|  💊 סופר פארם תל מונד 96         Health     -₪149   red         |
|  👕 נעלי ריצן תל מונד            Shopping   -₪299   red         |
+------------------------------------------------------------------+
```

- Grouped by date ("Today", "Yesterday", "Feb 15")
- Each row: category icon (emoji from categories page), description, category name, amount
- Positive amounts in green, negative in red
- "View All" link navigates to Transactions page
- No checkboxes, no action buttons - this is read-only for quick scanning

#### 1d. Insights Section (Collapsed by Default)

A collapsible "More Insights" accordion that contains the current dashboard charts:

- **Monthly Expenses** bar chart (with averages)
- **Net Worth Over Time** line chart
- **Cash Flow** Sankey diagram
- **Monthly Income vs Expenses** comparison
- **Income by Source** stacked bar
- **Category Breakdown** pie charts

Each chart is in its own collapsible sub-section so users can open only what they want. The Sankey is particularly large and should be collapsed by default.

The Data Status / Live Updates indicator moves to the header area (small badge near Demo Mode toggle).

---

### 2. Transactions Page (Medium Changes)

#### 2a. Simplified Default View
- **Remove "Account" column by default.** Add a column visibility toggle (gear icon) that lets users show/hide columns.
- **Default visible columns:** Date, Description, Category/Tag, Amount
- Category shown as a **colored pill** with the category's emoji icon (e.g., `🍕 Food / Restaurants`) instead of plain text

#### 2b. Untagged Transactions Highlight
- When uncategorized transactions exist, show a prominent banner: "**12 uncategorized transactions** - click to filter"
- Clicking it activates the "Only Untagged" filter automatically
- This replaces the subtle checkbox that's easy to miss

#### 2c. Cleaner Action Buttons
- The service filter buttons (All, Credit Card, Bank, Cash, Investments, Refunds) get subtle icons next to their text
- Search bar gets more visual prominence (slightly larger, centered above table)

#### 2d. Auto Tagging Panel
- Default to **collapsed** (just show the toggle button)
- When open, keep existing behavior

---

### 3. Budget Page (Medium Changes)

#### 3a. Summary Header Strip

Add a horizontal metrics strip above the month navigation:

```
+------------------------------------------------------------------+
|  ₪11,014 / ₪12,000  |  4 on track  |  Biggest: Eating  |  6 days |
|  Total Spent          |  2 over      |  Out (114%)       |  left   |
+------------------------------------------------------------------+
```

Four cards showing:
1. Total spent vs total budget (with mini progress bar)
2. On track / over budget count (green/red numbers)
3. Biggest overspend category (name + percentage)
4. Days remaining in month

#### 3b. Compact Progress List

Each budget rule takes **one line** instead of two:
```
Before:
  v  Groceries                                      1196.33 / 2000.00
     FOOD                                          View Transactions
  [===============================                              ]

After:
  🍕 Groceries  [=========60%========                ] ₪1,196 / ₪2,000  [G]
```

- Category icon (emoji) + name on the left
- Inline progress bar in the middle
- Numbers on the right
- Status dot (green/amber/red) at the end
- Edit/delete buttons appear on hover only
- Expand arrow still works to show transactions

#### 3c. "Other Expenses" Treatment
- Show "Other Expenses" with a muted/softer visual style (e.g., dashed progress bar border, lighter text)
- This signals it's a catch-all, not a specific budget rule, reducing alarm when it's "over budget"

---

### 4. Data Sources Page (Light Changes)

#### 4a. Humanize Labels
- "banks Account" -> "Bank Account"
- "credit_cards Account" -> "Credit Card"
- "Credit_cards" badge -> "Credit Card"

#### 4b. Group by Account Type
Add section headers:
```
BANK ACCOUNTS
  [Shir - Hapoalim card]
  [Shir & Tomer - OneZero card]
  [Tomer - OneZero card]

CREDIT CARDS
  [Shir & Tomer - Isracard card]
  [Tomer - Isracard card]
  [Tomer - Max card]
```

#### 4c. Action Button Labels
Replace the 5 icon-only buttons with labeled buttons or add tooltips:
- Play icon -> "Scrape" (or tooltip)
- Eye icon -> "View" (or tooltip)
- Pen icon -> "Edit" (or tooltip)
- Trash icon -> "Remove" (or tooltip)
- Dollar icon -> "Set Balance" (or tooltip)

---

### 5. Investments Page (Light Changes)

- Show **current balance** prominently on each investment card (large number)
- Show **gain/loss** per card (amount + percentage, colored green/red)
- These values already exist in the data (from calculate_profit_loss) but aren't shown on the card view

---

### 6. Categories Page (Light Changes)

- Sort categories **alphabetically** by default
- No other changes needed - the card grid works well

---

### 7. Global Improvements

#### 7a. Sidebar Badges
Add notification badges to sidebar nav items:
- **Transactions:** Show count of uncategorized transactions (e.g., red "12" badge)
- **Data Sources:** Show indicator if any source hasn't been scraped in >7 days

#### 7b. Label Humanization (Global)
Throughout the entire app, replace technical identifiers with human-readable text:
- `credit_cards` -> "Credit Card"
- `banks` -> "Bank"
- `manual_investments` -> "Investment"
- `cash` -> "Cash"
- Provider names: `hapoalim` -> "Hapoalim", `onezero` -> "One Zero", `isracard` -> "Isracard", `max` -> "Max"

#### 7c. Loading States
Replace "Loading..." text with skeleton loading animations (gray pulsing rectangles matching content shape).

#### 7d. Consistent Button Styling
Audit all icon-only buttons throughout the app. Any button that performs a destructive or important action must have a text label or a tooltip.

---

## Non-Goals

- No light mode
- No backend API changes
- No new features (this is purely UI/UX improvement)
- No changes to business logic or calculations
- No mobile-specific (responsive) redesign beyond what exists
- No changes to the Sankey chart implementation (Plotly stays)

## Technical Approach

All changes are frontend-only:
- New/modified React components
- Tailwind CSS styling changes
- New API calls only where existing endpoints already return the needed data
- The semicircular gauge can be built with SVG or CSS (no new chart library needed)
- Sparklines can use simple inline SVG (no new library)
- Skeleton loading can use Tailwind's `animate-pulse` utility

## Estimated Scope

| Area | Effort | Files Affected |
|------|--------|---------------|
| Dashboard redesign | Large | Dashboard.tsx (rewrite), new sub-components |
| Transactions improvements | Medium | TransactionsTable.tsx, Transactions.tsx |
| Budget improvements | Medium | Budget.tsx, BudgetProgressBar.tsx |
| Data Sources cleanup | Small | DataSources.tsx |
| Investments polish | Small | Investments.tsx |
| Categories sort | Trivial | Categories.tsx |
| Global improvements | Medium | Sidebar.tsx, various components, api.ts |
