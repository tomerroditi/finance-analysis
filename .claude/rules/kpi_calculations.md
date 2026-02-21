# KPI Calculations - Financial Analysis Logic

How we calculate financial KPIs across the dashboard. Every analytics method must follow these rules.

## Core Concepts

### Transaction Amount Convention
- **Negative = money out** (expenses, deposits into investments, CC bill payments)
- **Positive = money in** (salary, refunds, withdrawals from investments, loan receipts)

### Data Sources (Transaction Tables)

| Source | `source` column value | Contains |
|--------|----------------------|----------|
| Bank transactions | `bank_transactions` | Direct debits, deposits, CC bill payments, transfers |
| Credit card transactions | `credit_card_transactions` | Itemized CC purchases |
| Cash transactions | `cash_transactions` | Manual cash entries |
| Manual investments | `manual_investment_transactions` | Deposits/withdrawals to investment accounts |

### Category Classification

| Group | Categories | Role in KPIs |
|-------|-----------|--------------|
| **Income** | Salary, Other Income | Counted as income (positive amounts) |
| **Liabilities** | Liabilities | Positive = loan receipt (income), Negative = debt payment (expense) |
| **Non-Expense** | Salary, Other Income, Investments, Liabilities | Base exclusion set via constants: `INVESTMENTS_CATEGORY`, `LIABILITIES_CATEGORY`, and `IncomeCategories` enum (but negative Liabilities override — see below) |
| **Credit Cards** | Credit Cards | Bank-side CC bill payments — excluded from most KPIs (see CC Deduplication) |
| **Expense** | Everything else (Food, Transport, etc.) | Standard expense categories |

### Income Mask (used across methods)
A transaction is **income** if:
- Category is in `IncomeCategories` (Salary, Other Income), OR
- Category is `Liabilities` AND amount > 0 (loan receipt)

A transaction is an **expense** if:
- NOT matching the income mask, AND NOT in the non-expense categories (`INVESTMENTS_CATEGORY`, `LIABILITIES_CATEGORY`, or `IncomeCategories`), OR
- Category is `Liabilities` AND amount < 0 (debt payment — overrides non-expense category exclusion)

This ensures debt payments are counted as real money outflows in income/expense calculations.

## Credit Card Deduplication

This is the most critical pattern. Two overlapping data sources exist for credit card spending:

1. **CC bill payment** — A single bank transaction (source: `bank_transactions`, category: `Credit Cards`) representing the monthly consolidated CC bill debit.
2. **Itemized CC purchases** — Individual transactions (source: `credit_card_transactions`, various categories like Food, Transport) representing what was actually bought.

**These overlap.** A 1000 ILS CC bill is one bank transaction AND ~N itemized CC transactions totaling ~1000 ILS. Including both double-counts the spending.

### The CC Gap
The amounts don't always match exactly. The **CC gap** is:
```
cc_gap = abs(sum(bank CC bill payments)) - abs(sum(itemized CC transactions))
```
Causes: timing differences, pending transactions, fees, foreign currency rounding.

### Deduplication Rules by Method

| Method | Strategy | How |
|--------|----------|-----|
| `get_income_investments_and_expenses()` | Keep bank view, drop CC items | Filter `source != "credit_card_transactions"` |
| `get_net_balance_over_time()` | Keep bank view, drop CC items | `exclude_services=["credit_card_transactions"]` |
| `get_net_worth_over_time()` | Keep bank view, drop CC items | `exclude_services=["credit_card_transactions"]` |
| `get_income_by_source_over_time()` | Keep bank view, drop CC items | Filter `source != "credit_card_transactions"` |
| `get_expenses_by_category()` | Uses itemized CC view | Filter out non-expense categories (`INVESTMENTS_CATEGORY`, `LIABILITIES_CATEGORY`, `IncomeCategories`, `CREDIT_CARDS`) |
| `get_sankey_data()` | Hybrid — uses both to calculate gap | Calculates CC gap, then filters out `Credit Cards` category |

**Rule of thumb:**
- For **aggregate totals** (income, expenses, balances): use bank transactions only, exclude CC source.
- For **category breakdowns** (pie charts, per-category): use itemized CC transactions, exclude the "Credit Cards" bank category.
- For **flow diagrams** (Sankey): use both to detect the CC gap, then filter.

## Prior Wealth

Prior wealth represents money that existed **before the system started tracking transactions**. Without it, cumulative balance charts would start at zero instead of the user's actual starting balance.

### Three Sources of Prior Wealth

| Source | Stored In | Calculation | When Set |
|--------|-----------|-------------|----------|
| **Bank prior wealth** | `bank_balances.prior_wealth_amount` | `user_entered_balance - sum(all bank txns for account)` | Auto-computed when user enters current bank balance (after scraping) |
| **Investment prior wealth** | `investments.prior_wealth_amount` | `-(sum of manual_investment_transactions)` | Auto-recalculated when manually inserted investment transactions change |
| **Cash prior wealth** | Cash transactions tagged `"Prior Wealth"` under `"Other Income"` | Direct transaction amounts | Manually created by user in cash transactions only |

### Why Investment Prior Wealth Lives in Bank Balance

Manual investment transactions (deposits/withdrawals) are not linked to a specific bank account. But the money **did** flow from/to some bank or cash account. When calculating net worth over time:

- `bank_balance = (bank_prior_wealth + investment_prior_wealth) + cumulative(non-CC transactions)`
- `investment_value = -cumulative(investment transactions to date)`

