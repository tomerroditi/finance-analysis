# 02 — Transaction views: pure refactor

Status: ready-for-agent
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
4. **Migrate callers.**
   - `analysis/cashflow.py`: `get_income_expenses_over_time`,
     `get_income_investments_and_expenses`, `get_income_by_source(_over_time)`,
     `get_expenses_by_category_over_time`, `get_monthly_expenses`;
     `_net_matched_refunds` deleted.
   - `analysis/net_worth.py` Sankey (still adds prior wealth itself).
   - `recurring_service.py` expense and income filters.
   - `insights_service.py`.
   - `savings_goals/inputs.py` (drops its own claimed rows; claimed rows
     still read raw).
   - `analysis/forecast.py` classification.
   - `fire_plan_service.py` typical month.
   - `budget/core.py`: only switches to the module's category constant.
5. Repository: `_CASHFLOW_EXCLUDED`, `get_cashflow_transactions`,
   `get_itemized_transactions` read only by the views module.
6. Update `.claude/rules/kpi_calculations.md` to point at the module.

## Done when

- Golden snapshot identical before and after.
- Full pre-PR checklist green (ruff, pytest with coverage, frontend lint /
  build / vitest / e2e).
