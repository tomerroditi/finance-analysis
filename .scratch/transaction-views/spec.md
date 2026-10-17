# Transaction views

Status: ready-for-agent

Origin: backend architecture review (2026-10-17), candidate #1 — "one
transaction view instead of fifteen filter recipes". Terms are defined in
`CONTEXT.md` (**bank view**, **spending view**).

## Problem

"Expense", "the Income & Expenses basis" and "netted for refunds" are each
re-derived by hand in 4–5 services, and the copies disagree:

- `transactions_masks` makes expenses the complement of income and
  investments, so `Ignore` transfers count as spending on the bank basis
  (forecast cash-out, the FIRE plan's typical month, the overview KPI) while
  budget, Sankey, recurring and savings drop them.
- Refund netting is hand-wired at 5 sites with different `exclude_open`
  defaults; `get_income_by_source` skips it while its `_over_time` sibling
  nets.
- The expense-category list exists twice (`NON_EXPENSE_CATEGORIES`,
  `EXPENSE_EXCLUDED_CATEGORIES`) plus a hand-built copy in recurring and a
  5-item list in the Sankey.
- Savings-yearly copied the Income & Expenses card's rules instead of
  reusing them (#391) and has already drifted.
- `cashflow.py` reads the repository's private `_CASHFLOW_EXCLUDED`.

## Decisions

| # | Decision |
|---|----------|
| Q1 | Two named views, **bank** and **spending**, each classified into income / expenses / investments. The Sankey moves onto the spending view (it reads card purchases item by item — corrected during step 1). |
| Q2 | `Ignore` is left out of both views (lands in step 2 — it changes figures). |
| Q3 | Matched refunds are always netted inside a view; only `exclude_pending_refunds` varies. |
| Q4 | Two steps: a pure refactor that moves no figure, then the fixes, each with its own before/after test. |
| Q5 | Module `backend/services/transaction_views.py`, absorbing `transaction_classification.py`; glossary terms in `CONTEXT.md`. |
| Q6 | A view exposes `.income`, `.expenses`, `.investments` row frames plus `.monthly()` (every month present, signed as the cards show it). |
| Q7 | View options: `exclude_pending_refunds`, `exclude_projects`, `exclude_liabilities`. Date windows stay with callers. No generic row-exclusion option. |
| Q8 | Savings asks for the spending view and drops its own goal-claimed rows; in step 1 it keeps reading claimed rows raw. |
| Q9 | Step 1 migrates every caller that already nets refunds; callers that don't (overview, forecast month-to-date, `income-by-source`, recurring, debt payments) move in step 2, since netting them moves figures. Budget's `get_filtered_expenses` only switches to the module's category constant; its filtering moves with the budget claim-ledger work. |
| Q10 | Step 1 is proven by temporary golden snapshots against the bundled demo DB plus permanent table-driven view tests, one per rule. |
| Q11 | Prior-wealth rows are left out of both views; the Sankey reads prior wealth itself. |
| Q12 | Each view is memoised by `(view, options)` through `data_cache`. |
| Q13 | Interface: `TransactionViews(db).bank(...)` / `.spending(...)`. The repository's `_CASHFLOW_EXCLUDED`, `get_cashflow_transactions` and `get_itemized_transactions` are read only by this module; local netting helpers are deleted. |
| Q14 | Step 2 is one PR, one commit + one before/after test per fix, every moved figure listed in the PR body. |

## Interface

```python
views = TransactionViews(db)
view = views.bank(exclude_pending_refunds=True, exclude_projects=False, exclude_liabilities=False)
view = views.spending(...)                         # same options
view.income / view.expenses / view.investments     # row frames, refund-netted, classified
view.monthly()                                      # month -> {income, expenses, investments}
```

## Plan

1. [`issues/01-stale-caches-after-restore.md`](issues/01-stale-caches-after-restore.md) — step 0, a confirmed bug found by the same review.
2. [`issues/02-transaction-views-refactor.md`](issues/02-transaction-views-refactor.md) — step 1, no figure moves.
3. [`issues/03-transaction-views-fixes.md`](issues/03-transaction-views-fixes.md) — step 2, the deliberate fixes.

## Out of scope

The other review candidates (budget claim ledger, closed-investment
valuation, transaction write module, ingestion module, budget rule store,
savings-goal facts, FIRE projection contract, transaction reference,
baselines, insight signals, request context) and their suspected bugs.
