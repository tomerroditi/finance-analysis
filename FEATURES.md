# Finance Analysis Dashboard — Features

Single source of truth for all features supported by the application.

## Overview

Personal finance tracking and analysis system for Israeli financial institutions. Automates data collection from banks, credit cards, and insurance providers. Provides intelligent expense categorization, budgeting, investment tracking, debt management, and early retirement planning.

**Tech Stack:** FastAPI (Python) backend + React 19 frontend, SQLite database, Playwright-based scraping.

---

## 1. Financial Dashboard

The main overview page with at-a-glance financial health metrics.

### KPI Cards
- **Net Worth** — total assets minus liabilities, with month-over-month delta
- **Bank Balance** — sum across all connected bank accounts, expandable per-account breakdown
- **Total Investments** — portfolio value based on transaction totals, expandable per-investment
- **Cash Balance** — sum across all cash envelopes

### Charts
- **Income vs Expenses** — monthly bar chart with toggleable filters (exclude projects, liabilities, refunds)
- **Net Worth Over Time** — line chart with views: all, bank only, investments only, net worth, debt payments
- **Income by Source** — stacked bar chart by income category/tag
- **Expenses by Category Over Time** — stacked bar showing spending trends per category
- **Monthly Expenses** — bar chart with 3/6/12-month rolling averages
- **Sankey Diagram** — money flow from income sources through categories to tags
- **Budget Spending Gauge** — current month budget utilization
- **Recent Transactions Feed** — last N transactions at a glance
- **Portfolio Allocation** — pie chart of investment distribution

---

## 2. Transaction Management

Full-featured transaction table with advanced filtering, sorting, and bulk operations.

### Viewing & Filtering
- **Service tabs:** All, Banks, Credit Cards, Cash, Manual Investments, Refunds
- **Text search** across description, category, tag, provider, account
- **Filter by:** account/provider, category, tag (dependent dropdowns), amount range, date range
- **Toggle:** show only untagged transactions, include/exclude split parents
- **Sorting:** by date, account, description, category, amount (asc/desc)
- **Pagination:** configurable rows per page (10, 50, 100, 500, 1000)

### Transaction Actions
- **Edit** — modify description, category, tag, amount, date, account name
- **Delete** — remove manually-created transactions (cash, manual investments)
- **Create** — add new cash or manual investment transactions via modal
- **Split** — divide one transaction into multiple category/tag portions
- **Revert Split** — undo a split and restore the original transaction

### Bulk Operations
- **Multi-select** — checkbox selection with "select all on page"
- **Bulk edit** — update category, tag, description, date, amount, or account for selected transactions

### Refund Tracking
- **Mark as Pending Refund** — flag a transaction as expecting a refund
- **Link Refund** — associate an actual refund transaction with a pending refund
- **Unlink Refund** — remove a refund link
- **Close Refund** — accept partial refund and mark as resolved
- **Refunds View** — dedicated tab showing all pending/partial/resolved/closed refunds

### Cash Envelope Management
- **View** all cash envelopes with balances
- **Add** new cash envelope (name + starting balance)
- **Edit** envelope balance
- **Delete** envelope with confirmation
- **Migration** — auto-migrate legacy cash data format on first load

---

## 3. Auto-Tagging Rules

Priority-based rule engine for automatic transaction categorization.

### Rule Builder
- **Conditions** — field-based matching: description (contains, equals, starts_with, ends_with), amount (gt, lt, gte, lte, between), provider, account, source
- **Logical Operators** — AND/OR grouping with nested subconditions
- **Priority** — higher priority rules evaluated first, first match wins
- **Preview** — see which transactions would match before applying
- **Conflict Detection** — validate rules against existing rules for overlaps
- **Apply** — run rules against all untagged transactions (or overwrite existing tags)
- **Apply Single Rule** — run one specific rule

### Auto-Tagging Panel
- Desktop sidebar panel on Transactions page
- Create, edit, delete rules
- Test rule conditions against transaction data
- Apply all rules or individual rules

---

## 4. Budget Planning

### Monthly Budgets
- **Budget rules** — spending limit per category for a specific month
- **Spending gauges** — visual progress bars showing budgeted vs actual spending
- **Transaction breakdown** — expand a category to see its transactions for the month
- **Copy rules** — duplicate all rules from a previous month
- **Total Budget** — special "category" for overall monthly spending limit
- **CRUD** — create, edit, delete budget rules via modal

