# Auto-Fill Budget Rules Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When the current month has no budget rules, automatically copy rules from the latest month that has them — filling all gap months in between.

**Architecture:** New `auto_fill_empty_months` method in `MonthlyBudgetService` finds the latest month with rules and copies them forward. The `get_monthly_analysis` route triggers this for today's month only. Frontend shows a toast when rules are auto-copied.

**Tech Stack:** Python (FastAPI, Pandas), React (TanStack Query), no new dependencies

---

### Task 1: Write failing tests for `auto_fill_empty_months`

**Files:**
- Modify: `tests/backend/unit/services/test_budget_service.py`

**Step 1: Write failing tests**

Add a new test class after `TestMonthlyBudgetServiceCopy` (around line 829). These tests use the existing `db_session` fixture and create rules manually via `service.add_rule()`.

```python
class TestAutoFillEmptyMonths:
    """Tests for auto_fill_empty_months method."""

    def test_fills_current_month_from_previous(self, db_session):
        """Verify rules are copied from the latest month with rules to the current month."""
        service = MonthlyBudgetService(db_session)

        # Create rules for January 2026
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 1, 2026)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 1, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)

        assert result is not None
        assert "January 2026" in result

        # February and March should both have rules now
        feb_rules = service.get_month_rules(2026, 2)
        mar_rules = service.get_month_rules(2026, 3)
        assert len(feb_rules) == 2
        assert len(mar_rules) == 2
        assert set(feb_rules[NAME].tolist()) == {TOTAL_BUDGET, "Food"}
        assert set(mar_rules[NAME].tolist()) == {TOTAL_BUDGET, "Food"}

    def test_no_rules_anywhere_returns_none(self, db_session):
        """Verify None returned when no monthly rules exist at all."""
        service = MonthlyBudgetService(db_session)
        budget_rules = service.get_all_rules()

        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None

    def test_current_month_has_rules_returns_none(self, db_session):
        """Verify no-op when the current month already has rules."""
        service = MonthlyBudgetService(db_session)

        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 3, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None

    def test_skips_months_that_already_have_rules(self, db_session):
        """Verify months with existing rules are not overwritten."""
        service = MonthlyBudgetService(db_session)

        # Jan has 2 rules, Feb has 1 custom rule, Mar is empty
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 1, 2026)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 1, 2026)
        service.add_rule(TOTAL_BUDGET, 9000.0, TOTAL_BUDGET, [ALL_TAGS], 2, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)

        assert result is not None
        # Feb should still have its 1 custom rule, not overwritten
        feb_rules = service.get_month_rules(2026, 2)
        assert len(feb_rules) == 1
        assert feb_rules.iloc[0][AMOUNT] == 9000.0

        # Mar should have 2 rules copied from Jan
        mar_rules = service.get_month_rules(2026, 3)
        assert len(mar_rules) == 2

    def test_year_boundary_fill(self, db_session):
        """Verify filling across year boundary (Dec → Jan)."""
        service = MonthlyBudgetService(db_session)

        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 11, 2025)
        service.add_rule("Food", 1500.0, "Food", [ALL_TAGS], 11, 2025)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 2, budget_rules)

        assert result is not None
        assert "November 2025" in result

        dec_rules = service.get_month_rules(2025, 12)
        jan_rules = service.get_month_rules(2026, 1)
        feb_rules = service.get_month_rules(2026, 2)
        assert len(dec_rules) == 2
        assert len(jan_rules) == 2
        assert len(feb_rules) == 2

    def test_ignores_future_months(self, db_session):
        """Verify rules in future months are not used as source."""
        service = MonthlyBudgetService(db_session)

        # Only rules in a future month (Dec 2026), none before current (Mar 2026)
        service.add_rule(TOTAL_BUDGET, 5000.0, TOTAL_BUDGET, [ALL_TAGS], 12, 2026)

        budget_rules = service.get_all_rules()
        result = service.auto_fill_empty_months(2026, 3, budget_rules)
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `poetry run pytest tests/backend/unit/services/test_budget_service.py::TestAutoFillEmptyMonths -v`
Expected: FAIL — `AttributeError: 'MonthlyBudgetService' object has no attribute 'auto_fill_empty_months'`

**Step 3: Commit**

```bash
git add tests/backend/unit/services/test_budget_service.py
git commit -m "test: add failing tests for auto_fill_empty_months"
```

---

### Task 2: Implement `auto_fill_empty_months` in `MonthlyBudgetService`

**Files:**
- Modify: `backend/services/budget_service.py` — add method after `copy_last_month_rules` (after line 402)

**Step 1: Write implementation**

Add this method to `MonthlyBudgetService`, after `copy_last_month_rules`:

```python
    def auto_fill_empty_months(
        self, current_year: int, current_month: int, budget_rules: pd.DataFrame
    ) -> Optional[str]:
        """
        Auto-fill budget rules for empty months between the latest month with
        rules and the current month.

        Finds the most recent month (before or equal to *current_month*) that
        has budget rules. Then copies those rules into every empty month from
        the source month + 1 through *current_month* inclusive.

        Parameters
        ----------
        current_year : int
            The current calendar year.
        current_month : int
            The current calendar month (1–12).
        budget_rules : pd.DataFrame
            All existing monthly budget rules (from ``get_all_rules``).

        Returns
        -------
        str or None
            A human-readable source month string (e.g. ``"January 2026"``) if
            rules were copied, or ``None`` if the current month already has
            rules or no source month was found.
        """
        # If current month already has rules, nothing to do
        current_rules = self.get_month_rules(current_year, current_month, budget_rules)
        if not current_rules.empty:
            return None

        # Find the latest month with rules, strictly before the current month
        monthly_rules = budget_rules.dropna(subset=[YEAR, MONTH])
        if monthly_rules.empty:
            return None

        # Filter to months before the current month
        before_current = monthly_rules[
            (monthly_rules[YEAR] < current_year)
            | (
                (monthly_rules[YEAR] == current_year)
                & (monthly_rules[MONTH] < current_month)
            )
        ]
        if before_current.empty:
            return None

        # Find the latest (year, month) pair
        before_current = before_current.copy()
        before_current["_sort"] = before_current[YEAR] * 12 + before_current[MONTH]
        max_sort = before_current["_sort"].max()
        source_row = before_current[before_current["_sort"] == max_sort].iloc[0]
        source_year = int(source_row[YEAR])
        source_month = int(source_row[MONTH])

        # Get the source rules
        source_rules = self.get_month_rules(source_year, source_month, budget_rules)

        # Iterate from source+1 to current month, filling empty months
        y, m = source_year, source_month
        while True:
            # Advance one month
            if m == 12:
                m = 1
                y += 1
            else:
                m += 1

            # Check if this month already has rules
            month_rules = self.get_month_rules(y, m, budget_rules)
            if month_rules.empty:
                for _, rule in source_rules.iterrows():
                    self.add_rule(
                        name=rule[NAME],
                        amount=rule[AMOUNT],
                        category=rule[CATEGORY],
                        tags=rule[TAGS],
                        month=m,
                        year=y,
                    )

            if y == current_year and m == current_month:
                break

        import calendar
        source_month_name = calendar.month_name[source_month]
        return f"{source_month_name} {source_year}"
