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
    banks: { title: "Banks", desc: "12 Israeli bank providers \u2014 Hapoalim, Leumi, Discount, Mizrahi, OneZero\u2026" },
    "credit-cards": { title: "Credit Cards", desc: "6 providers \u2014 Max, Visa Cal, Isracard, Amex" },
    insurance: { title: "Pension Savings", desc: "Keren Hishtalmut & pension \u2014 the Pension Clearing House." },
    manual: { title: "Manual Entry", desc: "Cash, investments, liabilities, balance corrections" },
    "rates-feed": { title: "Bank of Israel", desc: "Key-rate series behind the Israeli prime rate. Drives prime-linked loans and savings." },
    scraper: { title: "Scraper Framework", desc: "BrowserScraper (Playwright) & ApiScraper (httpx). Login, 2FA, stealth, data fetch." },
    adapter: { title: "ScraperAdapter", desc: "Result \u2192 DataFrame. Generates unique_id, normalizes fields, triggers pipeline." },
    "api-routes": { title: "API Routes", desc: "One router per feature area under /api. Host allowlist, bearer token for non-loopback, same-origin guard on writes." },
    "auto-tag": { title: "Auto-Tagging", desc: "Recursive AND/OR rule engine. Creation order, first match wins. CC bill matching." },
    "balance-recalc": { title: "Balance Recalculation", desc: "Recomputes running bank balance from transaction history after each scrape." },
    "prior-wealth": { title: "Prior Wealth", desc: "Bridges pre-tracking capital. entered_balance \u2212 sum(transactions). Injected as synthetic rows." },
    "kh-sync": { title: "Keren Hishtalmut Sync", desc: "Scraped insurance policies become type=hishtalmut investments with scraped snapshots." },
    "txn-tables": { title: "Transaction Tables", desc: "5 parallel tables: bank, credit_card, cash, manual_investment, insurance + split_transactions." },
    "bank-bal": { title: "Bank Balances", desc: "Per-account balance + prior_wealth_amount." },
    "cash-bal": { title: "Cash Balances", desc: "Per-envelope balance + prior_wealth. Multiple envelopes." },
    "inv-snapshots": { title: "Investment Snapshots", desc: "Timestamped market values. manual | calculated | scraped." },
    "meta-tables": { title: "Metadata", desc: "categories, tagging_rules, budget_rules, investments, liabilities, insurance_accounts, interest_rates, refunds." },
    "goal-tables": { title: "Savings Goal Tables", desc: "savings_goals + per-month allocations, transaction links, investment backings." },
    "decision-tables": { title: "Decisions & Overrides", desc: "recurring_decisions, insight_dismissals, budget_month_overrides \u2014 what you ruled on, kept across re-detection." },
    "credentials-vault": { title: "Credential Vault", desc: "Passwords in the OS Keyring; usernames, ID numbers and card digits Fernet-encrypted in the DB." },
    "demo-mode": { title: "Demo Mode", desc: "Isolated demo DB with date-shifted sample data. Dummy scrapers for testing." },
    backup: { title: "Backup & Restore", desc: "Database snapshots. Create, list, restore with safety backup." },
    "manual-tagging": { title: "Manual Tagging", desc: "Inline category/tag editing, bulk-tag operations on selected transactions." },
    splits: { title: "Split Transactions", desc: "Split one transaction across multiple categories/tags. Parent excluded, splits merged at analysis." },
    "cc-dedup": { title: "CC Deduplication", desc: "Bank CC bill + itemized CC overlap. Aggregates use bank view; breakdowns use itemized." },
    "refunds-mgmt": { title: "Refund Management", desc: "Mark pending refunds, link to actual refund transactions, adjust budget calculations." },
    "invest-mgmt": { title: "Investment Management", desc: "Create/close/reopen investments. Manual snapshots. Fixed-rate compounding generation." },
    "liab-mgmt": { title: "Liability Management", desc: "Create loans, track payments, mark as paid off. Amortization schedule generation." },
    "budget-mgmt": { title: "Budget Management", desc: "Three rule kinds \u2014 monthly, yearly, project. Copy forward, close a finished one, alerts." },
    "month-override": { title: "Budget Month Override", desc: "Count a transaction in a neighbouring month without changing its date. Capped at \u00B11 month." },
    "savings-goals-mgmt": { title: "Savings Goals", desc: "Prioritised earmarks over money already tracked. Cap, target, links, investment backing." },
    "recurring-review": { title: "Recurring Review", desc: "Confirm, dismiss or re-open a detected commitment. Only confirmed ones are acted on." },
    "balance-mgmt": { title: "Balance Management", desc: "Bank balance entry (post-scrape), cash envelope CRUD. Triggers prior wealth recalculation." },
    "cat-mgmt": { title: "Category & Rules", desc: "Create/rename/delete categories and tags. Manage tagging rules. Changes cascade to all transactions." },
    "analysis-svc": { title: "Analysis", desc: "Overview, income/expenses, net balance, net worth, Sankey, income by source, heatmap." },
    "forecast-svc": { title: "Cash-Flow Forecast", desc: "Projects month end from trend + month-to-date. Safe-to-spend nets out committed charges." },
    "recurring-svc": { title: "Recurring Detection", desc: "Finds commitments on cadence, regularity and amount stability. Scores each with a confidence." },
    "insights-svc": { title: "Insights", desc: "Only what the budget does not already explain \u2014 spikes, pace, big charges, repriced subscriptions." },
    "budget-svc": { title: "Budget", desc: "Budget vs actual across monthly, yearly and project rules. Fixed/variable split, alerts." },
    "goals-svc": { title: "Savings Goals Engine", desc: "Each month\u2019s realized surplus flows down goals by priority. Free cash is what none claims." },
    "invest-svc": { title: "Investments", desc: "P&L, ROI, CAGR. Snapshot-first balance. Fixed-rate compounding." },
    "liab-svc": { title: "Liabilities", desc: "Amortization, remaining balance, total interest, payment tracking." },
    "rates-svc": { title: "Rates", desc: "Bank of Israel key-rate history \u2192 prime. Re-prices prime-linked loans and savings at each step." },
    "retire-svc": { title: "Retirement", desc: "All-real-terms FIRE model. Projections, drawdown survival, solve-for-a-field, suggestions." },
    "onboarding-page": { title: "Onboarding", desc: "First-run gate \u2014 connect an account or add data before the app opens." },
    dashboard: { title: "Dashboard", desc: "Reorderable, hideable cards: forecast, insights, budget, recurring, goals, net worth, heatmap\u2026" },
    "txn-page": { title: "Transactions", desc: "Filterable table, inline tagging, splits, bulk ops, refunds, budget-month override." },
    "budget-page": { title: "Budget", desc: "Overview, monthly, yearly and project tabs. Savings goals section, alerts, freshness badge." },
    "categories-page": { title: "Categories", desc: "Category/tag management, drag-and-drop reorder, tagging rules." },
    "invest-page": { title: "Investments", desc: "Portfolio overview, allocation, balance history, P&L analysis." },
    "liab-page": { title: "Liabilities", desc: "Debt cards, payment timeline, amortization schedule." },
    "insurance-page": { title: "Pension Savings", desc: "Retirement outlook, savings KPIs, pension and Keren Hishtalmut funds." },
    "retire-page": { title: "Early Retirement", desc: "FIRE calculator, projections, status cards, suggestions." },
    "datasources-page": { title: "Data Sources", desc: "Bank/CC account management, scraping triggers, stale data alerts." },
    "settings-page": { title: "Settings", desc: "Dashboard layout, budget alerts, language, demo toggle, backups, updates, uninstall." },
    pwa: { title: "PWA & Offline", desc: "Installable app. Service worker caches API GETs; the query cache persists to IndexedDB." },
  },

  details: {
    banks: {
      title: "Banks", tag: "12 Providers",
      sections: [
        { heading: "Providers", text: "Hapoalim, Leumi, Discount, Mercantile, Mizrahi, Otsar Hahayal, Union, Beinleumi, Massad, Yahav, OneZero, Pagi \u2014 19 providers in all across banks, cards and insurance." },
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
      title: "Pension Savings", tag: "Pension Clearing House",
      sections: [
        { heading: "Providers", text: "The Pension Clearing House (Mislaka) reports every pension and Keren Hishtalmut the user holds, across all fund managers, from monthly month-end reports the portal keeps for about two months. HaPhoenix is deprecated: existing HaPhoenix accounts keep scraping, but new ones cannot be added." },
        { heading: "Data Produced", items: ["Pension/savings deposit transactions", "Memo field: deposit breakdown (employee/employer/compensation)", "Account metadata (policy type, investment tracks, commissions)"] },
        { heading: "Special Handling", text: "InsuranceScraperAdapter extends the base adapter with a post-save hook that persists insurance account metadata, which the Keren Hishtalmut sync then turns into a tracked investment." },
        { heading: "Policy IDs Drift", text: "A provider can restyle the internal ID it appends to a policy number without the account changing. Incoming IDs are normalized before being stored or matched \u2014 a stored ID is never rewritten, because other tables join on that exact string." },
        { heading: "Takeover from HaPhoenix", text: "A Clearing House scrape adopts the HaPhoenix policies it also reports: their deposits, account row and linked investment move to the Clearing House account, keeping HaPhoenix's policy IDs. Deposits dedup across providers, so history the Clearing House cannot report survives and overlapping deposits are stored once. A later HaPhoenix scrape of an adopted policy only refreshes its balance, and a balance older than the stored one is ignored." },
      ],
    },
    manual: {
      title: "Manual Entry", tag: "UI Forms",
      sections: [
        { heading: "Entry Points", items: ["POST /transactions/ \u2014 cash or investment transactions", "POST /cash_balances/ \u2014 set cash envelope balance", "POST /bank_balances/ \u2014 enter bank balance (triggers prior wealth calc)", "POST /investments/ \u2014 create investment metadata", "POST /investments/{id}/snapshots \u2014 manual balance snapshot"] },
        { heading: "Restrictions", text: "Manual entries can be fully edited/deleted. Scraped entries only allow category/tag changes." },
      ],
    },
    "rates-feed": {
      title: "Bank of Israel", tag: "Rates Feed",
      sections: [
        { heading: "What It Provides", text: "The Bank of Israel key-rate series. The Israeli prime rate is that key rate + 1.5%, and it is what variable Israeli credit is quoted against." },
        { heading: "Who Consumes It", items: ["Prime-linked loans \u2014 rate = prime + per-loan spread (the spread may be negative)", "Variable-unlinked loans \u2014 re-priced every rate_reset_months at the prime of the reset date", "Prime-linked savings and deposits \u2014 same arithmetic on the investment side"] },
        { heading: "Sync", text: "Seeded from a bundled history on first run and refreshed on demand via POST /rates/refresh. Stored in interest_rates, so amortization and compounding stay reproducible offline." },
      ],
    },
    scraper: {
      title: "Scraper Framework", tag: "Async",
      sections: [
        { heading: "Architecture", items: ["BaseScraper: initialize \u2192 login \u2192 fetch_data \u2192 terminate", "BrowserScraper: Playwright with stealth anti-detection", "ApiScraper: httpx async HTTP for API-only sources"] },
        { heading: "Features", items: ["2FA/OTP handling with async callback", "Scrape window shaped by the last-success watermark \u2014 no daily cap, no automatic retry", "Screenshot capture on failure", "5-minute timeout per run", "OneZero needs a Cloudflare mTLS client certificate, vendored with the provider"] },
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
        { heading: "Access Control", items: ["Every request needs an allowlisted Host header (DNS-rebinding guard)", "Non-loopback clients need Authorization: Bearer <token>", "Writes require a same-site Origin, or none at all \u2014 a cross-origin POST cannot reach the API from a browser", "A tailscale-relayed request is admitted by its verified tailnet login"] },
        { heading: "Errors", text: "Domain errors are raised in services and repositories \u2014 EntityNotFound (404), EntityAlreadyExists (409), Validation / BadRequest (400). Routes carry no try/except, and a 5xx body never echoes exception text." },
      ],
    },
    "auto-tag": {
      title: "Auto-Tagging Engine", tag: "Rules Engine",
      sections: [
        { heading: "How It Works", items: ["Rules evaluated in creation order \u2014 first match wins; overlapping rules are rejected on save", "Conditions are recursive AND/OR trees", "Fields: description, account_name, provider, amount", "Operators: contains, equals, starts_with, gt, lt, between"] },
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
    "kh-sync": {
      title: "Keren Hishtalmut Sync", tag: "Insurance \u2192 Investments",
      sections: [
        { heading: "What It Does", items: ["Scraped hishtalmut policies become type=hishtalmut investments, keyed by insurance_policy_id", "Balance data upserts a scraped snapshot \u2014 never overwriting a manual one", "Existing policies have their metadata refreshed instead of being duplicated"] },
        { heading: "Why It Matters For FIRE", text: "A synced policy is already inside tracked net worth. The retirement model therefore swaps the tracked KH value out before adding the goal\u2019s KH bucket, so Keren Hishtalmut counts exactly once for scraped and typed-only users alike." },
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
        { heading: "Workflow", items: ["Mark a transaction or split as \u201cpending refund\u201d with expected amount", "When actual refund arrives, link it to the pending refund", "Supports partial refunds (multiple links to one pending)", "One refund transaction can fund multiple pending refunds \u2014 leftover money stays available for further matching", "Status tracking: pending \u2192 partial \u2192 resolved \u2192 closed"] },
        { heading: "Budget Impact", text: "Pending refund adjustments are subtracted from budget spent amounts. This prevents temporary overspend alerts for expenses that will be refunded." },
        { heading: "Flow", flow: ["Mark pending", "Link refund txn", "Update status", "Budget recalculates"] },
      ],
    },
    "invest-mgmt": {
      title: "Investment Management", tag: "Lifecycle",
      sections: [
        { heading: "Operations", items: ["Create investment (category, tag, type, rates, commissions)", "Add manual balance snapshots at any date", "Generate compounded snapshots for fixed and prime-linked rates", "Close investment \u2192 creates a 0-balance snapshot on the last transaction date", "Reopen closed investments, edit close date", "Earmark a holding to back a savings goal"] },
        { heading: "Keren Hishtalmut", text: "A scraped hishtalmut policy arrives as a managed investment with its own scraped snapshots. Its value is already in net worth, so the retirement model deliberately swaps it out before adding the KH bucket." },
        { heading: "Balance Resolution", items: ["1. Latest snapshot on/before today \u2192 use snapshot", "2. No snapshots \u2192 fallback to \u2212sum(all transactions)", "Snapshot sources: manual > calculated > scraped"] },
      ],
    },
    "liab-mgmt": {
      title: "Liability Management", tag: "Loan Tracking",
      sections: [
        { heading: "Operations", items: ["Create liability (principal, rate, term, start date, loan type)", "Generated payment rows land in liability_transactions", "Track payment records against the amortization schedule", "Mark as paid off with a specific date, reopen if needed"] },
        { heading: "Rate Behavior", items: ["Fixed unlinked \u2014 one rate for the term", "Prime-linked \u2014 prime + spread, re-priced at every Bank of Israel step", "Variable unlinked \u2014 resets to the prime of the reset date, flat between resets"] },
        { heading: "Category Override", text: "Negative Liabilities (debt payments) override into expenses despite Liabilities being a non-expense category." },
      ],
    },
    "budget-mgmt": {
      title: "Budget Management", tag: "Three Rule Kinds",
      sections: [
        { heading: "Monthly", items: ["A spending limit per category/tag for one month", "Copy every rule from a previous month forward in one click", "'Total Budget' \u2014 a single overall monthly cap", "Alerts when a rule is near or over its limit"] },
        { heading: "Yearly", items: ["A per-year rule for a category/tag that is lumpy by design \u2014 insurance, car test, tuition", "Mutually exclusive with a monthly rule on the same (category, tag) within that year", "Carry the year\u2019s rules into the next year", "A settled rule is closed, not deleted \u2014 it keeps its limit, its spend and its row, and goes on claiming its category"] },
        { heading: "Projects", items: ["A category-owned rule for a one-off effort \u2014 a renovation, a trip", "A finished project is closed, not deleted: it keeps its rules, transactions and tab, and its category stays claimed", "Deleting is what frees the category again", "Closing only removes it from the Overview \u2014 the money it spent still counts in total out"] },
        { heading: "Category Exclusion", text: "A category cannot be both project-owned and used by a monthly or yearly rule. The new-project picker filters claimed categories out, rule creation blocks claimed ones, and any pre-existing overlap surfaces as a dismissible notice rather than a hard block." },
      ],
    },
    "month-override": {
      title: "Budget Month Override", tag: "\u00B11 Month",
      sections: [
        { heading: "The Problem", text: "A charge lands on the 1st for a bill that belongs to last month, or the supermarket run for next month\u2019s holiday clears early. Its real date is correct; the month the budget counts it in is not." },
        { heading: "How It Works", items: ["The transaction keeps its real date \u2014 only the monthly budget view moves", "Movement is capped at one month before or after the real month", "Works on a split as well as a whole transaction", "Stored in budget_month_overrides; removing the override puts it back"] },
      ],
    },
    "savings-goals-mgmt": {
      title: "Savings Goals", tag: "Virtual Earmarks",
      sections: [
        { heading: "What A Goal Is", text: "A claim over money already sitting in tracked accounts \u2014 never an addition to net worth. You are not moving shekels, you are naming what they are for." },
        { heading: "Operations", items: ["Name, target amount, opening balance, optional monthly cap and target date", "Priority order \u2014 drag to reorder; changes apply forward", "Link a transaction as a contribution or a utilization", "Pay for a project, a yearly envelope or any category/tags from a goal \u2014 one link, every matching purchase (past and future, card purchases included) counts as spent from the goal", "Back a goal with an investment you mean to liquidate", "Close a goal \u2014 its allocations freeze and can never be reclaimed"] },
        { heading: "Rewriting History", text: "A priority change applies from today. Recomputing past months is an explicit rebuild, and it is previewed before it is written." },
      ],
    },
    "recurring-review": {
      title: "Recurring Review", tag: "Confirm / Dismiss",
      sections: [
        { heading: "Nothing Is Assumed", text: "Detection only proposes. A candidate stays pending until you rule on it, and only confirmed charges reach the budget\u2019s fixed/variable split, the forecast\u2019s safe-to-spend, and the insight cards." },
        { heading: "Verdicts", items: ["Confirm \u2014 it is a real commitment", "Dismiss \u2014 it is not; hidden, but listed under \u201cshow dismissed\u201d with its amount and cadence", "Back to review \u2014 undo either one", "Ended charges hide behind a toggle: already out of the monthly total, so history rather than commitment"] },
        { heading: "Why Verdicts Survive", text: "A decision is keyed by the normalized merchant label detection groups on \u2014 not by a transaction id \u2014 so it outlives new charges, amount drift and re-detection. Writing a verdict runs no detection at all; the card patches its own cached row so it moves on click." },
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
        { heading: "unique_id Is Per-Table", text: "Each table has its own auto-increment \u2014 bank #5 and credit-card #5 are different transactions. Merged or cross-table data is always keyed by the pair (source, unique_id), never by the bare id." },
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
        { heading: "Sources", items: ["manual \u2014 user-entered, wins over the others", "calculated \u2014 daily compounding for fixed and prime-linked rates", "scraped \u2014 live Keren Hishtalmut policy values"] },
        { heading: "Closing", text: "Closing auto-creates a 0-balance snapshot on the last transaction date \u2014 not the closure date." },
        { heading: "The Closing Zero Follows", text: "A withdrawal that lands after the close would otherwise be carried past that zero and value the fund below zero in net worth. Every write path that can add, re-date or retag a transaction re-aligns closed investments." },
      ],
    },
    "meta-tables": {
      title: "Metadata Tables", tag: "Configuration",
      sections: [
        { heading: "Tables", items: ["categories \u2014 name, tags (JSON), icon", "tagging_rules \u2014 name, conditions (recursive JSON), category, tag", "budget_rules \u2014 amount, category, tags (semicolon-separated), period_type, is_closed", "investments + insurance_accounts \u2014 type, rates, commissions, policy metadata", "liabilities + liability_transactions \u2014 principal, rate, term, generated payments", "pending_refunds, refund_links, refund_source_notes", "interest_rates \u2014 Bank of Israel key-rate history", "scraping_history \u2014 the per-account success watermark", "retirement_goal \u2014 the single FIRE plan"] },
        { heading: "Budget Kinds Are Explicit", text: "budget_rules.period_type discriminates monthly, yearly and project rules as a column \u2014 not inferred from which fields happen to be null." },
      ],
    },
    "goal-tables": {
      title: "Savings Goal Tables", tag: "Earmarks",
      sections: [
        { heading: "Tables", items: ["savings_goals \u2014 target, opening balance, priority, monthly cap, status", "savings_goal_allocations \u2014 one row per (goal, month), auto or manual", "savings_goal_links \u2014 transactions tied to a goal as contribution or utilization", "savings_goal_investments \u2014 holdings earmarked to back a goal"] },
        { heading: "Why Allocations Persist", text: "Progress is derived from surplus, but the derivation is stored per month so a later priority change does not silently rewrite last year. Rewriting is an explicit, previewed rebuild." },
      ],
    },
    "decision-tables": {
      title: "Decisions & Overrides", tag: "Sticky Verdicts",
      sections: [
        { heading: "Tables", items: ["recurring_decisions \u2014 pending / confirmed / dismissed per normalized merchant key", "insight_dismissals \u2014 dismissed insight cards, restorable", "budget_month_overrides \u2014 the budget month a transaction is counted in"] },
        { heading: "Keyed To Outlive Detection", text: "A verdict is stored against the same normalized label detection groups on, and a dismissal key encodes what its card is about \u2014 a month, a (source, unique_id), a merchant and a price. So a verdict survives re-detection, and a dismissal lapses exactly when the thing it was about changes." },
      ],
    },
    "credentials-vault": {
      title: "Credential Vault", tag: "Keyring + Fernet",
      sections: [
        { heading: "Where Secrets Live", items: ["Passwords: the OS Keyring, never in code, YAML or the database", "Usernames, ID numbers and card digits: Fernet-encrypted in the DB, key also in the Keyring", "All keyring access goes through one module \u2014 nothing else imports keyring directly"] },
        { heading: "Refusals", text: "An insecure keyring backend (null or plaintext) is rejected on credential writes. CI and sandboxes opt in explicitly." },
        { heading: "2FA", text: "Providers that need an OTP prompt the browser through an async callback during the scrape \u2014 the code is never stored." },
      ],
    },
    "analysis-svc": {
      title: "AnalysisService", tag: "11 KPI Reads",
      sections: [
        { heading: "Core KPIs", items: ["overview \u2014 totals + net change", "income-expenses-over-time \u2014 monthly bars", "net-balance-over-time \u2014 cumulative trend", "net-worth-over-time \u2014 bank + cash + investments", "expenses-by-category-over-time", "sankey \u2014 income \u2192 expenses flow", "income-by-source (+ over time) \u2014 stacked breakdown", "debt-payments-over-time, monthly-expenses (spending heatmap)"] },
        { heading: "Transaction Masks", items: ["Income: Salary, Other Income, + positive Liabilities", "Investment: Investments category", "Expense: everything else + negative Liabilities"] },
        { heading: "Also Hosted Here", text: "The same service hosts the cash-flow forecast, which is its own card here. Recurring detection and insights are separate services reading the same merged transaction view." },
      ],
    },
    "forecast-svc": {
      title: "Cash-Flow Forecast", tag: "Safe To Spend",
      sections: [
        { heading: "How It Projects", items: ["Month-to-date actuals + a trend estimate for the days that are left", "Expense trend: rolling 3-month average, falling back to 6 or 12 when sparse", "Income trend: the average of the last 3 complete months", "The projection never dips below money already spent"] },
        { heading: "Safe To Spend", text: "expected income \u2212 actual expenses \u2212 committed remaining, floored at zero, and also given per remaining day. Committed remaining is the confirmed recurring charges still due before month end \u2014 the rent that has not left yet is not spending money." },
        { heading: "Outputs", items: ["Projected month-end bank balance and net", "A per-day trajectory: actual up to today, projected after", "The trend baselines themselves, so the number can be argued with"] },
      ],
    },
    "recurring-svc": {
      title: "Recurring Detection", tag: "5 Cadence Bands",
      sections: [
        { heading: "What Qualifies", items: ["One of five cadence bands \u2014 monthly, bimonthly, quarterly, semiannual, annual \u2014 each with its own tight tolerance", "Nothing below a month is a cadence: weekly rhythms are habits, not billing", "An interval-regularity gate on the robust spread of the gaps", "An amount path: fixed (\u2265 75% of charges within \u00B115%) or metered (a consumption bill: \u00B150%, but a tighter schedule and \u2265 6 sightings)"] },
        { heading: "Day-Of-Month", text: "Anchoring only scores a candidate, never rejects one \u2014 real bills slip five or six days around weekends and month ends." },
        { heading: "Confidence", text: "Every candidate carries a 0\u20131 score over regularity, interval shape, day anchoring, amount stability and evidence count. It ranks the review list; it does not decide anything on its own." },
      ],
    },
    "insights-svc": {
      title: "InsightsService", tag: "Dismissible",
      sections: [
        { heading: "Unexplained And Material", items: ["Project and yearly spend is lumpy by design \u2014 never a spike or a surprise charge", "A category still inside its monthly budget is not a spike", "A confirmed recurring charge is never a large-charge surprise \u2014 rent is big every month", "A spike\u2019s baseline is the median of the last 3 months, and the category must appear in at least 2"] },
        { heading: "Scaled To The Household", text: "Shekel floors are max(absolute, a share of typical monthly outflow), so the same rule fits a small budget and a large one. Cards sort by severity, then by the money involved, capped at 6." },
        { heading: "Dismissal", text: "Each card has a stable key encoding what it is about \u2014 a month, a (source, unique_id), a merchant and a price. Dismiss it and it stays gone until that changes. Filtering happens before each rule\u2019s cap, so a dismissal frees its slot for the runner-up." },
      ],
    },
    "budget-svc": {
      title: "BudgetService", tag: "Budget vs Actual",
      sections: [
        { heading: "Features", items: ["Monthly limits per category/tag, plus the Total Budget cap", "Yearly rules and project rules, open or closed", "Pending-refund adjustments so a refundable expense is not flagged as overspend", "Alerts, per-rule sparklines and a trend view"] },
        { heading: "The Overview", items: ["Splits the month into fixed (confirmed recurring) and variable spend", "committed_remaining \u2014 confirmed charges still due this month", "free_to_spend = budget \u2212 spent \u2212 committed", "long_envelopes \u2014 the open yearly and project rules, and the needs-attention rows built from them"] },
        { heading: "Closed Still Counts", text: "A closed project or yearly rule leaves the Overview but its spend stays in total out \u2014 that money did leave the accounts. What it loses is attention, not arithmetic." },
        { heading: "Exclusions", text: "Credit Cards, Investments, Liabilities and Ignore are excluded from budget calculations." },
      ],
    },
    "goals-svc": {
      title: "Savings Goals Engine", tag: "Surplus Waterfall",
      sections: [
        { heading: "The Waterfall", items: ["Each month\u2019s realized surplus is income \u2212 expenses \u2212 investments, CC-deduped", "It flows down the goals by priority, each taking min(remaining need, monthly cap)", "Linked transactions are pulled out of the surplus and reintroduced explicitly, so no shekel counts twice", "What no goal claims stays in the free-cash pool"] },
        { heading: "A Bad Month", text: "A month that spends more than it earns drains free cash first. Only once that is empty does the shortfall come back out of the goals, lowest priority first, each giving back at most what is funded but not yet spent \u2014 money already spent can never be reclaimed." },
        { heading: "Investment-Backed", text: "A goal can be backed by a holding you mean to liquidate. It counts toward funded and shrinks what the goal needs from surplus, but it is not cash: never in the free-cash pool, never clawed back, reported separately." },
        { heading: "Closed Goals", text: "Frozen. Their allocations can never be reclaimed or clawed back." },
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
        { heading: "Loan Types", items: ["Fixed unlinked \u2014 one rate for the whole term", "Prime-linked \u2014 prime + a per-loan spread, re-priced at every Bank of Israel step", "Variable unlinked \u2014 resets to the prime of the reset date every rate_reset_months, flat in between"] },
        { heading: "Category", text: "Positive = loan receipts (income). Negative = debt payments (override into expenses despite Liabilities being a non-expense category)." },
      ],
    },
    "rates-svc": {
      title: "RatesService", tag: "BOI Prime",
      sections: [
        { heading: "What It Answers", items: ["The current prime rate and the key-rate history behind it", "The prime in effect at any given date", "The sequence of prime steps from a date forward \u2014 what re-prices a variable loan"] },
        { heading: "Why It Is Stored", text: "Amortization and compounding have to be reproducible offline, so the history is seeded on first run and refreshed on demand rather than fetched per calculation." },
      ],
    },
    "retire-svc": {
      title: "RetirementService", tag: "Real Terms",
      sections: [
        { heading: "Everything In Today\u2019s Shekels", text: "The whole model is real-terms \u2014 a nominal return is converted through inflation before it is used, so a projection 30 years out is readable as money you understand now." },
        { heading: "Inputs", items: ["Net worth, income, expenses, savings rate", "Target retirement age, life expectancy, monthly expenses in retirement", "Return rate and withdrawal rate", "Pension and Keren Hishtalmut buckets, pre-filled from scraped data where available"] },
        { heading: "Counting KH Once", text: "Scraped Keren Hishtalmut policies are already inside tracked net worth. The model swaps that tracked value out before adding the goal\u2019s KH bucket, so it counts exactly once for scraped and typed-only users alike." },
        { heading: "Outputs", items: ["Years to financial independence and a net-worth projection", "Whether the plan survives drawdown to life expectancy, and where it depletes if not", "Solve for a single field \u2014 what retirement age, spend, return or life expectancy would make the plan work", "Optimization suggestions"] },
      ],
    },
    "onboarding-page": {
      title: "Onboarding", tag: "First Run",
      sections: [
        { heading: "The Gate", text: "A fresh install has nothing to show, so every route sits behind a gate until there is data. The gate asks the backend what exists rather than guessing from a local flag." },
        { heading: "Ways In", items: ["Connect a bank or credit-card account and scrape it", "Enter balances and transactions by hand", "Turn on Demo Mode and explore the sample household first"] },
      ],
    },
    dashboard: {
      title: "Dashboard", tag: "14 Cards",
      sections: [
        { heading: "Cards", items: ["This-month forecast and safe-to-spend", "Insights strip \u2014 dismissible, deduplicated against the other cards", "Budget, recurring charges, savings goals, pending refunds", "Net worth, income vs expenses, income by source, category breakdown, spending heatmap, cash flow, early retirement"] },
        { heading: "Your Layout, Your Browser", text: "Card order and which cards are hidden is a per-browser preference. The pinned KPI header stays put; everything below it can be reordered or hidden from Settings \u2192 Dashboard." },
        { heading: "No Card Repeats Another", text: "The insights strip drops its pace cards while the forecast card is on screen, and its recurring cards while the recurring card is \u2014 which cards are visible is a browser-local preference the backend cannot see, so the strip does that filtering itself." },
      ],
    },
    "txn-page": {
      title: "Transactions Page", tag: "Filterable",
      sections: [
        { heading: "Features", items: ["Sortable, filterable table", "Inline tag editing and bulk operations", "Split creation, pending refunds, refund linking", "Move a charge to a neighbouring budget month without changing its date", "Link a transaction to a savings goal as a contribution or a utilization"] },
        { heading: "Editability", text: "A scraped transaction only allows category and tag changes. A manual one is fully editable and deletable." },
        { heading: "Cache Invalidation", text: "Every write cancels the reads that predate it, then invalidates transactions, categories and the analytics queries \u2014 so a response computed before the write cannot land on top of it." },
      ],
    },
    "budget-page": {
      title: "Budget Page", tag: "Overview + 3 Tabs",
      sections: [
        { heading: "Views", items: ["Overview \u2014 fixed vs variable, free to spend, long rules needing attention", "Monthly \u2014 ledger rows with sparklines and a per-tag breakdown", "Yearly \u2014 annual rules, open and closed", "Projects \u2014 one tab per project, closed ones included"] },
        { heading: "Alongside", items: ["Savings goals section", "Pending refunds section", "Budget alerts, also reachable from the bell in the sidebar", "A freshness badge so a stale scrape does not read as an underspend", "A dismissible notice for pre-existing category conflicts"] },
      ],
    },
    "invest-page": {
      title: "Investments Page", tag: "Portfolio",
      sections: [
        { heading: "Views", items: ["Portfolio: total value, profit, ROI", "Allocation pie chart", "Balance history line chart", "Individual analysis modal", "Keren Hishtalmut policies alongside typed-in holdings", "Prime-linked positions re-priced from the Bank of Israel history"] },
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
        { heading: "Components", items: ["Retirement goal form, pre-fillable from scraped pension and KH data", "Status grid \u2014 savings rate, years to FI, readiness", "Projection charts in today\u2019s shekels", "Solve-for-a-field: what would have to change for the plan to work", "Optimization suggestions"] },
      ],
    },
    "categories-page": {
      title: "Categories Page", tag: "Management",
      sections: [
        { heading: "Features", items: ["Create/rename/delete categories and tags", "Drag-and-drop reorder", "Tagging rules builder with preview", "Tag reallocation between categories"] },
      ],
    },
    "insurance-page": {
      title: "Pension Savings Page", tag: "Funds",
      sections: [
        { heading: "Features", items: ["Retirement outlook from the clearing house: expected monthly pension, lump sum, projected savings and insurance cover", "Savings KPIs: total balance, deposits over the last 12 months, profit and costs this year, balance-weighted management fee", "Pension and Keren Hishtalmut fund cards", "Deposit history with the employee / employer / compensation breakdown", "Investment track information and commissions", "Rename a policy, and sync hishtalmut policies into tracked investments"] },
      ],
    },
    "demo-mode": {
      title: "Demo Mode", tag: "Toggle",
      sections: [
        { heading: "How It Works", items: ["Toggle in Settings (sidebar) switches THIS browser only \u2014 other clients on the same backend are unaffected", "The choice is stored in localStorage and sent as the X-FAD-Demo request header", "Demo DB is a copy of bundled template with date-shifted data", "All dates relative to current date for realistic appearance", "Pre-seeded bank and credit card accounts (with/without 2FA)"] },
        { heading: "Scraper Redirect", text: "When demo mode is active, scraping requests are automatically redirected to dummy scrapers that generate fake data. No real financial institutions are contacted." },
        { heading: "Isolation", text: "Separate database \u2014 no production data is read or affected. Per-client: one browser can be in demo mode while another reads real data. Two clients both in demo mode do share one demo database." },
        { heading: "Hosted Demo", text: "On the public deployment each visitor gets their own sandbox database instead, mirrored to blob storage between requests so a write survives being served by a different instance." },
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
        { heading: "Features", items: ["Bank, credit-card and insurance account management", "Scraping triggers with live progress, per account or all at once", "2FA prompts surfaced inline during a run", "Stale data alerts", "Credential management via the OS Keyring"] },
      ],
    },
    "settings-page": {
      title: "Settings", tag: "Layout + Demo",
      sections: [
        { heading: "Panels", items: ["Dashboard \u2014 reorder cards, hide cards, opt into experimental ones", "Budget alert thresholds", "Language and direction \u2014 English or Hebrew, RTL switches automatically", "Demo Mode toggle", "Backups: create, list, restore", "App version, update check, uninstall"] },
        { heading: "Per-Browser", text: "Layout, language and the demo flag live in that browser\u2019s localStorage, not on the server \u2014 two people on the same backend can see it their own way." },
      ],
    },
    pwa: {
      title: "PWA & Offline", tag: "Service Worker",
      sections: [
        { heading: "What Is Cached", items: ["The build itself is precached \u2014 the app opens offline", "API GETs are network-first with a fallback to the last good response", "Credentials, scraping and backup endpoints are never cached", "The React Query cache persists to IndexedDB across reloads"] },
        { heading: "Network-First, Not Timeout-First", text: "The fallback fires the moment a request errors. The timeout only bounds a connection that is up and silent, so it sits well above any plausible recompute \u2014 otherwise a slow-but-healthy read gets answered with the body from before your last write." },
        { heading: "Also", items: ["Installable on phone and desktop", "Toasts for service-worker updates and for going offline", "Mobile-first responsive layout throughout"] },
      ],
    },
  },

  platformFeatures: [
    {
      title: "Split Transactions",
      desc: "One charge often covers different things \u2014 split it across categories so your reports stay accurate.",
      highlights: [
        "A single supermarket receipt can become Food + Household + Pharmacy",
        "Each split has its own amount, category, and tag",
        "The original transaction stays intact, splits flow into every chart and budget",
      ],
    },
    {
      title: "Tagging & Auto-Tagging",
      desc: "Categorize once and forget it. Custom rules quietly tag every new transaction the moment it arrives.",
      highlights: [
        "Build rules from description, account, amount, or any combination",
        "Creation order \u2014 first match wins, conflicts are flagged before you save",
        "Manual override anytime, single transaction or in bulk",
      ],
    },
    {
      title: "Monthly, Yearly & Project Budgets",
      desc: "Three kinds of rule, because not every commitment repeats every month.",
      highlights: [
        "Monthly limits per category, or one total cap",
        "Yearly rules for the lumpy things \u2014 insurance, car test, tuition",
        "Project rules for a renovation or a trip; close one when it's done and it keeps its history",
        "Copy last month's (or last year's) rules forward in one click",
        "Move a charge to a neighbouring month when it lands on the wrong side of the 1st",
        "Pending refunds adjust spent amounts so you don't get false 'overspent' alerts",
      ],
    },
    {
      title: "Savings Goals",
      desc: "Name what your money is for. Goals are earmarks over cash you already have \u2014 never an imaginary extra balance.",
      highlights: [
        "Each month's leftover flows down your goals in priority order",
        "An optional monthly cap keeps one goal from eating the whole surplus",
        "What no goal claims stays in a free-cash pool you can see",
        "A bad month drains free cash first, and only gives back what a goal hasn't already spent",
        "Back a goal with an investment you plan to liquidate",
      ],
    },
    {
      title: "Recurring Charges, Confirmed By You",
      desc: "The app spots what looks like a standing commitment \u2014 then asks, instead of assuming.",
      highlights: [
        "Monthly through annual cadences, judged on timing regularity and amount stability",
        "Metered bills (electricity, water) are allowed to vary; they just need a tighter schedule",
        "Confirm, dismiss, or send one back to review \u2014 nothing is final",
        "Only confirmed charges shape your budget's fixed/variable split and safe-to-spend",
        "A verdict survives new charges, price changes and re-detection",
      ],
    },
    {
      title: "Insights & This-Month Forecast",
      desc: "A short strip of things worth knowing, and a projection of where the month actually lands.",
      highlights: [
        "Safe-to-spend nets out the bills that haven't left yet",
        "Spikes compare against the median of recent months, not a one-off",
        "Nothing your budget already plans for gets flagged \u2014 projects and yearly rules stay quiet",
        "Every card can be dismissed, and the next-best one takes its slot",
      ],
    },
    {
      title: "Investment Portfolio Tracking",
      desc: "Track deposits, withdrawals, current value, profit/loss and ROI for every investment account.",
      highlights: [
        "Manual or fixed-rate balance snapshots over time",
        "Auto-compounded daily growth for fixed-rate investments",
        "Close, reopen, and edit close dates whenever life changes",
        "Per-investment analysis modal plus a portfolio-wide overview",
      ],
    },
    {
      title: "Loans, Liabilities & Refunds",
      desc: "Keep tabs on the money flowing the other way \u2014 debt payments, loan amortization, and pending refunds.",
      highlights: [
        "Full amortization schedule for every loan you track",
        "Fixed, prime-linked and periodically-resetting loans, priced off real Bank of Israel rates",
        "Mark transactions as 'pending refund' so they don't pollute your budget",
        "Link partial or full refunds when the money actually comes back",
        "Status tracking from pending \u2192 partial \u2192 resolved \u2192 closed",
      ],
    },
    {
      title: "Early Retirement Planning",
      desc: "A FIRE calculator that speaks in today's shekels and knows how Israeli retirement savings actually work.",
      highlights: [
        "Everything real-terms \u2014 a projection 30 years out is still money you recognise",
        "Pension and Keren Hishtalmut buckets, pre-filled from your scraped policies",
        "Scraped KH is counted exactly once, never double-added to net worth",
        "Ask it to solve: what retirement age, spend or return would make this plan work?",
      ],
    },
    {
      title: "Bilingual & Mobile-Friendly",
      desc: "Built for Hebrew and English speakers, on phone or desktop, online or offline.",
      highlights: [
        "Full Hebrew + English with automatic RTL layout switching",
        "Mobile-first responsive design from phone to widescreen",
        "Installable PWA that works offline with cached data",
        "Demo mode for safe exploration without touching real finances",
      ],
    },
  ],

  callouts: [
    { title: "Auto-sync from Israeli banks and credit cards.", text: "Connect your accounts once and let the app handle the rest \u2014 17 bank providers and 6 credit card providers supported, with 2FA out of the box. Credentials live in your OS keyring, never in plain text." },
    { title: "Categories that travel with your data.", text: "Rename a category and every transaction, split, rule, and budget updates automatically. Drag-and-drop to reorder. Custom tags inside each category give you finer control without cluttering the top level." },
    { title: "Net worth, cash flow, and FIRE projections.", text: "See where every shekel goes with a Sankey flow chart, watch your net worth trend over time, and run early-retirement scenarios with the built-in FIRE calculator \u2014 all from the same data." },
    { title: "Try everything without risk via Demo Mode.", text: "Open Settings from the sidebar and toggle demo mode to switch to an isolated database with realistic sample data. Explore every feature, click every button, then switch back when you're done. Your real finances stay untouched." },
    { title: "Backups and history, just in case.", text: "Snapshot your data anytime, browse your backup list, and restore on demand. A safety backup is taken first, so even an accidental restore can be undone." },
    { title: "Nothing is decided behind your back.", text: "A detected subscription stays pending until you confirm it. An insight card can be dismissed and comes back only if the thing it was about changes. A finished project or yearly rule is closed, not deleted \u2014 it keeps its history and its category. The app proposes; you rule." },
    { title: "Your data stays on your machine.", text: "Everything lives in a local SQLite file. Passwords sit in the OS keyring, other credential fields are encrypted at rest, and the API refuses requests that don't come from you. Install it as an app and it keeps working offline on cached data." },
  ],
};

export default content;