This works because investment deposits (-1000) reduce `bank_balance` through the transaction sum, while simultaneously increasing `investment_value`. Net worth stays consistent:
```
net_worth = bank_balance + investment_value
         = (all_prior_wealth + bank_txns_including_inv_movements) + (-inv_txns)
```

The anchor point (1 month before earliest data) shows all prior wealth as `bank_balance` with `investment_value = 0`, representing the state before any tracked transactions.

### Prior Wealth in Overview & Sankey

- **Overview `total_income`**: Adds `bank_prior_wealth + investment_prior_wealth` (all investments) to transaction-based income. Represents "total resources available" (starting capital + earned income).
- **Sankey "Prior Wealth" source node**: Sums all three sources — transaction-tagged prior wealth + bank prior wealth + investment prior wealth.

### Overview Accounting Identity

The dashboard targets: `Total Income ≈ Total Expenses + Total Bank Balance + Total Investments`

Both the overview KPI and the net worth chart calculate investment value the same way: `-sum(all investment transactions)`. This is the total money directed to investments, not reflecting investment profits (that's what the investments page is for). Since `investment_prior_wealth = -sum(all inv txns)`, the prior wealth on the income side and the investment total on the holdings side cancel, keeping the identity balanced.

Known structural residual: **net cash position** from cash transactions. Cash income/expenses are in Total Income/Expenses, but there is no "cash balance" KPI on the right side.

## KPI Method Reference

### `get_overview()`
- **Purpose:** Dashboard stat cards (Total Income, Total Expenses, Total Bank Balance, Total Investments)
- **CC handling:** Excludes CC source in `get_income_investments_and_expenses()`
- **Expenses:** Excludes non-expense categories, but negative Liabilities (debt payments) are included as expenses
- **Prior wealth:** All investment prior wealth (open + closed) added to income
- **Investments:** Transaction-based total: `-sum(all investment transactions)` — money directed to investments, not reflecting profit/loss
- **Bank balance:** Displayed from `bankBalancesApi` (frontend), not computed in overview API
- **Formula:** `net_balance_change = income (+ prior_wealth) - expenses`

### `get_income_expenses_over_time()`
- **Purpose:** Monthly income vs expenses bar chart
- **CC handling:** Excludes CC source in `get_income_investments_and_expenses()`
- **Expenses:** Includes negative Liabilities (debt payments) as expenses
- **Prior wealth:** Not included (monthly view shows transaction-based activity only)

### `get_net_balance_over_time()`
- **Purpose:** Cumulative balance trend line
- **CC handling:** `exclude_services=["credit_card_transactions"]`
- **Prior wealth:** Not included — starts cumulative from 0
- **Formula:** `cumulative_balance[month] = sum(all non-CC txn amounts up to month)`

### `get_expenses_by_category()`
- **Purpose:** Expense pie chart with category breakdown
- **CC handling:** Excludes non-expense categories and `Credit Cards`. Uses itemized CC purchases for category-level detail.
- **Output:** Splits into `expenses` (net negative categories) and `refunds` (net positive categories)

### `get_net_worth_over_time()`
- **Purpose:** Net worth trend with bank balance and investment value lines
- **CC handling:** `exclude_services=["credit_card_transactions"]`
- **Prior wealth:** All prior wealth starts in `bank_balance`; investment movements shift value between the two lines
- **Investments:** `-sum(all investment transactions to date)` — same formula as overview KPI, applied cumulatively per month
- **Formula:** See "Why Investment Prior Wealth Lives in Bank Balance" above

### `get_sankey_data()`
- **Purpose:** Cash flow diagram (sources → Total Income → destinations)
- **CC handling:** Calculates CC gap, filters out `Credit Cards` category, adds gap as "Unknown" destination
- **Prior wealth:** Shown as dedicated "Prior Wealth" source node (all three sources combined)
- **Balance nodes:** "Wealth Growth" (income > expenses) or "Wealth Deficit" (expenses > income)

### `get_income_by_source_over_time()`
- **Purpose:** Stacked bar chart of income broken down by source
- **CC handling:** Excludes CC source
- **Prior wealth:** Excludes transactions tagged "Prior Wealth" (one-time entries, not recurring income)

## Investment KPIs

### Transaction Sign Convention for Investments
- **Deposit (money into investment):** Negative amount (money leaving bank)
- **Withdrawal (money from investment):** Positive amount (money returning to bank)
- **Balance:** `-(sum of all transactions)` — depositing -1000 gives balance +1000

### Key Metrics (`calculate_profit_loss`)
```
total_deposits    = abs(sum of negative amounts)
total_withdrawals = sum of positive amounts
net_invested      = total_deposits - total_withdrawals
current_balance   = -(sum of all amounts)  [0 if closed]
profit_loss       = current_balance - net_invested  [withdrawals - deposits if closed]
roi               = (final_value / total_deposits - 1) * 100
```

Where `final_value = current_balance + total_withdrawals` (open) or `total_withdrawals` (closed).

## Resolved Misalignments

All previously identified code misalignments have been fixed:
- `get_expenses_by_category()` now excludes `Credit Cards` category alongside other non-expense categories
- `get_income_investments_and_expenses()` now filters non-expense categories from expenses, with negative Liabilities overriding back into expenses
- Overview and net worth chart both use transaction-based investment totals (`-sum(all inv txns)`), not portfolio value
- Ignore category has no special treatment in KPI calculations — not in non-expense categories, not filtered
- `"Salay"` typo in `PROTECTED_CATEGORIES` corrected to `"Salary"`
- `NonExpensesCategories` enum removed; non-expense categories now built from individual constants (`INVESTMENTS_CATEGORY`, `LIABILITIES_CATEGORY`) and `IncomeCategories` enum