```

**Step 2: Run tests to verify they pass**

Run: `poetry run pytest tests/backend/unit/services/test_budget_service.py::TestAutoFillEmptyMonths -v`
Expected: All 6 tests PASS

**Step 3: Run full test suite to check for regressions**

Run: `poetry run pytest tests/backend/unit/services/test_budget_service.py -v`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add backend/services/budget_service.py
git commit -m "feat: add auto_fill_empty_months to MonthlyBudgetService"
```

---

### Task 3: Wire auto-fill into the analysis route

**Files:**
- Modify: `backend/routes/budget.py` — update `get_monthly_analysis` endpoint (line 140)
- Modify: `backend/services/budget_service.py` — update `get_monthly_analysis` method (line 474)

**Step 1: Update the service method**

In `MonthlyBudgetService.get_monthly_analysis` (line 474), add the auto-fill logic. The method needs to know if it's being called for today's month:

```python
    def get_monthly_analysis(
        self, year: int, month: int, include_split_parents: bool = False
    ) -> dict:
        """
        Get full monthly budget analysis combining budget view, project spending, and pending refunds.

        Parameters
        ----------
        year : int
            Calendar year.
        month : int
            Calendar month (1–12).
        include_split_parents : bool, optional
            When ``True``, include parent transactions alongside split children.
            Default is ``False``.

        Returns
        -------
        dict
            Dictionary with keys:

            - ``rules`` – list of budget rule view dicts (from ``get_monthly_budget_view``),
              or empty list if no rules are defined.
            - ``project_spending`` – dict with a ``projects`` list summarising
              project spend for the month (from ``get_monthly_project_spending_summary``).
            - ``pending_refunds`` – dict with ``items`` (pending refund list) and
              ``total_expected`` (sum of expected amounts).
            - ``copied_from`` – source month name if rules were auto-filled,
              or ``None``.
        """
        from datetime import date

        copied_from = None
        today = date.today()

        # Auto-fill empty months only when viewing the current calendar month
        if year == today.year and month == today.month:
            budget_rules = self.get_all_rules()
            current_rules = self.get_month_rules(year, month, budget_rules)
            if current_rules.empty:
                copied_from = self.auto_fill_empty_months(year, month, budget_rules)

        view = self.get_monthly_budget_view(year, month, include_split_parents)
        project_summary = self.get_monthly_project_spending_summary(
            year, month, include_split_parents
        )

        pending_refunds = self.pending_refunds_service.get_all_pending(status="pending")
        budget_adjustment = self.pending_refunds_service.get_budget_adjustment(
            year, month
        )

        return {
            "rules": view if view else [],
            "project_spending": project_summary,
            "pending_refunds": {
                "items": pending_refunds,
                "total_expected": budget_adjustment,
            },
            "copied_from": copied_from,
        }
```

