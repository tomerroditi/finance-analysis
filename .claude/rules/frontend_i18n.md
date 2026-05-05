---
paths:
  - "frontend/src/**/*.{ts,tsx}"
---

# Frontend i18n - Hebrew/English Bilingual UI

## Stack

- **Library:** `i18next` + `react-i18next`
- **Config:** `frontend/src/i18n.ts`
- **Translations:** `frontend/src/locales/en.json`, `frontend/src/locales/he.json`
- **Default language:** English, persisted to `localStorage`
- **RTL:** Automatic — `document.documentElement.dir` switches on language change

## Translation Keys

Translations are nested JSON organized by feature section:

```
common, sidebar, settings, dashboard, transactions, budget,
categories, investments, dataSources, insurance, modals,
dateRange, tooltips, services, ruleBuilder
```

**Adding new strings:** Always add to BOTH `en.json` and `he.json` under the same key path.

## Usage Patterns

### Basic translation
```tsx
const { t } = useTranslation();
return <h1>{t("dashboard.title")}</h1>;
```

### RTL-aware icon flipping
```tsx
const { i18n } = useTranslation();
const isRtl = i18n.language === "he";
{isRtl ? <ChevronRight /> : <ChevronLeft />}
```

### Numbers/currency in Hebrew context
Wrap numeric values with `dir="ltr"` to keep them left-to-right inside RTL text:
```tsx
<span dir="ltr">{formatCurrency(amount)}</span>
```

**This applies to every signed-number node, not just deltas.** A common
miss: a feed row or table cell renders
`{isPositive ? "+" : ""}{formatCurrency(...)}` with no `dir`. Negatives
still render correctly because `formatCurrency` injects the bidi marks
itself; positives prefix a bare `+` literal that the bidi algorithm
reorders under RTL — `+150 ₪` next to a Hebrew description ends up
visually scrambled. **Every numeric/currency span needs `dir="ltr"`,
including inside `<td>`/`<th>` cells, regardless of sign.** The bug we
keep relapsing into looks like:

```tsx
{/* WRONG */}
<span className={isPositive ? "text-emerald-400" : "text-rose-400"}>
  {isPositive ? "+" : ""}{formatCurrency(amount)}
</span>

{/* CORRECT */}
<span dir="ltr" className={isPositive ? "text-emerald-400" : "text-rose-400"}>
  {isPositive ? "+" : ""}{formatCurrency(amount)}
</span>
```

### Truncation of user-supplied text inside RTL — use `dir="auto"`

`text-overflow: ellipsis` (Tailwind's `truncate` / `line-clamp-N`) clips
at the **end of the line in the document direction**. Under RTL that's
the visual left. A category badge `"Transportation / Gas"` rendered
inside an RTL container becomes `"...sportation / Gas"` — the leading
characters are hidden because the user reads right-to-left.

Fix: every `truncate`/`line-clamp` element whose **content is user
data** (transaction descriptions, category names, account names, rule
names, project names, notes, etc.) must add `dir="auto"`:

```tsx
{/* WRONG — clips "Transportation / Gas" to "...sportation / Gas" in RTL */}
<span className="truncate">{tx.category}</span>

{/* CORRECT — first-strong-char detection picks LTR for English content,
    so ellipsis goes on the right; Hebrew content stays RTL with ellipsis
    on the left. */}
<span className="truncate" dir="auto">{tx.category}</span>
```

Translated chrome (column headers, button labels, section titles) does
**not** need `dir="auto"` — it always matches the document direction.
Rule of thumb: if the string came from `t(...)` it stays untagged; if
it came from a DB column or user input, add `dir="auto"`.

## RTL Layout Rules

### Prefer Tailwind CSS 4 logical properties over physical ones:
| Physical (avoid) | Logical (use instead) |
|---|---|
| `left-*` / `right-*` | `inset-inline-start-*` / `inset-inline-end-*` |
| `pl-*` / `pr-*` | `ps-*` / `pe-*` |
| `ml-*` / `mr-*` | `ms-*` / `me-*` |
| `border-l` / `border-r` | `border-s` / `border-e` |
| `text-left` / `text-right` | `text-start` / `text-end` |
| `rounded-l-*` / `rounded-r-*` | `rounded-s-*` / `rounded-e-*` |

Logical properties auto-flip in RTL — no conditional classes needed.

### When to use `isRtl` conditionals
Only when logical properties aren't sufficient:
- Flipping directional icons (chevrons, arrows)
- Third-party components that don't support logical properties
- Animations with directional transforms (e.g., slide-in direction)

## Date & Number Formatting

- **Dates:** `frontend/src/utils/dateFormatting.ts` — uses `date-fns` with Hebrew locale (`he`) when language is Hebrew
- **Currency:** Always use `formatCurrency()` from `utils/numberFormatting.ts` — never inline `new Intl.NumberFormat()`
- **Plotly charts:** Hebrew locale registered in `frontend/src/utils/plotlyLocale.ts` (day/month names, date format)

## Provider/Service Name Localization

`frontend/src/utils/textFormatting.ts` maintains parallel label maps:
- `PROVIDER_LABELS` (English) / `PROVIDER_LABELS_HE` (Hebrew) for financial institution names
- `humanizeProvider()` and `humanizeService()` auto-select by current language

When adding a new provider, add its display name to BOTH maps.

## Checklist for New UI Features

1. All user-visible strings use `t("section.key")` — no hardcoded English/Hebrew
2. Keys added to both `en.json` and `he.json`
3. Layout uses logical CSS properties (not physical left/right)
4. Numeric / signed values wrapped in `dir="ltr"` (always, even unsigned, especially inside table cells and feed rows)
5. `truncate` / `line-clamp` on user-supplied text gets `dir="auto"`
6. Directional icons flip based on `isRtl` check
7. New provider/service names added to both label maps in `textFormatting.ts`
8. Hardcoded relative-time strings (`"5d ago"`, `"in 3 hours"`) routed through `t(...)` with `{{count}}` interpolation
