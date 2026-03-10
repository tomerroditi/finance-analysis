# Inline Create in SelectDropdown

## Problem

Users must navigate to the Categories page to create new categories or tags before they can use them in transaction editing, rule creation, budgets, etc. This breaks workflow.

## Solution

Add an optional `onCreateNew` prop to `SelectDropdown`. When provided, a "+ Create new" button appears at the bottom of the options list. Clicking it switches to an inline text input where the user types a name and presses Enter to create.

## Component Changes — SelectDropdown.tsx

New optional prop:

```typescript
onCreateNew?: (value: string) => Promise<void> | void;
```

### Behaviors when `onCreateNew` is provided

1. **"+ Create new" button** — sticky at bottom of options list, always visible regardless of search/filter state. Styled with `Plus` icon in accent color.

2. **Inline creation mode** — clicking "+ Create new" replaces the button with a text input:
   - Pre-filled with current search text (if any)
   - Enter → calls `onCreateNew(name)`, exits creation mode, selects new value via `onChange`
   - Escape or X → exits creation mode, returns to normal dropdown
   - Input text is formatted to title case before submission

### Keyboard navigation

Arrow keys cycle through `filteredOptions` only (skip the create row). The create row is reachable by mouse or Tab from search input.

## Consumer Sites (6 locations)

Each category/tag `SelectDropdown` passes `onCreateNew`:

| Site | Category `onCreateNew` | Tag `onCreateNew` |
|------|----------------------|-------------------|
| TransactionEditorModal | `taggingApi.createCategory(name)` | `taggingApi.createTag(category, name)` |
| TransactionFormModal | same | same |
| SplitTransactionModal | same | same |
| RuleEditorModal | same | same |
| BudgetRuleModal | same | N/A (chip UI) |
| TransactionsTable bulk tag bar | same | same |

All callbacks invalidate the `["categories"]` TanStack Query cache on success and auto-select the new value.

## Title case formatting

Applied on the frontend before API call so the selected value displays correctly immediately. Backend already normalizes via `to_title_case()`.

## What we don't change

- No backend changes (endpoints already exist)
- No changes to `MultiSelect` (FilterPanel filters are data-driven)
- No changes to BudgetRuleModal tag chips (different UX pattern)
