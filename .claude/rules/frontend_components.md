---
paths:
  - "frontend/src/components/**/*.{ts,tsx}"
---

# Frontend Components - UI Implementation

## Purpose
Components contain **ALL UI implementation logic** for the React application. They render HTML/JSX, handle user interactions, manage local state, and display data fetched via hooks.

**Golden Rule:** Components focus on "how it looks and feels" — Hooks/Services handle "data fetching and business logic".

## Directory Structure

```
frontend/src/components/
├── common/              # Reusable generic UI primitives (Modal, MultiSelect, SelectDropdown, Skeleton, etc.)
├── dashboard/           # Dashboard-specific sections (BudgetSection, RecentTransactionsSection, DashboardInsightsPanel)
├── transactions/        # Transaction page sub-components (FilterPanel, Pagination, BulkActionsBar, RuleBuilder, etc.)
├── budget/              # Budget page sub-components (MonthlyBudgetView, ProjectBudgetView, TransactionCollapsibleList)
├── investments/         # Investment page sub-components
├── retirement/          # Early retirement calculator components
├── layout/              # App layout shell (Layout, Sidebar, TopBar)
├── modals/              # Shared modals used across multiple features (ConfirmationModal, LinkRefundModal, SplitTransactionModal, etc.)
├── BudgetProgressBar.tsx      # Shared across budget views
├── DateRangePicker.tsx        # Shared date range selector
├── ErrorBoundary.tsx          # Error boundary wrapper
├── SankeyChart.tsx            # Sankey flow diagram
└── TransactionsTable.tsx      # Core transaction table (used by Transactions page + budget views)
```

### Where to Place New Components
- **Used by one page only?** → In that page's feature directory (e.g., `components/dashboard/`)
- **Used across multiple features?** → In `components/common/` (generic UI) or `components/modals/` (shared modals)
- **Top-level `components/` root** — only for widely shared feature components like `TransactionsTable.tsx` and `DateRangePicker.tsx`

## Core Principles

### What Components DO:
- Render UI (JSX) with Tailwind CSS 4 utility classes
- Handle user interactions (onClick, onChange, onSubmit)
- Manage local state (useState, useReducer)
- Display data from props or React Query hooks
- Simple form validation before submission

### What Components DO NOT DO:
- Direct API calls — use custom hooks or `services/api.ts`
- Business logic — complex calculations belong in backend or hooks
- Global state management — use Zustand stores, not prop drilling

## Key Patterns

### Modal Component
Always use the shared `Modal` component from `components/common/Modal.tsx`:
```tsx
import { Modal } from "../common/Modal";

<Modal isOpen={isOpen} onClose={onClose} title={t("modals.editTitle")} maxWidth="2xl">
  {/* Modal body content here — Modal handles overlay, header, scroll lock, accessibility */}
</Modal>
```
- `maxWidth` options: `"sm"` | `"md"` | `"lg"` | `"xl"` | `"2xl"` | `"3xl"` | `"4xl"`
- Use `zIndex="z-[60]"` for modals that open on top of other modals
- Modal handles: backdrop, close button, `aria-modal`, `aria-labelledby`, `useScrollLock`, unique `useId()`

### Data Fetching with Custom Hooks
Use shared hooks instead of inline `useQuery` calls for commonly fetched data:
```tsx
import { useCategories } from "../../hooks/useCategories";
import { useCashBalances } from "../../hooks/useCashBalances";
import { useTaggingRules } from "../../hooks/useTaggingRules";

const { data: categories } = useCategories();
const { data: cashBalances } = useCashBalances();
const { data: rules } = useTaggingRules();
```
**When to create a new shared hook:** If the same `useQuery` pattern appears in 3+ components.

### Mutations
Use `useMutation` with `onSuccess` that invalidates related queries:
```tsx
const mutation = useMutation({
  mutationFn: (data) => api.update(data),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["relatedData"] }),
});
```
**Always add `onSuccess` invalidation** — missing it means the UI won't refresh after mutations.

#### Don't fan out invalidation in mutation hot paths

