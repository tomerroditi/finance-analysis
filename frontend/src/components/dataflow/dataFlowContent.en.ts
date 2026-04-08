import type { DataFlowContent } from "./dataFlowData";

const content: DataFlowContent = {
  layerLabels: {
    sources: "DATA SOURCES",
    ingestion: "INGESTION",
    processing: "PROCESSING",
    storage: "STORAGE",
    management: "DATA MANAGEMENT",
    analytics: "ANALYTICS",
    frontend: "FRONTEND",
  },

  nodes: {
    banks: { title: "Banks", desc: "17 Israeli bank providers" },
    "credit-cards": { title: "Credit Cards", desc: "6 providers \u2014 Max, Visa Cal, Isracard, Amex" },
    insurance: { title: "Insurance", desc: "Pension & savings \u2014 Hafenix" },
    manual: { title: "Manual Entry", desc: "Cash, investments, balance corrections" },
    scraper: { title: "Scraper Framework", desc: "BrowserScraper (Playwright) & ApiScraper (httpx). Login, 2FA, stealth, data fetch." },
    adapter: { title: "ScraperAdapter", desc: "Result \u2192 DataFrame. Generates unique_id, normalizes fields, triggers pipeline." },
    "api-routes": { title: "API Routes", desc: "POST /transactions, /investments, /cash_balances, /bank_balances" },
    "auto-tag": { title: "Auto-Tagging", desc: "Recursive AND/OR rule engine. Priority-based, first match wins. CC bill matching." },
    "balance-recalc": { title: "Balance Recalculation", desc: "Recomputes running bank balance from transaction history after each scrape." },
    "prior-wealth": { title: "Prior Wealth", desc: "Bridges pre-tracking capital. entered_balance \u2212 sum(transactions). Injected as synthetic rows." },
    "txn-tables": { title: "Transaction Tables", desc: "5 parallel tables: bank, credit_card, cash, manual_investment, insurance + split_transactions." },
    "bank-bal": { title: "Bank Balances", desc: "Per-account balance + prior_wealth_amount." },
    "cash-bal": { title: "Cash Balances", desc: "Per-envelope balance + prior_wealth. Multiple envelopes." },
    "inv-snapshots": { title: "Investment Snapshots", desc: "Timestamped market values. manual | calculated | scraped." },
    "meta-tables": { title: "Metadata", desc: "categories, tagging_rules, budget_rules, investments, liabilities, pending_refunds." },
    "demo-mode": { title: "Demo Mode", desc: "Isolated demo DB with date-shifted sample data. Dummy scrapers for testing." },
    backup: { title: "Backup & Restore", desc: "Database snapshots. Create, list, restore with safety backup." },
    "manual-tagging": { title: "Manual Tagging", desc: "Inline category/tag editing, bulk-tag operations on selected transactions." },
    splits: { title: "Split Transactions", desc: "Split one transaction across multiple categories/tags. Parent excluded, splits merged at analysis." },
    "cc-dedup": { title: "CC Deduplication", desc: "Bank CC bill + itemized CC overlap. Aggregates use bank view; breakdowns use itemized." },
    "refunds-mgmt": { title: "Refund Management", desc: "Mark pending refunds, link to actual refund transactions, adjust budget calculations." },
    "invest-mgmt": { title: "Investment Management", desc: "Create/close/reopen investments. Manual snapshots. Fixed-rate compounding generation." },
    "liab-mgmt": { title: "Liability Management", desc: "Create loans, track payments, mark as paid off. Amortization schedule generation." },
    "budget-mgmt": { title: "Budget Management", desc: "Monthly budget rules, project budgets, copy rules between months. Total Budget special limit." },
    "balance-mgmt": { title: "Balance Management", desc: "Bank balance entry (post-scrape), cash envelope CRUD. Triggers prior wealth recalculation." },
    "cat-mgmt": { title: "Category & Rules", desc: "Create/rename/delete categories and tags. Manage tagging rules. Changes cascade to all transactions." },
    "analysis-svc": { title: "Analysis", desc: "Overview, income/expenses, net balance, net worth, by-category, Sankey, income by source." },
    "budget-svc": { title: "Budget", desc: "Budget vs actual. Monthly limits + project budgets. Refund adjustments." },
    "invest-svc": { title: "Investments", desc: "P&L, ROI, CAGR. Snapshot-first balance. Fixed-rate compounding." },
    "liab-svc": { title: "Liabilities", desc: "Amortization, remaining balance, total interest, payment tracking." },
    "retire-svc": { title: "Retirement", desc: "FIRE projections, savings rate, years to retirement, suggestions." },
    dashboard: { title: "Dashboard", desc: "Overview cards, net worth chart, income/expenses, Sankey, budget gauge." },
    "txn-page": { title: "Transactions", desc: "Filterable table, inline tagging, splits, bulk ops, refunds." },
    "budget-page": { title: "Budget", desc: "Monthly gauges, per-tag breakdown, project budgets." },
    "categories-page": { title: "Categories", desc: "Category/tag management, drag-and-drop reorder, tagging rules." },
    "invest-page": { title: "Investments", desc: "Portfolio overview, allocation, balance history, P&L analysis." },
    "liab-page": { title: "Liabilities", desc: "Debt cards, payment timeline, amortization schedule." },
    "insurance-page": { title: "Insurance", desc: "Insurance policy tracking, pension/savings accounts." },
    "retire-page": { title: "Early Retirement", desc: "FIRE calculator, projections, status cards, suggestions." },
    "datasources-page": { title: "Data Sources", desc: "Bank/CC account management, scraping triggers, stale data alerts." },
  },

  details: {
    banks: {
      title: "Banks", tag: "17 Providers",
      sections: [
        { heading: "Providers", text: "Hapoalim, Leumi, Discount, Mercantile, Mizrahi, Otsar Hahayal, Union, Beinleumi, Massad, Yahav, OneZero, Pagi, and more." },
        { heading: "Data Produced", items: ["Account transactions (debits, deposits, CC bill payments, transfers)", "Account balance snapshot", "Fields: date, amount, description, account_number, status"] },
        { heading: "Pipeline", flow: ["Playwright login", "Navigate to transactions", "Parse HTML/API response", "AccountResult", "ScraperAdapter"] },
      ],
    },
    "credit-cards": {
      title: "Credit Cards", tag: "6 Providers",
      sections: [
        { heading: "Providers", text: "Max, Visa Cal, Isracard, Amex, Beyahad Bishvilha, Behatsdaa." },
        { heading: "Data Produced", items: ["Itemized purchases with categories", "Installment tracking (type: INSTALLMENTS)", "Original + charged amounts (foreign currency)"] },
        { heading: "Overlap Warning", text: "These transactions overlap with bank CC bill payments. The CC Deduplication logic handles which view to use per KPI." },
      ],
    },
    insurance: {
      title: "Insurance", tag: "Hafenix",
      sections: [
        { heading: "Data Produced", items: ["Pension/savings deposit transactions", "Memo field: deposit breakdown (employee/employer/compensation)", "Account metadata (policy type, investment tracks, commissions)"] },
        { heading: "Special Handling", text: "InsuranceScraperAdapter extends base adapter with post-save hook to persist insurance account metadata." },
      ],
    },
    manual: {
      title: "Manual Entry", tag: "UI Forms",
      sections: [
        { heading: "Entry Points", items: ["POST /transactions/ \u2014 cash or investment transactions", "POST /cash_balances/ \u2014 set cash envelope balance", "POST /bank_balances/ \u2014 enter bank balance (triggers prior wealth calc)", "POST /investments/ \u2014 create investment metadata", "POST /investments/{id}/snapshots \u2014 manual balance snapshot"] },
        { heading: "Restrictions", text: "Manual entries can be fully edited/deleted. Scraped entries only allow category/tag changes." },
      ],
    },
    scraper: {
      title: "Scraper Framework", tag: "Async",
      sections: [
        { heading: "Architecture", items: ["BaseScraper: initialize \u2192 login \u2192 fetch_data \u2192 terminate", "BrowserScraper: Playwright with stealth anti-detection", "ApiScraper: httpx async HTTP for API-only sources"] },
        { heading: "Features", items: ["2FA/OTP handling with async callback", "Configurable scraping period (days back)", "Screenshot capture on failure", "Daily rate limit (one scrape per account per day)", "5-minute timeout"] },
        { heading: "Output", text: "ScrapingResult { success, accounts: [{ account_number, transactions, balance }], error_type, error_message }" },
      ],
    },
    adapter: {
      title: "ScraperAdapter", tag: "Bridge",
      sections: [
        { heading: "Pipeline Steps", flow: ["ScrapingResult", "DataFrame", "INSERT/UPDATE", "Auto-tag", "Rebalance", "Record history"] },
        { heading: "Normalization", items: ["Generates unique_id: {provider}_{account}_{date}_{amount}_{identifier}", "Maps source to table name", "Normalizes all fields to unified schema"] },
        { heading: "Demo Mode", text: "Automatically redirects to dummy scrapers that generate fake data." },
      ],
    },
    "api-routes": {
      title: "API Routes", tag: "FastAPI",
      sections: [
        { heading: "Transaction Routes", items: ["POST /transactions/ \u2014 create (cash, manual_investments)", "PUT /transactions/{id} \u2014 update fields", "DELETE /transactions/{id} \u2014 delete (manual only)", "POST /transactions/{id}/split \u2014 split into sub-transactions", "POST /transactions/bulk-tag \u2014 bulk category/tag update"] },
        { heading: "Balance Routes", items: ["POST /bank_balances/ \u2014 triggers prior wealth calculation", "POST /cash_balances/ \u2014 triggers prior wealth + balance recalc"] },
      ],
    },
    "auto-tag": {
      title: "Auto-Tagging Engine", tag: "Rules Engine",
      sections: [
        { heading: "How It Works", items: ["Rules evaluated in priority order (DESC) \u2014 first match wins", "Conditions are recursive AND/OR trees", "Fields: description, account_name, provider, amount", "Operators: contains, equals, starts_with, gt, lt, between"] },
        { heading: "CC Bill Matching", text: "Matches bank debit amounts to CC monthly totals (shifted +1 month, \u00b10.01 tolerance). Tags as Credit Cards category." },
        { heading: "Conflict Detection", text: "Checks for overlapping rules assigning different tags before creating." },
      ],
    },
    "balance-recalc": {
      title: "Balance Recalculation", tag: "Bank Only",
      sections: [
        { heading: "When", text: "Triggered after every bank scrape. Recomputes running balance from full transaction history." },
        { heading: "Why", text: "New transactions change cumulative sum. Stored balance must stay consistent." },
      ],
    },
    "prior-wealth": {
      title: "Prior Wealth", tag: "Synthetic Rows",
      sections: [
        { heading: "Formula", text: "prior_wealth = user_entered_balance \u2212 sum(all_tracked_transactions)" },
        { heading: "Three Sources", items: ["Bank: calculated when user enters balance after scraping", "Cash: calculated when user sets cash balance", "Investments: investment.prior_wealth_amount = \u2212sum(all inv txns)"] },
        { heading: "Why Inv Prior Wealth Lives in Bank", text: "Investment deposits came from bank accounts. Keeping inv_prior_wealth in bank balance maintains: net_worth = bank_balance + investment_value." },
      ],
    },
    "manual-tagging": {
      title: "Manual Tagging", tag: "User-Driven",
      sections: [
        { heading: "Operations", items: ["Inline category/tag editing on individual transactions", "Bulk-tag: select multiple transactions, apply same category/tag", "Scraped transactions: only category/tag can be changed", "Manual transactions: all fields editable"] },
        { heading: "Flow", flow: ["User selects transaction(s)", "Choose category + tag", "PUT /transactions/{id} or POST /transactions/bulk-tag", "Cache invalidation", "Analytics re-render"] },
      ],
    },
    splits: {
      title: "Split Transactions", tag: "User-Driven",
      sections: [
        { heading: "How It Works", items: ["User splits one transaction into multiple category/tag portions", "Parent stays in main table, marked type=split_parent", "Splits stored in split_transactions table with own amount, category, tag", "Service merges: replaces parents with splits for analysis"] },
        { heading: "Example", text: "\u2212500 Supermarket \u2192 Split 1: \u2212300 Food/Groceries + Split 2: \u2212200 Home/Cleaning. Parent excluded from totals." },
      ],
    },
    "cc-dedup": {
      title: "CC Deduplication", tag: "Critical Pattern",
      sections: [
        { heading: "The Problem", text: "A 3,000\u20AA CC bill = ONE bank txn AND ~N itemized CC txns totaling ~3,000\u20AA. Both = double-count." },
        { heading: "Strategy by KPI", items: ["Aggregate KPIs (income, balance, net worth) \u2192 bank view, exclude CC source", "Category breakdowns (pie, budgets) \u2192 itemized CC, exclude Credit Cards category", "Sankey flow \u2192 hybrid, CC gap shown as Unknown"] },
        { heading: "CC Gap", text: "cc_gap = abs(bank CC bills) \u2212 abs(itemized CC). Caused by timing, pending txns, fees, FX rounding." },
      ],
    },
    "refunds-mgmt": {
      title: "Refund Management", tag: "Budget Adjust",
      sections: [
        { heading: "Workflow", items: ["Mark a transaction or split as \u201cpending refund\u201d with expected amount", "When actual refund arrives, link it to the pending refund", "Supports partial refunds (multiple links to one pending)", "Status tracking: pending \u2192 partial \u2192 resolved \u2192 closed"] },
        { heading: "Budget Impact", text: "Pending refund adjustments are subtracted from budget spent amounts. This prevents temporary overspend alerts for expenses that will be refunded." },
        { heading: "Flow", flow: ["Mark pending", "Link refund txn", "Update status", "Budget recalculates"] },
      ],
    },
    "invest-mgmt": {
      title: "Investment Management", tag: "Lifecycle",
      sections: [
        { heading: "Operations", items: ["Create investment (category, tag, type, rates, commissions)", "Add manual balance snapshots at any date", "Generate fixed-rate compounded snapshots automatically", "Close investment \u2192 creates 0-balance snapshot on last txn date", "Reopen closed investments, edit close date"] },
        { heading: "Balance Resolution", items: ["1. Latest snapshot on/before today \u2192 use snapshot", "2. No snapshots \u2192 fallback to \u2212sum(all transactions)", "Snapshot sources: manual > calculated > scraped"] },
      ],
    },
    "liab-mgmt": {
      title: "Liability Management", tag: "Loan Tracking",
      sections: [
        { heading: "Operations", items: ["Create liability (principal, rate, term, start date)", "Track payment records against amortization schedule", "Mark as paid off with specific date", "Reopen if needed"] },
        { heading: "Category Override", text: "Negative Liabilities (debt payments) override into expenses despite Liabilities being a non-expense category." },
      ],
    },
    "budget-mgmt": {
      title: "Budget Management", tag: "Rules + Projects",
      sections: [
        { heading: "Monthly Budgets", items: ["Create spending limit per category/tag for a specific month", "Edit or delete existing budget rules", "Copy all rules from a previous month to a new month", "'Total Budget' \u2014 special overall monthly spending limit"] },
        { heading: "Project Budgets", items: ["Time-limited budgets for specific goals (e.g., Home Renovation)", "Track spending vs budget with gauge visualization", "View all transactions tagged to the project"] },
      ],
    },
    "balance-mgmt": {
      title: "Balance Management", tag: "Triggers Prior Wealth",
      sections: [
        { heading: "Bank Balance Entry", items: ["Set current bank balance after scraping", "Triggers prior wealth calculation: balance \u2212 sum(all bank txns)", "Stores per-account: provider, account_name, balance, prior_wealth_amount"] },
        { heading: "Cash Envelope Management", items: ["Create new cash envelopes with starting balance", "Edit envelope balance \u2192 recalculates prior wealth", "Delete envelopes with confirmation"] },
      ],
    },
    "cat-mgmt": {
      title: "Category & Rules Management", tag: "Cascade",
      sections: [
        { heading: "Category Operations", items: ["Create/rename/delete categories and tags", "Rename cascades to all transactions, splits, rules, budgets", "Delete nullifies category/tag on affected transactions", "Protected categories (Salary, Credit Cards, etc.) cannot be deleted"] },
        { heading: "Tagging Rules", items: ["Create rules with recursive AND/OR conditions", "Preview matching transactions before saving", "Conflict detection: warns if rules overlap with different targets", "Rules apply immediately on creation to matching untagged transactions"] },
      ],
    },
    "txn-tables": {
      title: "Transaction Tables", tag: "5 Tables",
      sections: [
        { heading: "Tables", items: ["bank_transactions \u2014 debits, deposits, CC bills, transfers", "credit_card_transactions \u2014 itemized CC purchases", "cash_transactions \u2014 manual cash entries", "manual_investment_transactions \u2014 deposits/withdrawals", "insurance_transactions \u2014 pension/savings (+ memo)"] },
        { heading: "Unified Schema", items: ["unique_id (PK), id, date, amount, description", "provider, account_name, account_number", "category, tag, source, type, status"] },
      ],
    },
    "bank-bal": {
      title: "Bank Balances", tag: "Per-Account",
      sections: [
        { heading: "Fields", items: ["provider + account_name (composite key)", "balance \u2014 current bank balance", "prior_wealth_amount \u2014 pre-tracking capital"] },
        { heading: "Used In", text: "Net worth calculation, overview KPIs, prior wealth injection into analysis." },
      ],
    },
    "cash-bal": {
      title: "Cash Balances", tag: "Envelopes",
      sections: [
        { heading: "Fields", items: ["account_name \u2014 envelope identifier", "balance, prior_wealth_amount"] },
        { heading: "Multiple Envelopes", text: "Each has independent balance and prior wealth. Total sums across all." },
      ],
    },
    "inv-snapshots": {
      title: "Investment Snapshots", tag: "Snapshot-First",
      sections: [
        { heading: "Resolution Order", items: ["1. Latest snapshot on/before today \u2192 use it", "2. No snapshots \u2192 fallback to \u2212sum(transactions)"] },
        { heading: "Sources", items: ["manual \u2014 user-entered", "calculated \u2014 fixed-rate daily compounding", "scraped \u2014 future integration"] },
        { heading: "Closing", text: "Auto-creates 0-balance snapshot on last transaction date." },
      ],
    },
    "meta-tables": {
      title: "Metadata Tables", tag: "Configuration",
      sections: [
        { heading: "Tables", items: ["categories \u2014 name, tags (JSON), icon", "tagging_rules \u2014 conditions (recursive JSON), priority", "budget_rules \u2014 amount, category, tags (semicolon-sep)", "investments \u2014 type, rates, commissions, dates", "liabilities \u2014 principal, rate, term, dates", "pending_refunds \u2014 source tracking, resolution"] },
      ],
    },
    "analysis-svc": {
      title: "AnalysisService", tag: "7 KPI Methods",
      sections: [
        { heading: "Methods", items: ["get_overview() \u2014 totals + net change", "get_income_expenses_over_time() \u2014 monthly bars", "get_net_balance_over_time() \u2014 cumulative trend", "get_net_worth_over_time() \u2014 bank + cash + investments", "get_expenses_by_category() \u2014 pie chart", "get_sankey_data() \u2014 income \u2192 expenses flow", "get_income_by_source_over_time() \u2014 stacked breakdown"] },
        { heading: "Transaction Masks", items: ["Income: Salary, Other Income, + positive Liabilities", "Investment: Investments category", "Expense: everything else + negative Liabilities"] },
      ],
    },
    "budget-svc": {
      title: "BudgetService", tag: "Budget vs Actual",
      sections: [
        { heading: "Features", items: ["Monthly spending limits per category/tag", "Project budgets (time-limited)", "Total Budget special category", "Pending refund adjustments"] },
        { heading: "Exclusions", text: "Excludes Credit Cards, Investments, Liabilities, Ignore from calculations." },
      ],
    },
    "invest-svc": {
      title: "InvestmentsService", tag: "P&L Engine",
      sections: [
        { heading: "Key Metrics", items: ["Total deposits = abs(sum of negatives)", "Net invested = deposits \u2212 withdrawals", "Current balance = snapshot OR \u2212sum(amounts)", "Profit/Loss = balance \u2212 net_invested", "ROI = (final_value / deposits \u2212 1) \u00d7 100"] },
        { heading: "Portfolio", text: "Aggregates total_value, total_profit, portfolio_roi, allocation % across all open investments." },
      ],
    },
    "liab-svc": {
      title: "LiabilitiesService", tag: "Amortization",
      sections: [
        { heading: "Calculations", items: ["Monthly payment schedule", "Total interest over lifetime", "Remaining balance, percent paid"] },
        { heading: "Category", text: "Positive = loan receipts (income). Negative = debt payments (override into expenses)." },
      ],
    },
    "retire-svc": {
      title: "RetirementService", tag: "FIRE",
      sections: [
        { heading: "Inputs", items: ["Net worth, income, expenses, savings rate", "Target retirement age, annual expenses", "Withdrawal rate (e.g., 4% rule)"] },
        { heading: "Outputs", items: ["Years to financial independence", "Net worth projection chart", "Income scenarios, optimization suggestions"] },
      ],
    },
    dashboard: {
      title: "Dashboard", tag: "10+ Queries",
      sections: [
        { heading: "Data Sources", items: ["analyticsApi: 10 endpoints", "bankBalancesApi + cashBalancesApi", "investmentsApi.getPortfolioAnalysis()", "transactionsApi.getAll() for recent feed"] },
        { heading: "Components", text: "Financial health header, net worth chart, income/expenses bars, Sankey flow, budget gauge, recent transactions." },
      ],
    },
    "txn-page": {
      title: "Transactions Page", tag: "Filterable",
      sections: [
        { heading: "Features", items: ["Sortable/filterable table", "Inline tag editing", "Split creation, bulk operations", "Pending refunds section"] },
        { heading: "Cache Invalidation", text: "Tagging invalidates: transactions, categories, and 6 analytics queries." },
      ],
    },
    "budget-page": {
      title: "Budget Page", tag: "Monthly + Projects",
      sections: [
        { heading: "Views", items: ["Monthly: gauge + rule cards", "Per-tag breakdown within categories", "Project budgets with progress"] },
      ],
    },
    "invest-page": {
      title: "Investments Page", tag: "Portfolio",
      sections: [
        { heading: "Views", items: ["Portfolio: total value, profit, ROI", "Allocation pie chart", "Balance history line chart", "Individual analysis modal"] },
      ],
    },
    "liab-page": {
      title: "Liabilities Page", tag: "Debt Tracking",
      sections: [
        { heading: "Views", items: ["Liability cards with metrics", "Debt over time chart", "Amortization schedule", "Payment history"] },
      ],
    },
    "retire-page": {
      title: "Early Retirement Page", tag: "FIRE Calculator",
      sections: [
        { heading: "Components", items: ["Retirement goal form", "6-card status grid", "Projection charts", "Optimization suggestions"] },
      ],
    },
    "categories-page": {
      title: "Categories Page", tag: "Management",
      sections: [
        { heading: "Features", items: ["Create/rename/delete categories and tags", "Drag-and-drop reorder", "Tagging rules builder with preview", "Tag reallocation between categories"] },
      ],
    },
    "insurance-page": {
      title: "Insurance Page", tag: "Policies",
      sections: [
        { heading: "Features", items: ["Insurance policy cards", "Pension/savings account details", "Deposit history and breakdowns", "Investment track information"] },
      ],
    },
    "demo-mode": {
      title: "Demo Mode", tag: "Toggle",
      sections: [
        { heading: "How It Works", items: ["Toggle in app header switches to isolated demo database", "Demo DB is a copy of bundled template with date-shifted data", "All dates relative to current date for realistic appearance", "Pre-seeded bank and credit card accounts (with/without 2FA)"] },
        { heading: "Scraper Redirect", text: "When demo mode is active, scraping requests are automatically redirected to dummy scrapers that generate fake data. No real financial institutions are contacted." },
        { heading: "Isolation", text: "Completely separate database \u2014 no production data is read or affected. Safe for UI testing and demos." },
      ],
    },
    backup: {
      title: "Backup & Restore", tag: "Snapshots",
      sections: [
        { heading: "Operations", items: ["Create backup \u2014 full snapshot of current database file", "List backups \u2014 all available snapshots with size and date", "Restore \u2014 revert to a previous backup (creates safety backup first)"] },
        { heading: "Storage", text: "Backups stored in ~/.finance-analysis/backups/ as timestamped SQLite copies." },
      ],
    },
    "datasources-page": {
      title: "Data Sources Page", tag: "Scraping",
      sections: [
        { heading: "Features", items: ["Bank/CC account management", "Scraping triggers with progress", "Stale data alerts (>7 days)", "Credential management via OS Keyring"] },
      ],
    },
  },

  platformFeatures: [
    {
      title: "Internationalization (i18n)",
      desc: "Full Hebrew + English bilingual support with automatic RTL layout switching.",
      highlights: ["i18next + react-i18next", "Logical CSS properties (ps/pe/ms/me) for RTL", "Locale-aware date, currency, chart formatting", "All strings via t() \u2014 no hardcoded text"],
    },
    {
      title: "Responsive Design",
      desc: "Mobile-first layout with adaptive patterns across all breakpoints.",
      highlights: ["Sidebar \u2192 drawer overlay on mobile", "Tap-to-reveal actions (no hover on touch)", "Dynamic viewport height (dvh)", "iOS safe areas, scroll-snap, touch targets \u2265 32px"],
    },
  ],

  callouts: [
    { title: "Amount Sign Convention (everywhere):", text: "Negative = money out (expenses, investment deposits). Positive = money in (salary, refunds, withdrawals). Applies across all tables, services, and calculations." },
    { title: "CC Deduplication \u2014 the critical pattern:", text: "Bank CC bill payment and itemized CC purchases overlap. Aggregate KPIs (income, net worth) \u2192 bank view, exclude CC source. Category breakdowns (pie charts, budgets) \u2192 itemized view, exclude \"Credit Cards\" category." },
    { title: "Prior Wealth bridges the gap:", text: "prior_wealth = entered_balance \u2212 sum(transactions). Injected as synthetic \"Prior Wealth\" tagged rows. Investment prior wealth lives in bank balance (money originally came from banks)." },
    { title: "Investment Balance Resolution:", text: "Snapshot-first (manual > calculated > scraped), then transaction-sum fallback (\u2212sum(all amounts)). Closing creates a 0-balance snapshot. Fixed-rate investments auto-generate daily-compounded snapshots." },
    { title: "Non-expense overrides:", text: "Investments, Liabilities, Income categories, Credit Cards excluded from expenses \u2014 except negative Liabilities (debt payments), which override back as real money outflows." },
  ],
};

export default content;
