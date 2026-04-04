# Data Flow Architecture

How data moves through the Finance Analysis system — from external sources to user-facing dashboards.

---

## High-Level Overview

```mermaid
flowchart TB
    subgraph Sources ["Data Sources"]
        BANKS[("Israeli Banks\n(17 providers)")]
        CC[("Credit Cards\n(6 providers)")]
        INS[("Insurance\n(1 provider)")]
        MANUAL["Manual Entry\n(UI forms)"]
    end

    subgraph Ingestion ["Ingestion Layer"]
        SCRAPER["Scraper Framework\n(Playwright / httpx)"]
        ADAPTER["ScraperAdapter\n(Result → DataFrame → DB)"]
        ROUTES_IN["API Routes\n(POST /transactions, etc.)"]
    end

    subgraph Processing ["Processing Layer"]
        TAGGING["Auto-Tagging Engine\n(rule-based categorization)"]
        BALANCE["Balance Recalculation\n(bank, cash, investments)"]
        PRIOR["Prior Wealth Calculation\n(starting capital offsets)"]
        SPLITS["Split Transaction\nMerging"]
    end

    subgraph Storage ["Storage (SQLite)"]
        DB_TXN[("Transaction Tables\n5 tables")]
        DB_BAL[("Balance Tables\nbank, cash, snapshots")]
        DB_META[("Metadata Tables\ncategories, rules,\nbudgets, investments")]
    end

    subgraph Analytics ["Analytics Layer"]
        ANALYSIS["AnalysisService\n(KPI calculations)"]
        BUDGET["BudgetService\n(budget vs actual)"]
        INVEST["InvestmentsService\n(P&L, ROI, CAGR)"]
        LIAB["LiabilitiesService\n(amortization)"]
        RETIRE["RetirementService\n(FIRE projections)"]
    end

    subgraph Frontend ["Frontend (React)"]
        DASH["Dashboard\n(overview, charts, sankey)"]
        TXN_PAGE["Transactions\n(table, filters, tagging)"]
        BUDGET_PAGE["Budget\n(monthly + projects)"]
        INV_PAGE["Investments\n(portfolio, analysis)"]
        LIAB_PAGE["Liabilities\n(debt tracking)"]
        RETIRE_PAGE["Early Retirement\n(FIRE calculator)"]
    end

    BANKS --> SCRAPER
    CC --> SCRAPER
    INS --> SCRAPER
    MANUAL --> ROUTES_IN

    SCRAPER --> ADAPTER
    ADAPTER --> DB_TXN
    ADAPTER --> TAGGING
    ADAPTER --> BALANCE
    ROUTES_IN --> DB_TXN
    ROUTES_IN --> PRIOR

    TAGGING --> DB_TXN
    BALANCE --> DB_BAL
    PRIOR --> DB_BAL

    DB_TXN --> ANALYSIS
    DB_TXN --> BUDGET
    DB_TXN --> INVEST
    DB_TXN --> LIAB
    DB_BAL --> ANALYSIS
    DB_BAL --> INVEST
    DB_META --> BUDGET
    DB_META --> INVEST

    ANALYSIS --> DASH
    BUDGET --> BUDGET_PAGE
    INVEST --> INV_PAGE
    LIAB --> LIAB_PAGE
    RETIRE --> RETIRE_PAGE
    DB_TXN --> TXN_PAGE
```

---

## 1. Data Sources & Ingestion

### Where Data Comes From

| Source | Method | Frequency | What It Produces |
|--------|--------|-----------|------------------|
| **Banks** (Hapoalim, Leumi, Discount, etc.) | Playwright browser scraping | On-demand (daily limit) | Account transactions + balance |
| **Credit Cards** (Max, Visa Cal, Isracard, etc.) | Playwright browser scraping | On-demand (daily limit) | Itemized purchases |
| **Insurance** (Hafenix) | Playwright browser scraping | On-demand | Pension/savings transactions + metadata |
| **Manual Cash** | UI form → `POST /transactions/` | User-initiated | Cash transactions |
| **Manual Investments** | UI form → `POST /transactions/` | User-initiated | Investment deposit/withdrawal records |
| **Balance Entry** | UI form → `POST /cash_balances/` or `POST /bank_balances/` | After scraping or manually | Current balance → prior wealth offset |

