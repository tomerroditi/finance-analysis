# Moneytor Feature Parity Plan

**Date:** 2026-03-02
**Source:** https://moneytor.co.il/en/
**Goal:** Identify features from Moneytor that we don't have and plan their integration.

---

## Features We Already Have

| Feature | Our Implementation |
|---------|-------------------|
| Bank & CC auto-scraping | israeli-bank-scrapers integration with 2FA |
| Net worth over time | Chart with bank balance + investment lines |
| Investment tracking | Accounts, P&L, balance snapshots, fixed-rate compounding |
| Cash flow tracking | Income vs expenses, Sankey diagram |
| Budgeting | Monthly per-category + project budgets |
| Category/tag management | Hierarchical categories with auto-tagging rules |
| Manual transaction entry | Cash & manual investment transactions |
| Dashboard overview | KPI cards, multiple chart types |
| Expense breakdown | By category pie chart |
| Income by source | Stacked bar chart over time |

---

## Features To Add (Gap Analysis)

### 1. Multi-Currency Support
**What Moneytor does:** Full support for all currency exchange rates. Assets in different currencies are converted to a base currency for unified net worth view.

**Integration approach:**
- Add a `currency` field to transactions, investments, and balance records
- Create a `CurrencyService` that fetches daily exchange rates (Bank of Israel API or similar)
- Store exchange rates in a `currency_rates` table for historical lookups
- All KPI calculations convert to base currency (ILS) before aggregation
- UI shows amounts in original currency with ILS equivalent

**Scope:** Medium-Large — touches most backend services and frontend components

---

### 2. Real Estate / Property Tracking
**What Moneytor does:** Automatic property value estimates, rent income management, financing insights for properties.

**Integration approach:**
- New `properties` table: address, purchase price, purchase date, current estimated value, mortgage link
- New `PropertyService` for CRUD and valuation history
- Property value snapshots (similar to investment balance snapshots) — manual entry or API-based estimation
- Rent tracking: recurring income entries linked to a property
- Properties appear as an asset class in net worth calculations
- New "Properties" page in frontend with property cards, value history chart, rent tracking

**Scope:** Large — new domain model, new page, net worth integration

---

### 3. Loan & Mortgage Tracking
**What Moneytor does:** Import loans and mortgages from Israeli banks. Track outstanding balances, payment schedules, interest rates.

**Integration approach:**
- New `loans` table: lender, original amount, outstanding balance, interest rate, term, monthly payment, type (mortgage/personal/auto)
- New `LoanService` for amortization calculations and payoff projections
- Link loan payments to bank transactions (auto-tag "Liabilities" transactions to specific loans)
- Loans appear as liabilities in net worth calculation (currently we have Liabilities category but no structured loan tracking)
- Amortization schedule view showing principal vs interest breakdown
- New "Loans" section — could be a tab on an existing page or standalone

**Scope:** Medium — extends existing Liabilities concept with structured data

---

### 4. Pension & Provident Fund Tracking
**What Moneytor does:** Automatic import and ongoing updates of Israeli pension assets (קופות גמל, קרנות פנסיה, ביטוח מנהלים).

**Integration approach:**
- New `pensions` table: provider, fund name, type (pension/provident/insurance), employer contribution, employee contribution, management fee
- Pension balance snapshots (like investments) — manual or scraped
- Could potentially use Har HaBituach (הר הביטוח) API or similar public pension data sources
- Pensions appear as a separate asset class in net worth
- Dashboard widget showing total pension value and monthly contributions
- New "Pensions" page or section within Investments

**Scope:** Large — new domain, potential new scraper integration, net worth changes

---

### 5. Cryptocurrency Tracking
**What Moneytor does:** Automatic connection to crypto wallets, automatic crypto value updates.

**Integration approach:**
- Extend investments model with crypto-specific fields OR new `crypto_assets` table: symbol, quantity, wallet address, exchange
- Price feed integration (CoinGecko API free tier) for automatic value updates
- Auto-generate balance snapshots from price feed data
- Support manual entry of crypto holdings (quantity + purchase price)
- Crypto as a separate asset class in net worth and portfolio allocation
- Could appear as a tab within Investments page

**Scope:** Medium — largely fits existing investment infrastructure, main work is price feed integration

---

### 6. Securities Auto-Import & Price Updates
**What Moneytor does:** Automatic import of securities holdings from Israeli banks, automatic stock value updates.

**Integration approach:**
- Extend scraping module to extract securities portfolio data (if israeli-bank-scrapers supports it)
- Stock price feed integration (TASE API for Israeli stocks, Yahoo Finance/Alpha Vantage for international)
- Auto-generate daily balance snapshots from market prices
- Link securities to investment accounts
- Show individual holdings breakdown within investment accounts

**Scope:** Medium — extends existing investment + scraping infrastructure

---

### 7. AI-Powered Financial Insights
**What Moneytor does:** "HI-AI insight generator" delivering personalized analysis — investment returns, fee identification, interest rate optimization, asset allocation recommendations.

**Integration approach:**
- New `InsightsService` that runs periodic analysis on user data
- Rule-based insights engine (no ML needed initially):
  - **Spending anomalies:** Flag months where category spending exceeds 2x average
  - **Fee detection:** Identify recurring small transactions that look like fees/subscriptions
  - **Budget warnings:** Proactive alerts when approaching budget limits mid-month
  - **Savings rate:** Track savings rate trend and flag declines
  - **Category trends:** "Your Food spending increased 30% over 3 months"
  - **Unused subscriptions:** Detect recurring charges the user might want to review
  - **Investment performance:** Compare ROI across investments, flag underperformers
  - **Optimization suggestions:** "Moving X from savings to investment Y would yield..."