### Project-Based Budgets
- **Projects** — time-limited budgets for specific spending goals (e.g., "Home Renovation")
- **Project tracking** — budget vs actual spending with gauge visualization
- **Transaction list** — all transactions tagged to the project
- **CRUD** — create, edit, delete projects

---

## 5. Category & Tag Management

Hierarchical organization system for transactions.

### Categories
- **List** all categories with assigned emoji icons
- **Create** new category (with optional initial tags)
- **Rename** category (cascades to all tagged transactions)
- **Delete** category (nullifies tagged transactions)
- **Emoji icon** — assign/change per-category icon via emoji picker (200+ options, searchable)

### Tags (Sub-categories)
- **List** tags nested under each category
- **Create** new tag within a category
- **Rename** tag (cascades to all tagged transactions)
- **Delete** tag (nullifies tagged transactions)
- **Relocate** — move tag from one category to another

### Protected Items
- **Protected categories:** Salary, Other Income, Investments, Ignore, Liabilities, Credit Cards
- **Protected tags:** Prior Wealth

---

## 6. Investment Portfolio Tracking

### Investment Management
- **Create** investment with type (stocks, crypto, bonds, real estate, pension, savings, other)
- **Edit** investment details (name, category, tag, type, interest rate, notes)
- **Close** investment (records close date, creates 0-balance snapshot)
- **Reopen** closed investment
- **Delete** investment with confirmation
- **Toggle** show/hide closed investments

### Balance Snapshots
- **Manual entry** — add/edit/delete balance observations at specific dates
- **Fixed-rate auto-calculation** — daily compounding for bonds/pensions with known interest rate
- **Snapshot sources:** manual, calculated, scraped (future)
- **Resolution:** snapshot-first, transaction-based fallback

### Analytics
- **Profit/Loss** — current value vs net invested
- **ROI** — return on investment percentage
- **CAGR** — compound annual growth rate
- **Total deposits/withdrawals** breakdown
- **Balance history chart** — line chart with interpolation between snapshots

### Portfolio Overview
- **Allocation pie chart** — percentage breakdown by investment
- **Balance history** — multi-line chart showing all investments over time
- **Total portfolio value** and aggregate P&L

---

## 7. Debt/Liability Management

### Liability Tracking
- **Create** liability with: name, lender, principal, interest rate, term (months), start date, notes, category, tag
- **Edit** liability details
- **Mark as Paid Off** (with date) / Reopen
- **Delete** with confirmation
- **Toggle** show/hide paid-off liabilities

### Amortization & Analysis
- **Amortization schedule** — payment breakdown (principal portion, interest portion, remaining balance)
- **Actual vs expected payments** — compare scheduled vs real transactions
- **Payment history** — linked transactions for the liability
- **Auto-detect transactions** — find existing bank transactions matching the liability's tag
- **Generate transactions** — auto-create missing payment transactions from schedule

### Debt Overview
- **Progress bar** — percentage of principal paid
- **Summary stats:** loan amount, remaining balance, monthly payment, total interest cost
- **Debt over time chart** — stacked area showing remaining balance per liability

---

## 8. FIRE Calculator (Early Retirement)

Financial Independence, Retire Early planning with Israeli-specific retirement vehicles.

### Goal Configuration
- Current age, gender, target retirement age, life expectancy
- Monthly expenses in retirement
- Inflation rate, expected return rate, withdrawal rate (4% rule default)
- Pension monthly payout estimate
- Keren Hishtalmut balance + monthly contribution
- Bituach Leumi (national insurance) eligibility + monthly estimate
- Other passive income sources

### Projections
- **FIRE number** — capital needed for financial independence
- **Years to FIRE** — based on current savings rate
- **FIRE age** — projected retirement age
- **Earliest possible retirement age** — best-case scenario
- **Monthly savings needed** — to reach goal
- **Progress %** — towards FIRE number
- **Readiness status:** on_track, close, off_track
- **Portfolio depleted age** — pessimistic scenario

