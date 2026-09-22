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
formatCurrency(amount, 2)       // "1,234.56 ₪"
```

**Canonical layout is sign-magnitude-currency** (Israeli convention:
₪ after digits, NBSP between). Helpers emit `1,003,211 ₪`, `-25K ₪`,
`+150 ₪`. Don't roll your own `₪${x}` template — you'll get the
shekel on the wrong side and re-introduce the inconsistency we
already fixed twice.

**Never inline** `new Intl.NumberFormat("he-IL", { style: "currency", currency: "ILS" })`.
The `he-IL` locale puts ₪ after digits without bidi isolation, the default
locale puts it before, and either way you skip the LRI/PDI envelope the
shared helpers add. Result: the same dashboard renders some values as
`1,234 ₪` and others as `₪ 1,234` depending on the surrounding RTL
context.

**Don't append `₪` yourself.** `formatCurrency()` already includes the
symbol. Manual concatenation (`{formatCurrency(x)}₪`) doubles the symbol.

**Helper output is bidi-stable.** Each call returns a string wrapped in
U+2066 (LRI) ... U+2069 (PDI), so `<span>{formatCurrency(x)}</span>`
without `dir="ltr"` renders correctly under RTL. You only need
`dir="ltr"` when you concatenate something around the helper output
yourself (a literal `+`, joining two helper outputs with `" / "` text,
date + currency on the same line, etc.).

## Delta / Change Formatting

For any "change" or "delta" value (KPI card trend, period-over-period change,
chart mini-cards), pick **one** helper and use it everywhere. Don't roll
your own template:

```tsx
// CORRECT — single source of truth
formatChange(-20000)    // "-20K ₪"
formatChange(6500)      // "+6.5K ₪"
formatChange(-132)      // "-132 ₪"   (small values still get currency)
```

Bad patterns that have shipped to prod and looked broken:
- `${sign}₪${formatCompactCurrency(v)}` and `₪${formatCompactCurrency(v)}` on the
  same page → `+₪6.5K` next to `₪-20K`.
- Falling out of the abbreviator for small absolute values → one card shows
  `+₪1.1M`, the next card shows `-482` (no currency, no abbreviation).
- `Math.abs(pct).toFixed(1) + "%-"` instead of `${sign}${pct.toFixed(1)}%`
  → `1.7%-` with the minus stuck on the end.

If you spot any of these, route them through the central helper.

## RTL Bidi: Truncated User Data and Signed Numbers

Two related bugs that we keep regressing on. Both come from the same
root cause: the document direction in Hebrew is `rtl`, and CSS / bidi
algorithms apply that direction to content that should actually be LTR.

### `truncate` on user data clips the wrong end

Tailwind `truncate` is `text-overflow: ellipsis`. CSS truncates at the
**end of the line in the document direction**. Under RTL, that's the
visual left side. English content like `"Transportation / Gas"` then
shows as `"...sportation / Gas"` — leading letters chopped off.

```tsx
// WRONG
<span className="truncate">{tx.description}</span>

// CORRECT — bidi auto-detects from first strong character
<span className="truncate" dir="auto">{tx.description}</span>
```

Apply `dir="auto"` to every `truncate` / `line-clamp` element that
holds **user data**: transaction descriptions, category / tag names,
account names, rule names, project names, free-text notes. Do not
apply it to chrome strings that came from `t(...)` — those should
always match document direction.

### Signed-number spans without `dir="ltr"` get reordered

The well-known case: deltas like `(+28.2%)` flipping to `(28.2%+)`.
The less obvious case used to be a **positive** transaction amount
rendered as `"+" + formatCurrency(150)`: the helper output was
bidi-safe, but the literal `+` was outside it and got reordered.

The shared helpers in `numberFormatting.ts` now wrap output in
U+2066 (LRI) ... U+2069 (PDI) and put NBSP between digits and ₪.
That means a bare `<span>{formatCurrency(x)}</span>` is correct
under RTL — no `dir="ltr"` needed.

You **still** need `dir="ltr"` (or use `formatChange`, which already
includes the sign) when you concatenate something around the helper
output yourself:

```tsx
// WRONG — literal "+" sits outside the LRI/PDI envelope and flips
<span>{isPositive ? "+" : ""}{formatCurrency(amount)}</span>

// CORRECT — the literal "+" is now inside an LTR run
<span dir="ltr">{isPositive ? "+" : ""}{formatCurrency(amount)}</span>

