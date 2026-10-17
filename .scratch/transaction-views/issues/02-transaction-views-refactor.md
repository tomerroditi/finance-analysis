# 02 — Transaction views: pure refactor

Status: claimed
Blocked by: 01

No figure on any card or endpoint moves. See `../spec.md` for the decisions.

## Work

1. **Golden snapshots first (temporary).** Against the bundled demo DB,
   record the output of every method below, rounded to 2 decimals. Assert
   equality after the refactor; delete the snapshot test once the PR passes.
2. **`backend/services/transaction_views.py`.** `TransactionViews(db)` with
   `bank(...)` and `spending(...)`. It absorbs `transaction_classification.py`
   (the masks become internals) and owns the single expense-category
   constant. Each view is memoised through `data_cache`.
3. **Table-driven view tests (permanent).** One per rule, through the view's
   interface on a seeded DB: card dedup per view, insurance left out,
   prior-wealth left out, refund netting (matched always, pending by
   option), projects, liabilities, `monthly()` keeps empty months.
4. **Migrate callers that already net refunds.**
   - `analysis/cashflow.py`: `get_income_expenses_over_time` (bank),
     `get_expenses_by_category_over_time` (spending),
     `get_income_by_source_over_time` (bank); `_net_matched_refunds` deleted.
     `get_income_expenses_over_time` keeps a marked shim adding prior-wealth
     rows back as income — the demo has a 15,000 one — removed in 03.
   - `analysis/net_worth.py` Sankey (spending view; still adds prior wealth
     itself and measures card coverage on raw rows).
   - `insights_service.py` large-charge rule; its `_net_matched_refunds`
     deleted. (Its category spend already comes via cashflow.)
   - `savings_goals/inputs.py` surplus (spending view, pending kept; drops its
     own claimed rows; claimed rows still read raw).
   - Forecast and FIRE plan follow automatically through
     `get_income_expenses_over_time`.
   - `budget/core.py`: only switches to the module's category constant; the
     duplicate `constants.categories.NON_EXPENSE_CATEGORIES` is deleted.
5. Repository: `_CASHFLOW_EXCLUDED`, `get_cashflow_transactions`,
   `get_itemized_transactions` end up read only by the views module once 03
   moves the remaining callers (the Sankey keeps one raw read for card
   coverage).
6. Update `.claude/rules/kpi_calculations.md` to point at the module.

## Done when

- Golden snapshot identical before and after.
- Full pre-PR checklist green (ruff, pytest with coverage, frontend lint /
  build / vitest / e2e).