### Scraping Pipeline

```mermaid
sequenceDiagram
    participant UI as Frontend
    participant API as ScrapingService
    participant Adapter as ScraperAdapter
    participant Scraper as Provider Scraper
    participant Site as Financial Site
    participant DB as SQLite

    UI->>API: POST /scraping/start
    API->>API: Look up credentials
    API->>API: Calculate start_date (last scrape - 7d)
    API->>DB: Record scraping_history (IN_PROGRESS)
    API-->>UI: Return process_id

    API->>Adapter: asyncio.create_task(run())
    Adapter->>Scraper: create_scraper(provider, credentials)
    Scraper->>Site: Launch browser, login, navigate

    alt 2FA Required
        Scraper-->>Adapter: OTP callback
        Adapter-->>API: Status: WAITING_FOR_2FA
        UI->>API: POST /scraping/2fa {code}
        API->>Adapter: set_otp_code(code)
        Adapter->>Scraper: Resume with OTP
    end

    Scraper->>Site: Fetch transactions
    Site-->>Scraper: Raw transaction data
    Scraper-->>Adapter: ScrapingResult {accounts, transactions}

    Note over Adapter: Pipeline starts
    Adapter->>Adapter: 1. Result → DataFrame
    Adapter->>DB: 2. INSERT/UPDATE transactions
    Adapter->>DB: 3. Auto-tag (rules engine)
    Adapter->>DB: 4. Recalculate bank balances
    Adapter->>DB: 5. Record scraping_history (SUCCESS)

    UI->>API: GET /scraping/status (polling)
    API-->>UI: {status: "done"}
```

### Transaction Data Shape

Every transaction, regardless of source, is normalized to this schema:

```
unique_id       Auto-increment PK (internal)
id              Original provider ID
date            YYYY-MM-DD
amount          Negative = expense, Positive = income
description     Transaction description
provider        e.g., "hapoalim", "max"
account_name    User-given name for the account
account_number  Provider account number
category        e.g., "Food", "Transport" (null if untagged)
tag             e.g., "Groceries", "Gas" (null if untagged)
source          Table name: bank_transactions, credit_card_transactions, etc.
type            "normal" or "split_parent"
status          "completed" or "pending"
```

---

## 2. Storage Schema

### Transaction Tables (5 parallel tables, identical schema)

```mermaid
erDiagram
    bank_transactions ||--o{ split_transactions : "splits"
    credit_card_transactions ||--o{ split_transactions : "splits"
    cash_transactions ||--o{ split_transactions : "splits"
    manual_investment_transactions ||--o{ split_transactions : "splits"
    insurance_transactions ||--o{ split_transactions : "splits"

    bank_transactions {
        int unique_id PK
        text id
        text date
        float amount
        text description
        text provider
        text account_name
        text category
        text tag
        text source
    }

    split_transactions {
        int id PK
        int transaction_id FK
        text source
        float amount
        text category
        text tag
    }
```

### Balance & Metadata Tables

```mermaid
erDiagram
    investments ||--o{ investment_balance_snapshots : "snapshots"
    investments ||--o{ manual_investment_transactions : "linked via category+tag"
    liabilities ||--o{ liability_transactions : "payments"

    bank_balances {
        text provider
        text account_name
        float balance
        float prior_wealth_amount
    }

    cash_balances {
        text account_name
        float balance
        float prior_wealth_amount
    }

    investments {
        int id PK
        text category
        text tag
        text type
        text name
        float interest_rate
        text interest_rate_type
        float prior_wealth_amount
        bool is_closed
    }

    investment_balance_snapshots {
        int id PK
        int investment_id FK
        text date
        float balance
        text source "manual|calculated|scraped"
    }

    categories {
        text name PK
        json tags
        text icon
    }

    tagging_rules {
        int id PK
        text name
        json conditions "recursive AND/OR tree"
        text category
        text tag
        int priority
    }

    budget_rules {
        int id PK
        text name
        float amount
        text category
        text tags "semicolon-separated"
        int year
        int month "null = project budget"
    }

    liabilities {
        int id PK
        text name
        text tag
        float principal_amount
        float interest_rate
        int term_months
        text start_date
        bool is_paid_off
    }
```