### Charts
- **Net worth projection** — optimistic / baseline / conservative scenarios
- **Income projection in retirement** — stacked: salary savings, portfolio withdrawal, pension, Bituach Leumi, passive income vs expenses

### AI Suggestions
- Recommended adjustments when off-track (target age, monthly expenses, return rate, life expectancy)

---

## 9. Data Sources & Scraping

### Credential Management
- **3-step wizard:** select service → select provider → enter credentials
- **Supported services:** Banks, Credit Cards, Insurance
- **Supported banks (11):** Hapoalim, Leumi, Discount, Mizrahi, Mercantile, Otsar Hahayal, Union, Beinleumi, Massad, Yahav, OneZero
- **Supported credit cards (6):** Max, Visa Cal, Isracard, Amex, Beyahad Bishvilha, Behatsdaa
- **Supported insurance (1):** Hafenix
- **View** saved credentials (password masked, toggle visibility)
- **Edit** existing credentials
- **Delete** credential with confirmation

### Scraping
- **Start scrape** for individual account with configurable period (2 weeks to 12 months, or auto)
- **Scrape all** accounts at once
- **2FA support** — enter OTP code when prompted, resend option
- **Abort** in-progress scrape
- **Last scrape date** — displayed per account
- **Daily rate limit** — one scrape per account per day
- **5-minute timeout** per scrape job

### Bank Balance Entry
- **View** all bank accounts with balances
- **Manual balance entry** — set current balance (triggers prior wealth recalculation)
- **Display:** provider, account name, last manual update, last scrape date

---

## 10. Insurance Tracking (Prototype)

Basic read-only view of scraped insurance account data.

- Policy ID, type, pension type
- Account balance and balance date
- Investment tracks
- Commission rates (deposits %, savings %)
- Insurance covers and costs
- Liquidity date

---

## 11. Analytics Engine

Backend analytics powering the dashboard and reports.

### Endpoints
- **Overview** — total income, expenses, investments, net balance change
- **Income/Expenses Over Time** — monthly breakdown with project/liability/refund filters
- **Debt Payments Over Time** — monthly debt payment totals by tag
- **Expenses by Category** — pie chart data with expense/refund split
- **Expenses by Category Over Time** — monthly category breakdown
- **Net Balance Over Time** — cumulative balance trend
- **Net Worth Over Time** — bank balance + investment value + cash over time
- **Income by Source Over Time** — income broken down by category/tag
- **Monthly Expenses** — with 3/6/12-month rolling averages
- **Sankey Data** — full money flow with CC gap calculation

### Credit Card Deduplication
- Aggregate totals use bank transactions only (exclude CC source)
- Category breakdowns use itemized CC transactions (exclude "Credit Cards" bank category)
- Sankey uses both sources to calculate CC gap

---

## 12. Internationalization

### Bilingual Support
- **Languages:** English (default) and Hebrew
- **RTL support** — automatic direction switching with logical CSS properties
- **All strings** use i18next translation keys — no hardcoded text
- **Number formatting** — locale-aware currency (₪) and date display
- **Provider names** — bilingual label maps for all financial institutions

---

## 13. Responsive Design

### Mobile Support
- **Mobile-first** Tailwind CSS with responsive breakpoints
- **Sidebar** — fixed on desktop, drawer overlay on mobile
- **Tables** — hide non-essential columns, tap-to-reveal action bars
- **Charts** — responsive Plotly with touch-optimized hover
- **Modals** — full-width on mobile, constrained on desktop
- **Touch targets** — minimum 32px for all interactive elements
- **iOS safe areas** — notch and Dynamic Island support
- **Viewport** — dynamic viewport height (dvh) for mobile browsers

---

## 14. Demo Mode

Isolated testing environment with sample data.

- **Toggle** via header button
- **Separate database** — demo data copied from bundled template
- **Date-shifted** — all dates relative to current date
- **Test credentials** — pre-seeded bank and credit card accounts (with/without 2FA)
- **No production data affected** — completely isolated environment

---

## 15. Backup & Restore

- **Create backup** — snapshot of current database
- **List backups** — all available backups with size and date
- **Restore** — revert to a previous backup (creates safety backup first)

---

## 16. Global Search

- **Cmd+K / Ctrl+K** shortcut to open search overlay
- Quick navigation across all pages and features
