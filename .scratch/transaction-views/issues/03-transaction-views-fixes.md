# 03 — Transaction views: deliberate fixes

Status: ready-for-agent
Blocked by: 02

One PR; one commit and one before/after test per fix. The PR body lists
every figure that moves and why.

1. **Drop `Ignore` from the bank view.** Moves the forecast cash-out
   baseline, the FIRE plan's typical month and the overview KPI for any
   household with one-sided transfers.
2. **Net refunds in `get_income_by_source`**, matching its `_over_time`
   sibling.
3. **Net refunds on savings' goal-claimed rows** — only if a figure actually
   changes; otherwise close as no-op.
4. **One expense-category constant** — delete `NON_EXPENSE_CATEGORIES` /
   `EXPENSE_EXCLUDED_CATEGORIES` duplicates in favour of the module's.
5. **Prior wealth** — only if issue 02's snapshot showed a caller counting it
   as income.