---

## 3. Processing Layer

### Auto-Tagging Engine

```mermaid
flowchart LR
    NEW_TX["New Untagged\nTransactions"] --> RULES["Tagging Rules\n(priority DESC)"]
    RULES --> EVAL{"Evaluate\nConditions"}
    EVAL -->|Match| TAG["Set category + tag"]
    EVAL -->|No match| SKIP["Leave untagged"]

    CC_MATCH["CC Bill Matching\n(bank debit ≈ CC total)"] --> TAG_CC["Tag as 'Credit Cards'\ncategory"]
```

**Rule conditions** are recursive trees supporting:
- **Operators:** AND, OR, CONDITION
- **Fields:** description, account_name, provider, amount
- **Comparisons:** contains, equals, starts_with, gt, lt, between

**CC bill auto-tagging** matches bank debits to monthly CC totals (shifted +1 month, ±0.01 tolerance).

### Prior Wealth Calculation

Prior wealth bridges the gap between "system started tracking" and "actual account balance":

```
prior_wealth = user_entered_balance - sum(all_tracked_transactions)
```

| Account Type | When Calculated | Stored In |
|-------------|-----------------|-----------|
| **Bank** | User enters balance after scraping | `bank_balances.prior_wealth_amount` |
| **Cash** | User enters balance via UI | `cash_balances.prior_wealth_amount` |
| **Investments** | From investment transactions | `investments.prior_wealth_amount` |

Prior wealth is injected as **synthetic transaction rows** (tag: "Prior Wealth") into analysis DataFrames so it flows through all KPI calculations consistently.

### Split Transactions

```mermaid
flowchart LR
    PARENT["Parent Transaction\n-500 (Supermarket)"] -->|Split| S1["Split 1: -300\nFood / Groceries"]
    PARENT -->|Split| S2["Split 2: -200\nHome / Cleaning"]

    PARENT -.->|type = split_parent\nExcluded from totals| X["Excluded"]
    S1 -->|Included| ANALYSIS["Analysis"]
    S2 -->|Included| ANALYSIS
```

Parent stays in the main table (marked `type=split_parent`). Splits live in `split_transactions`. The service layer merges them for analysis, replacing parents with their splits.

---

## 4. Credit Card Deduplication

The most critical data flow concern. Two overlapping views of CC spending exist:

```mermaid
flowchart TD
    subgraph Bank View
        BILL["Bank Transaction\n-3,000 (CC Bill Payment)\ncategory: Credit Cards"]
    end

    subgraph CC View
        CC1["-800 Food"]
        CC2["-600 Transport"]
        CC3["-1,200 Shopping"]
        CC4["-400 Entertainment"]
    end

    BILL -.->|"These represent\nthe same money"| SUM["Total: -3,000"]
    CC1 & CC2 & CC3 & CC4 --> SUM

    subgraph Rules ["Deduplication Strategy"]
        AGG["Aggregate KPIs\n(income, balance, net worth)"]
        CAT["Category Breakdowns\n(pie charts, budgets)"]
    end

    BILL -->|"Use bank view\nExclude CC source"| AGG
    CC1 & CC2 & CC3 & CC4 -->|"Use itemized view\nExclude 'Credit Cards' category"| CAT
```

| Use Case | Strategy | Implementation |
|----------|----------|----------------|
| Total income/expenses | Bank view only | Filter `source != credit_card_transactions` |
| Net balance / net worth | Bank view only | `exclude_services=["credit_card_transactions"]` |
| Expense by category | Itemized CC view | Exclude "Credit Cards" category from bank txns |
| Sankey flow | Hybrid | Calculate CC gap, show as "Unknown" |

---

## 5. Analytics & KPI Calculations

### AnalysisService Data Flow