`queryClient.invalidateQueries()` with no args marks every cached
query stale and refetches every active observer. The dashboard alone
has ~12 active queries; firing that on every keystroke or every
dropdown change saturates the mobile HTTP/1.1 connection pool, makes
the next user interaction feel frozen, and can leave subsequent
mutations queued behind in-flight refetches (we hit this exact bug
in the dashboard inline tag editor — a tap on the tag dropdown after
a category change couldn't reach the backend until the previous
invalidation cascade drained).

When a mutation's effect on the UI is local and predictable, prefer:

1. A narrow `setQueryData` / `setQueriesData` patch keyed by the
   same identifier the row uses for its React key. The visible row
   updates synchronously, no refetch needed.
2. `invalidateQueries({ queryKey: [<specific key>] })` for the
   handful of derived queries that genuinely changed (analytics,
   aggregates, etc.).
3. Reserve `invalidateQueries()` (no args) for explicit "I just
   imported a backup, refresh everything" flows.

The shared `MutationCache.onSuccess` in `queryClient.ts` already
runs a debounced full invalidation on every mutation. **You do not
need to add another one.** Anything you add on top is pure overhead
on the hot path.

### Multi-field inline editors: stage locally, commit on Done

Inline editors with two or more correlated fields (e.g. category +
tag, where the tag's options depend on the chosen category) **must
not** fire a mutation per dropdown change. Treat each editing
session as one atomic edit:

- Hold the in-flight selections in local `useState`
  (`stagedCategory`, `stagedTag`, …) initialised from the row's
  current values when the editor opens.
- Bind each `SelectDropdown`'s `value` and `onChange` to the staged
  state, not to the underlying row data. Dependent dropdowns
  (e.g. tag options) derive from the staged value, not the row.
- The row underneath stays visually unchanged during the session —
  no icon flips, no label rewrites, no progress bars jumping.
- A primary "Done" / "Save" button fires a single mutation with
  the staged values and closes the editor. If nothing changed,
  skip the mutation entirely.
- Re-opening the editor on a different row, or tapping the toggle
  again, discards the staged values.

`RecentTransactionsSection.tsx` is the canonical reference. The
prior per-selection-mutation design was responsible for: the icon
flipping mid-edit, the editor feeling laggy on mobile, the Done
button occasionally eating taps, and the second mutation in a
chained edit failing to reach the backend on HTTP/1.1.

Per-field auto-commit is acceptable **only** for genuinely
single-field controls — a toggle, a debounced search input, a
standalone slider — where there's no dependent state and no
"halfway through" intermediate state for the user to be in.

### Currency Formatting
Always use the shared utility:
```tsx
import { formatCurrency, formatCompactCurrency } from "../../utils/numberFormatting";
```
Never inline `new Intl.NumberFormat("he-IL", ...)` in components.

### TypeScript
- Always define `interface Props` for component props
- Import `Transaction` type from `../../types/transaction` (canonical location)
- Use strict mode — no unused locals or parameters

## Styling

### Design System (CSS Custom Properties)
All colors use CSS custom properties defined in `index.css` (dark theme):
```
--background, --surface, --surface-light    (backgrounds)
--text-primary, --text-muted                (text)
--accent, --accent-hover                    (interactive elements)
--success, --danger, --warning              (semantic colors)
```
Use as: `bg-[var(--surface)]`, `text-[var(--text-muted)]`, `border-[var(--surface-light)]`

### Tailwind CSS 4
- Mobile-first responsive: base styles for mobile, `sm:`, `md:`, `lg:` for larger
- Use logical properties for RTL (see `frontend_i18n.md`)
- Use `clsx` for conditional class joining

## System-Specific Rules

### TransactionsTable Updates
When modifying `TransactionsTable.tsx` (especially props), **YOU MUST** update all consumers:
- `frontend/src/pages/Transactions.tsx`
- `frontend/src/components/budget/TransactionCollapsibleList.tsx`
- Ensure data fetching (e.g., pending refunds) is consistent across `MonthlyBudgetView` and `ProjectBudgetView`

### SQLite Boolean Fields in JSX
SQLite stores booleans as `0`/`1` integers. In JSX, `{0 && <Component />}` renders the string "0".
**Always use:** `{!!value && <Component />}` or `{value > 0 && <Component />}`