- Later phase: integrate Claude API for natural language insight generation from financial data
- Frontend: Insights panel/card on dashboard, or dedicated Insights page

**Scope:** Large — new service with multiple analysis algorithms, new UI components

---

### 8. Financial Calendar & Reminders
**What Moneytor does:** Automated reminders for upcoming financial actions — bill due dates, subscription renewals, investment maturity dates.

**Integration approach:**
- New `financial_events` table: title, date, type (bill/renewal/maturity/custom), recurrence, linked entity (loan/investment/etc.)
- Auto-detect recurring transactions and create calendar entries
- Investment maturity date reminders
- Loan payment due date tracking
- Budget reset reminders (month start)
- Frontend: Calendar view component, notification badge in header
- Could integrate with system notifications or email (future)

**Scope:** Medium — new domain model, recurring transaction detection logic, calendar UI

---

### 9. Alerts & Notifications System
**What Moneytor does:** Action alerts based on activity and assets — notifications for incomplete tasks, unusual activity.

**Integration approach:**
- New `notifications` table: type, message, severity, read status, created date, linked entity
- Notification triggers:
  - Large transaction detected (configurable threshold)
  - Budget limit approaching/exceeded
  - Scraping failure or account sync issues
  - New untagged transactions requiring categorization
  - Pending refund past expected date
  - Investment milestone (e.g., ROI target reached)
- Frontend: Notification bell in header with dropdown, notification preferences page
- Future: Push notifications, email digest

**Scope:** Medium — notification infrastructure + trigger hooks in existing services

---

### 10. PDF / Report Export
**What Moneytor does:** Export financial summaries to PDF.

**Integration approach:**
- New `ReportService` with report templates:
  - Monthly financial summary (income, expenses, net balance, category breakdown)
  - Net worth report (all asset classes, historical trend)
  - Investment portfolio report (holdings, P&L, allocation)
  - Annual summary report
- Use a Python PDF library (ReportLab or WeasyPrint) to generate styled PDFs
- Frontend: "Export" buttons on dashboard and relevant pages
- Could also support CSV export for transaction data

**Scope:** Small-Medium — backend PDF generation, frontend export buttons

---

### 11. Early Retirement Planning (FIRE Calculator)
**What Moneytor does:** Early retirement planning tools — likely a calculator based on current savings rate, investment returns, and target retirement number.

**Integration approach:**
- New calculator page/modal with inputs:
  - Current age, target retirement age
  - Current net worth (auto-populated from our data)
  - Monthly savings rate (calculated from income - expenses)
  - Expected investment return rate
  - Target annual spending in retirement
  - Inflation rate assumption
- Output: Years to retirement, required portfolio size, savings gap analysis
- Monte Carlo simulation for probability estimates (stretch goal)
- Chart showing projected net worth growth over time

**Scope:** Small-Medium — standalone calculator page, no backend persistence needed initially

---

### 12. Portfolio Sharing / Multi-User
**What Moneytor does:** Share portfolios with financial advisors. Couples subscription with two users.

**Integration approach:**
- This is a significant architectural change requiring:
  - User authentication system (currently single-user, no auth)
  - User accounts table, session management
  - Data isolation per user
  - Sharing permissions (read-only advisor view)
  - Couples mode: two users sharing one dataset
- This should be the LAST feature to implement as it fundamentally changes the app architecture

**Scope:** Very Large — requires auth system, multi-tenancy, permission model

---

## Recommended Implementation Priority

### Phase 1 — Quick Wins (Low effort, high value)
1. **PDF / Report Export** — Users love exportable reports, relatively simple
2. **Alerts & Notifications** — Hooks into existing services, improves daily utility
3. **AI-Powered Insights (rule-based)** — Start with simple anomaly detection, no ML needed

### Phase 2 — Asset Class Expansion (Broaden net worth picture)
4. **Loan & Mortgage Tracking** — Structures our existing Liabilities concept
5. **Cryptocurrency Tracking** — Extends investment infra with price feeds
6. **Securities Price Updates** — Auto-update investment values from market data

### Phase 3 — New Domains (Bigger features)
7. **Real Estate / Property Tracking** — New asset class with valuation history
8. **Pension & Provident Fund Tracking** — Important for Israeli users
9. **Financial Calendar & Reminders** — Recurring transaction detection + calendar UI

### Phase 4 — Strategic Features
10. **Multi-Currency Support** — Cross-cutting concern, touches many components
11. **Early Retirement Planning** — Standalone calculator, fun feature
12. **Portfolio Sharing / Multi-User** — Major architectural change, do last

---

## Notes

- Each feature should follow existing architecture: Route → Service → Repository → DB
- New pages should match existing UI patterns (Tailwind CSS 4, Zustand, TanStack Query)
- Features that affect net worth calculation need careful integration with `get_net_worth_over_time()` and the overview KPIs
- Investment-adjacent features (crypto, securities, pensions) can leverage existing `InvestmentsService` patterns
- Scraper-based features depend on whether israeli-bank-scrapers supports the data source
