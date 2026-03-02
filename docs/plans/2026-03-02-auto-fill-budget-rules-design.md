# Auto-Fill Budget Rules for Current Month

## Problem

When a new month starts and no budget rules have been created for it, the user sees an empty budget view. They must manually click "Replicate Previous Month" to copy rules. If they skip multiple months, only the immediately previous month is checked.

## Solution

Automatically fill budget rules for the current month (and any gap months) from the latest month that has rules. Triggered on the budget analysis API call for today's month.

## Behavior

1. `GET /api/budget/analysis/{year}/{month}` is called for today's year/month
2. Service checks: does the current month have zero rules?
3. If yes → find the latest `(year, month)` with existing rules (looking backwards only)
4. If found → copy those rules to **every empty month** between the source and current month (inclusive)
   - Example: rules in Jan 2026, current is Apr 2026 → fill Feb, Mar, Apr with Jan's rules
5. Return analysis with `copied_from: "January 2026"` so the frontend can show a toast
6. If no month has any rules → return empty budget view as usual (no toast)

## Backend Changes

### `MonthlyBudgetService`

New method: `auto_fill_empty_months(current_year, current_month, budget_rules)`
- Filter `budget_rules` to monthly rules only (non-null year/month)
- Find the max `(year, month)` that is before or equal to the current month
- If none → return None
- Get the source month's rules
- Iterate forward month-by-month from source+1 to current month
- For each month: if no rules exist, copy the source rules via `add_rule()`
- Return the source month string for the toast message

### `get_monthly_analysis()` / route handler

- After fetching rules, check if current month (today) has no rules
- If so, call `auto_fill_empty_months()`
- If rules were copied, re-fetch analysis and include `copied_from` in response
- Only trigger for today's actual year/month, not when browsing other months

### Response schema change

Add optional `copied_from: str | None` field to the analysis response.

## Frontend Changes

### `MonthlyBudgetView.tsx`

- Check response for `copied_from` field
- If present, show toast: "Copied budget rules from {copied_from}"

## Edge Cases

- No rules anywhere → no copy, empty view, no toast
- Rules exist for future month but not current → only look backwards from current month
- Current month already has rules → no-op
- Previous month is in a different year (e.g., Jan → Dec) → year rollback handled correctly
- User manually deletes all rules for current month → auto-fill won't re-trigger until next API call (acceptable)