// BETTER — let formatChange handle the sign
<span>{formatChange(amount)}</span>
```

Same rule for percent deltas (`(${formatPercentChange(x)})`), date +
currency joined on one line, two helper outputs joined with `" / "`,
etc. — anything you build outside the helpers needs the wrapper.

## Hardcoded Relative-Time Strings

Don't ship strings like `` `${days}d ago` `` or `"in 3 hours"`. They
slip into Hebrew UIs unchanged. Route them through `t(...)` with
`{{count}}` interpolation:

```json
// en.json
"daysAgo": "{{count}}d ago"

// he.json
"daysAgo": "לפני {{count}} ימים"
```

```tsx
t("investments.daysAgo", { count: snapshotAgeDays })
```

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
patches for local effects. The shared mutation cache already
runs a debounced global sweep after every mutation settles — you
don't need to add another one. It also cancels reads that were in
flight when the write began, so they cannot revert your patch. See `frontend_components.md` →
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

## Rounded Scroll Containers

A scroll container cannot round its own scrollbar away. Blink paints the
scrollbar inside the element's **border box**, and `border-radius` clips
content, not scrollbar gutters — so an element that is both rounded and its
own scroller gets the scrollbar drawn across its rounded corners and over its
border. With this app's `::-webkit-scrollbar` styling (8px, solid track) that
is plainly visible; it shipped in the Settings popup.

The same defect has a second shape: a rounded **panel** that clamps its
height and lets a child scroll. The panel clips nothing, so the child's
scrollbar runs over the panel's corners instead.

```tsx
// WRONG — the rounded element is the scroller
<div className="rounded-2xl border p-6 max-h-[90vh] overflow-y-auto">…</div>

// WRONG — rounded panel, scrolling child, nothing clipping
<div className="rounded-2xl border max-h-[80vh] flex flex-col">
  <div className="flex-1 overflow-y-auto">…</div>
</div>

// CORRECT — radius + border on a clipping parent, scrolling on the child
<div className="rounded-2xl border overflow-hidden flex flex-col max-h-[90vh]">
  <div className="flex-1 min-h-0 overflow-y-auto p-6">…</div>
</div>
```

The radius, border and background belong to the wrapper; padding moves to the
scroller (so the scrollbar sits outside it, flush to the clipped edge). This
is what `components/common/Modal.tsx` already does — reach for it before
hand-rolling a panel.

Both shapes are enforced by `frontend/src/roundedScrollContainers.test.ts`
(a source scan, runs in `npm test`), with the behavioural half in
`e2e/dashboard-layout.spec.ts`.

## Capped Scroll Regions Swallow the Page's Scroll

A height cap turns an element into a scroll container, and a scroll container
owns every gesture that starts on it. Browsers chain a drag to the page only
when the inner scroller **could not move at all**, and they do not start
chaining part-way through one — so a list capped at a height its content
barely passes scrolls those few pixels and then holds the finger. On a phone
that reads as "the page won't scroll here", over a list hiding nothing worth
reaching. The savings-goals card shipped exactly that.

Cap conditionally instead. `hooks/useScrollCap.ts` measures the content and
turns the cap on only once it hides about a row:

```tsx
// WRONG — a scroll region whether or not there is anything to scroll
<div className="space-y-2 max-h-[20rem] overflow-y-auto">…</div>

// CORRECT — a plain block until the cap earns its keep
const [listRef, capped] = useScrollCap(320, rows.length);
<div ref={listRef} className={capped ? "max-h-[20rem] overflow-y-auto" : ""}>…</div>
```

Pass anything that changes with the content as the second argument: a capped
element's own box stops changing size, so a resize observer alone never
notices rows arriving.

Two things stay exempt, and the scan knows both:

- **Modals, popups and drawers.** The page behind them is locked, so there is
  nothing to chain to and the cap is always right.
- **Panes the layout fixes** (`min-h-*` and `max-h-*` together, e.g. a grid
  cell that must match its neighbour's height). Their height is structural;
  dropping the cap would move the layout.

`overscroll-contain` is a different knob and does not help here — it governs
what happens once the inner scroller is exhausted, not whether the gesture was
taken in the first place.

Enforced by `frontend/src/cappedScrollRegions.test.ts` (a source scan, runs in
`npm test`), with the behavioural half in `e2e/savings-goals.spec.ts`.

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
