---
paths:
  - "frontend/src/**/*.{ts,tsx}"
---

# Frontend Pitfalls — Common Mistakes to Avoid

Hard-won lessons from the codebase. Read before adding new code.

## React Hooks Rules

### Hooks Before Early Returns
React hooks (`useState`, `useId`, `useTranslation`, `useScrollLock`, etc.) MUST be called before any early `return`. This is a React rule — violating it causes runtime crashes.

```tsx
// WRONG — useId() after early return
function Modal({ isOpen }: Props) {
  if (!isOpen) return null;    // ← early return
  const id = useId();          // ← CRASH: hook called conditionally
}

// CORRECT — all hooks before early return
function Modal({ isOpen }: Props) {
  const id = useId();          // ← hook called unconditionally
  useScrollLock(isOpen);       // ← hook called unconditionally
  if (!isOpen) return null;    // ← early return is safe here
}
```

## i18n (Internationalization)

### Variable Shadowing with `t()`
Never name `.map()` / `.forEach()` callback parameters `t` — it shadows `useTranslation()`'s `t` function.

```tsx
// WRONG — `t` in callback shadows the translation function
const { t } = useTranslation();
tags.map((t: string) => <span>{t}</span>)  // ← `t` is now the tag string, not the translation fn

// CORRECT — use a descriptive name
tags.map((tagName: string) => <span>{tagName}</span>)
```

### Always Add Keys to Both Locale Files
When adding `t("section.newKey")`, add the key to BOTH:
- `frontend/src/locales/en.json`
- `frontend/src/locales/he.json`

Missing keys silently render the key path as text (e.g., "common.select" instead of "Select").

### Interpolation in Locale Strings
If a translated string needs a dynamic value, use `{{variable}}` interpolation:
```json
// WRONG
"daysRemaining": "days remaining"

// CORRECT
"daysRemaining": "{{count}} days remaining"
```
```tsx
t("budget.daysRemaining", { count: 15 })
```

### No Hardcoded Strings
Every user-visible string must use `t()`. This includes:
- Placeholder text in inputs and selects
- Tooltip text
- `window.confirm()` and `window.alert()` messages
- Aria labels

## Transaction Type Duality

The `Transaction` type has TWO description fields due to different backend sources:
- `desc` — from some API endpoints
- `description` — from other API endpoints

**Always handle both:**
```tsx
const description = tx.description ?? tx.desc ?? "";
```

Import the canonical `Transaction` type from `types/transaction.ts`, not from component files.

## Currency Formatting

**Always use** `formatCurrency()` from `utils/numberFormatting.ts`:
```tsx
import { formatCurrency } from "../../utils/numberFormatting";
formatCurrency(amount)          // "₪1,234"
formatCurrency(amount, 2)       // "₪1,234.56"
```

**Never inline** `new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" })`. It creates duplicate logic and inconsistent formatting.

**Don't append `₪` yourself.** `formatCurrency()` already includes the symbol.
Manual concatenation (`{formatCurrency(x)}₪`) doubles the symbol on RTL builds
and causes the inconsistent spacing (`1,234₪` here, `1,234 ₪` there) you'll
see on legacy code. If you need the value without the symbol, route the
number through `formatCurrency()` and add `, { signDisplay: "never", currency: undefined }`
options — or extract a separate helper.

## Delta / Change Formatting

For any "change" or "delta" value (KPI card trend, period-over-period change,
chart mini-cards), pick **one** helper and use it everywhere. Don't roll
your own template:

```tsx
// CORRECT — single source of truth
formatChange(-20000)    // "-₪20K"
formatChange(6500)      // "+₪6.5K"
formatChange(-132)      // "-₪132"   (small values still get currency)
```

Bad patterns that have shipped to prod and looked broken:
- `${sign}₪${formatCompactCurrency(v)}` and `₪${formatCompactCurrency(v)}` on the
  same page → `+₪6.5K` next to `₪-20K`.
- Falling out of the abbreviator for small absolute values → one card shows
  `+₪1.1M`, the next card shows `-482` (no currency, no abbreviation).
- `Math.abs(pct).toFixed(1) + "%-"` instead of `${sign}${pct.toFixed(1)}%`
  → `1.7%-` with the minus stuck on the end.

If you spot any of these, route them through the central helper.

## SQLite Booleans in JSX

SQLite stores booleans as `0` / `1` integers. In JSX, `{0 && <Component />}` renders the string `"0"`.

```tsx
// WRONG — renders "0" when value is falsy
{transaction.is_pending && <PendingBadge />}

// CORRECT
{!!transaction.is_pending && <PendingBadge />}
// or
{transaction.is_pending > 0 && <PendingBadge />}
```

## React Query Keys

### Consistent Query Key Usage
Use the same `queryKey` array for the same data everywhere. The shared hooks enforce this:
- `["categories"]` → `useCategories()`
- `["cashBalances"]` → `useCashBalances()`
- `["taggingRules"]` → `useTaggingRules()`

### Always Invalidate on Mutation Success
Every `useMutation` that changes server data MUST have an `onSuccess` that invalidates related queries:
```tsx
const mutation = useMutation({
  mutationFn: (data) => api.update(data),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["relatedData"] }),
});
```
Missing `onSuccess` invalidation = UI doesn't refresh after the mutation.

### But don't fan out — narrow keys + setQueryData patches
The flip side: `queryClient.invalidateQueries()` with no args
refetches every active query and saturates the mobile HTTP/1.1
connection pool. Prefer narrow keys
(`{ queryKey: ["specific"] }`) and synchronous `setQueriesData`
patches for local effects. The shared `MutationCache.onSuccess`
already runs a debounced global sweep — you don't need to add
another one. See `frontend_components.md` →
"Don't fan out invalidation in mutation hot paths".

### Multi-field inline editors stage and commit on Done
Editors with two or more correlated fields (category + tag,
amount + currency, etc.) must NOT fire a mutation per dropdown
change. Stage selections in local `useState` and commit once on
Done. See `frontend_components.md` →
"Multi-field inline editors: stage locally, commit on Done" for
the canonical pattern and the list of bugs the
per-selection-mutation design produced.

## Key Generation in Lists

### Stable, Unique Keys
Don't use array indices as React keys for dynamic lists. Use a stable identifier:
```tsx
// WRONG — index changes when list is filtered/sorted
transactions.map((tx, i) => <Row key={i} />)

// CORRECT — use a stable unique identifier
transactions.map((tx) => (
  <Row key={`${tx.source}_${tx.unique_id ?? tx.id ?? `${tx.date}-${tx.amount}`}`} />
))
```

## Modal Stacking

When a modal opens another modal (e.g., transaction edit → split transaction), the inner modal needs a higher z-index:
```tsx
<Modal zIndex="z-[60]" ...>  {/* Inner modal on top */}
```
Default is `z-50`. Use `z-[60]` for second-level modals.

## TransactionsTable Consumer Updates

When modifying `TransactionsTable.tsx` props or behavior, **always update all consumers**:
1. `frontend/src/pages/Transactions.tsx`
2. `frontend/src/components/budget/TransactionCollapsibleList.tsx`

These components pass different prop configurations and may break silently.

## Provider/Service Name Maps

When adding a new financial provider:
1. Add to backend `PROVIDER_CONFIGS` in `scraper/models/credentials.py`
2. Add display names to BOTH `PROVIDER_LABELS` and `PROVIDER_LABELS_HE` in `frontend/src/utils/textFormatting.ts`
3. Add to both `en.json` and `he.json` under `services.*` if needed