```mermaid
flowchart TB
    subgraph Input
        TXN["All Transactions\n(merged + splits)"]
        PW["Prior Wealth\n(synthetic rows)"]
        BAL["Bank/Cash/Inv\nBalances"]
    end

    subgraph Masks ["Transaction Classification"]
        INC_MASK["Income Mask\nSalary, Other Income,\n+ positive Liabilities"]
        INV_MASK["Investment Mask\nInvestments category"]
        EXP_MASK["Expense Mask\nEverything else\n+ negative Liabilities"]
    end

    subgraph KPIs ["KPI Methods"]
        OVERVIEW["get_overview()\nTotal Income, Expenses,\nInvestments, Net Change"]
        IE_TIME["get_income_expenses_over_time()\nMonthly bars"]
        NB_TIME["get_net_balance_over_time()\nCumulative balance line"]
        NW_TIME["get_net_worth_over_time()\nBank + Cash + Investments"]
        EXP_CAT["get_expenses_by_category()\nPie chart breakdown"]
        SANKEY["get_sankey_data()\nIncome → Expenses flow"]
        INC_SRC["get_income_by_source_over_time()\nStacked income bars"]
    end

    TXN --> Masks
    PW --> INC_MASK
    BAL --> NW_TIME

    INC_MASK --> OVERVIEW
    INV_MASK --> OVERVIEW
    EXP_MASK --> OVERVIEW

    INC_MASK --> IE_TIME
    EXP_MASK --> IE_TIME

    TXN -->|"Exclude CC source"| NB_TIME
    TXN -->|"Exclude CC source"| NW_TIME
    TXN -->|"Use CC items,\nexclude CC category"| EXP_CAT
    TXN -->|"Both views"| SANKEY
    INC_MASK --> INC_SRC
```

### Investment KPI Flow

```mermaid
flowchart LR
    TXN["Investment\nTransactions"] --> DEPOSITS["Total Deposits\nabs(sum of negatives)"]
    TXN --> WITHDRAWALS["Total Withdrawals\nsum of positives"]

    DEPOSITS --> NET["Net Invested\ndeposits - withdrawals"]

    SNAP["Balance Snapshots"] -->|"If available"| BALANCE["Current Balance"]
    TXN -->|"Fallback:\n-sum(all amounts)"| BALANCE

    BALANCE --> PL["Profit/Loss\nbalance - net_invested"]
    DEPOSITS --> ROI["ROI %\n(final_value / deposits - 1) * 100"]
    BALANCE --> ROI
    WITHDRAWALS --> ROI
```

### Budget Analysis Flow

```mermaid
flowchart LR
    RULES["Budget Rules\n(category + tags + amount)"] --> COMPARE
    TXN["Month's Transactions\n(expenses only)"] --> FILTER["Exclude:\nCredit Cards, Investments,\nLiabilities, Ignore"]
    FILTER --> AGG["Aggregate by\ncategory + tags"]
    AGG --> COMPARE{"Compare\nspent vs budget"}
    REFUNDS["Pending Refund\nAdjustments"] --> COMPARE
    COMPARE --> RESULT["Budget Status\n(under/over/on track)"]
```

---

## 6. Frontend Data Consumption

### API → UI Pipeline

```mermaid
flowchart LR
    API["FastAPI\nBackend"] -->|"axios /api/*"| TQ["TanStack Query\n(cache + refetch)"]
    TQ --> HOOKS["Custom Hooks\n(useCategories,\nuseCashBalances, etc.)"]
    HOOKS --> PAGES["Page Components"]
    PAGES --> UI["Charts, Tables,\nCards, Gauges"]

    MUTATIONS["User Actions\n(tag, split, create)"] -->|"useMutation"| API
    MUTATIONS -->|"invalidateQueries"| TQ
```

### What Each Page Fetches

