# 03 — Transaction views: deliberate fixes

Status: ready-for-agent
Blocked by: 02

One PR; one commit and one before/after test per fix. The PR body lists
every figure that moves and why.

1. **Drop `Ignore` from the bank view.** Moves the forecast cash-out
   baseline, the FIRE plan's typical month and the overview KPI for any
   household with one-sided transfers.
2. **Move the callers that don't net refunds yet onto a view** — each one
   starts netting matched refunds:
   - `get_income_by_source` (bank view income), matching its `_over_time`
     sibling;
   - `get_overview` totals and the forecast's month-to-date income / cash
     out via `get_income_investments_and_expenses` (bank view);
   - forecast `_cashflow_spend_shares` (bank view expenses);
   - `get_debt_payments_over_time` (bank view expenses, `Liabilities`);
   - recurring detection: expense candidates (spending view, projects and
     liabilities excluded) and income streams (spending view income) — check
     detection output on the demo DB before and after;
   - then delete `transactions_masks` / `income_mask` from the module's
     public surface if nothing else reads them.
3. **Net refunds on savings' goal-claimed rows** — only if a figure actually
   changes; otherwise close as no-op.
4. ~~One expense-category constant~~ — done in 02 (the lists were
   identical, so no figure moved).
5. **Prior wealth** — issue 02's snapshot showed
   `get_income_expenses_over_time` counting a 15,000 `Prior Wealth`-tagged
   `Other Income` row as income in its month. Delete the marked shim there.