**Step 2: Run tests**

Run: `poetry run pytest tests/backend/unit/services/test_budget_service.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add backend/services/budget_service.py backend/routes/budget.py
git commit -m "feat: trigger auto-fill in monthly analysis for current month"
```

---

### Task 4: Show toast notification in frontend

**Files:**
- Modify: `frontend/src/components/budget/MonthlyBudgetView.tsx`

The project uses `alert()` for notifications. We'll use a simple inline toast banner (auto-dismiss) to avoid adding a dependency, matching the project's existing pattern of lightweight UI.

**Step 1: Add toast state and effect**

Add a `copiedFrom` state and a `useEffect` that watches the analysis response:

```typescript
// After line 26 (after includeSplitParents state)
const [copiedFromMsg, setCopiedFromMsg] = useState<string | null>(null);
```

Add a `useEffect` after the query definition (after line 34):

```typescript
import { useEffect } from "react";

React.useEffect(() => {
  if (analysis?.copied_from) {
    setCopiedFromMsg(analysis.copied_from);
    const timer = setTimeout(() => setCopiedFromMsg(null), 5000);
    return () => clearTimeout(timer);
  }
}, [analysis?.copied_from]);
```

**Step 2: Render toast banner**

Add the toast right after the Month Navigation `<div>` (after line 249), before the Summary Header Strip:

```tsx
{/* Auto-copy toast */}
{copiedFromMsg && (
  <div className="flex items-center justify-between bg-blue-500/10 border border-blue-500/20 text-blue-400 px-4 py-3 rounded-xl text-sm font-medium animate-in fade-in slide-in-from-top-2 duration-300">
    <span>Budget rules copied from {copiedFromMsg}</span>
    <button
      onClick={() => setCopiedFromMsg(null)}
      className="ml-4 text-blue-400/60 hover:text-blue-400 transition-colors"
    >
      ✕
    </button>
  </div>
)}
```

**Step 3: Update the import line**

Ensure `useEffect` is imported. Change line 1 from:
```typescript
import React, { useState } from "react";
```
to:
```typescript
import React, { useState, useEffect } from "react";
```

And change `React.useEffect` to just `useEffect`.

**Step 4: Verify in browser**

Run: `python .claude/scripts/with_server.py -- echo "servers started"`
Enable Demo Mode, navigate to Budget page, verify toast appears if current month had no rules.

**Step 5: Commit**

```bash
git add frontend/src/components/budget/MonthlyBudgetView.tsx
git commit -m "feat(ui): show toast when budget rules are auto-copied"
```

---

### Task 5: Move the `import calendar` to module level

**Files:**
- Modify: `backend/services/budget_service.py`

**Step 1: Move the inline `import calendar` to the top of the file**

Move `import calendar` from inside `auto_fill_empty_months` to the top-level imports (after `from typing import Optional`). Also move `from datetime import date` from inside `get_monthly_analysis` to the top-level imports.

**Step 2: Run all tests**

Run: `poetry run pytest tests/backend/unit/services/test_budget_service.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/services/budget_service.py
git commit -m "refactor: move imports to module level in budget_service"
```