```mermaid
flowchart TB
    subgraph Dashboard
        D1["analyticsApi × 10 endpoints"]
        D2["bankBalancesApi.getAll()"]
        D3["cashBalancesApi.getAll()"]
        D4["investmentsApi.getPortfolioAnalysis()"]
        D5["transactionsApi.getAll()"]
    end

    subgraph Transactions
        T1["transactionsApi.getAll()"]
        T2["cashBalancesApi.getAll()"]
        T3["pendingRefundsApi.getAll()"]
        T4["taggingApi.getCategories()"]
    end

    subgraph Budget
        B1["budgetApi.getRulesByMonth()"]
        B2["budgetApi.getAnalysis()"]
        B3["budgetApi.getProjects()"]
    end

    subgraph Investments
        I1["investmentsApi.getAll()"]
        I2["investmentsApi.getPortfolioAnalysis()"]
        I3["investmentsApi.getPortfolioBalanceHistory()"]
    end

    subgraph DataSources
        DS1["credentialsApi.getAll()"]
        DS2["scrapingApi.getLastScrapes()"]
        DS3["Polling: scrapingApi.getStatus()\nevery 2s while active"]
    end
```

### Cache Invalidation Strategy

When a mutation occurs, only affected queries are invalidated:

| Action | Invalidates |
|--------|------------|
| Tag a transaction | `transactions`, `categories`, 6 analytics queries |
| Split a transaction | `transactions`, analytics queries |
| Create budget rule | `budget-rules`, `budget-analysis` |
| Start scraping | Nothing (polling begins) |
| Scraping completes | `transactions`, `bank-balances`, `last-scrapes`, analytics |
| Set bank balance | `bank-balances`, analytics |
| Toggle demo mode | **All queries** (different database) |

---

## 7. Special Data Flows

### Net Worth Calculation

```
net_worth = bank_balance + cash_balance + investment_value

Where:
  bank_balance     = bank_prior_wealth + inv_prior_wealth + cumsum(non-CC transactions)
  cash_balance     = cash_prior_wealth + cumsum(cash transactions)
  investment_value = -cumsum(investment transactions)  [or snapshot if available]
```

Investment prior wealth lives inside bank balance because investment deposits originally came from bank accounts. This keeps the accounting identity balanced.

### Sankey Flow (Income → Expenses)

```mermaid
flowchart LR
    SAL["Salary"] --> TOTAL["Total Income"]
    OTHER["Other Income"] --> TOTAL
    PW["Prior Wealth"] --> TOTAL
    LIAB_IN["Loan Receipts\n(+Liabilities)"] --> TOTAL

    TOTAL --> FOOD["Food"]
    TOTAL --> TRANS["Transport"]
    TOTAL --> HOME["Home"]
    TOTAL --> OTHER_EXP["...other categories"]
    TOTAL --> DEBT["Debt Payments\n(-Liabilities)"]
    TOTAL --> UNKNOWN["Unknown\n(CC gap)"]
    TOTAL --> GROWTH["Wealth Growth\nor Deficit"]
```

The CC gap (difference between bank CC bill and sum of itemized CC purchases) appears as "Unknown" to maintain the accounting balance.

### Retirement (FIRE) Projections

```mermaid
flowchart LR
    STATUS["Current Status\n(net worth, income,\nexpenses, savings rate)"] --> PROJ["Projection Engine"]
    GOAL["Retirement Goal\n(target age, expenses,\nwithdrawal rate)"] --> PROJ
    PROJ --> TIMELINE["Years to FIRE"]
    PROJ --> CHART["Net Worth\nProjection Chart"]
    PROJ --> SUGGESTIONS["Optimization\nSuggestions"]
```

---

## 8. Architectural Rules Summary

1. **Amount sign convention:** negative = money out, positive = money in (everywhere)
2. **CC deduplication:** aggregate KPIs use bank view; category breakdowns use itemized CC view
3. **Prior wealth:** synthetic transaction rows injected into analysis DataFrames
4. **Investment balance:** snapshot-first, transaction-sum fallback
5. **Tagging:** priority-based rules (DESC order), first match wins
6. **Split transactions:** parent excluded, splits included in analysis
7. **Non-expense categories:** Investments, Liabilities (positive only), Income categories, Credit Cards
8. **Expense override:** negative Liabilities (debt payments) count as expenses despite being in a non-expense category
