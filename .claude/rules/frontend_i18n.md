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

**Israeli convention is digits-then-shekel.** `formatCurrency`,
`formatCompactCurrency`, and `formatChange` (in
`frontend/src/utils/numberFormatting.ts`) all emit the canonical
**sign-magnitude-currency** layout:

```
1,003,211 ₪
-25K ₪
+150 ₪
```

Not `₪1,003,211`, not `₪ -25K`. If you find yourself prepending `₪`,
use the helpers — don't roll your own.

**The helpers are bidi-stable.** Each output is wrapped in U+2066 (LRI,
Left-to-Right Isolate) ... U+2069 (PDI, Pop Directional Isolate) and
uses NBSP between digits and ₪. That means the digits-then-shekel order
survives any surrounding paragraph direction — you can drop a
`formatCurrency(amount)` into a Hebrew sentence, an RTL `<td>`, or a
plain text node and it will render correctly without an explicit
`dir="ltr"` wrapper.

**You still need `dir="ltr"` when you concatenate something around the
helper output yourself.** E.g.:

```tsx
{/* OK — helper output is bidi-stable on its own */}
<span>{formatCurrency(amount)}</span>

{/* OK — concatenated literal "+", needs dir="ltr" for the literal */}
<span dir="ltr">{isPositive ? "+" : ""}{formatCurrency(amount)}</span>

{/* For deltas use formatChange, which already includes the sign */}
<span>{formatChange(delta)}</span>   {/* "+35K ₪" — bidi-stable */}
```

The previous rule "every numeric span needs `dir="ltr"`" still applies
when you build the string yourself (date + currency joined with `" / "`,
hand-written `"+" + formatted`, etc.). It's just no longer needed for a
bare helper call.

**Don't inline `new Intl.NumberFormat()` in components.** It produces
locale-dependent output that breaks the canonical layout — the
`he-IL` locale puts ₪ after the digits without LRI/PDI, and the
plain default locale puts it before. Either way you're back to the
`1,003,211₪` / `-₪25K` inconsistency we keep getting bitten by.

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
| `left-*` / `right-*` | `start-*` / `end-*` |
| `pl-*` / `pr-*` | `ps-*` / `pe-*` |
| `ml-*` / `mr-*` | `ms-*` / `me-*` |
| `border-l` / `border-r` | `border-s` / `border-e` |
| `text-left` / `text-right` | `text-start` / `text-end` |
| `rounded-l-*` / `rounded-r-*` | `rounded-s-*` / `rounded-e-*` |

Logical properties auto-flip in RTL — no conditional classes needed.

**Name the utility, not the CSS property.** Tailwind's class is `start-0`,
not `inset-inline-start-0`; `inset-x-0` / `inset-y-0`, not `inset-inline-0` /
`inset-block-0`. A property-spelled class matches no utility, so Tailwind
emits **no CSS at all** and the browser ignores it silently — an absolutely
positioned element then falls back to its *static* position instead of
erroring. This table used to recommend the property spelling, and five
elements shipped with dead classes before anyone noticed: a settings toggle
whose knob never moved, and a sidebar footer that shrink-wrapped instead of
spanning the sidebar. The other three only looked right because the static
position happened to match.

Two guards now enforce this: `src/tailwindLogicalProperties.test.ts` (vitest,
scans source for property-spelled classes) and `e2e/rtl-logical-insets.spec.ts`
(asserts computed geometry — a className assertion would pass against the bug,
since the dead class is still present in the DOM).

### When to use `isRtl` conditionals
Only when logical properties aren't sufficient:
- Flipping directional icons (chevrons, arrows)
- Third-party components that don't support logical properties
- Animations with directional transforms (e.g., slide-in direction)

## Date & Number Formatting

- **Dates:** `frontend/src/utils/dateFormatting.ts` — uses `date-fns` with Hebrew locale (`he`) when language is Hebrew
- **Currency:** Always use `formatCurrency()` from `utils/numberFormatting.ts` — never inline `new Intl.NumberFormat()`
- **Charts (Recharts):** axis ticks and tooltip labels go through the `date-fns` helpers in `dateFormatting.ts` (e.g. `formatMonthCompact`, `formatMonthYear`), which already switch to the Hebrew locale

## Provider/Service Name Localization

`frontend/src/utils/textFormatting.ts` maintains parallel label maps:
- `PROVIDER_LABELS` (English) / `PROVIDER_LABELS_HE` (Hebrew) for financial institution names
- `humanizeProvider()` and `humanizeService()` auto-select by current language

When adding a new provider, add its display name to BOTH maps.

## Checklist for New UI Features

1. All user-visible strings use `t("section.key")` — no hardcoded English/Hebrew
2. Keys added to both `en.json` and `he.json`
3. Layout uses logical CSS properties (not physical left/right)
4. Currency rendered through `formatCurrency` / `formatCompactCurrency` / `formatChange` — never inline `Intl.NumberFormat`. The helpers emit `<digits> ₪` and are LRI/PDI-isolated, so a bare `<span>{formatCurrency(...)}</span>` is safe under RTL
5. Hand-built numeric strings (concatenation, literal `+`/`-` outside the helpers, date + currency joined manually) still need a `dir="ltr"` wrapper
6. `truncate` / `line-clamp` on user-supplied text gets `dir="auto"`
7. Directional icons flip based on `isRtl` check
8. New provider/service names added to both label maps in `textFormatting.ts`
9. Hardcoded relative-time strings (`"5d ago"`, `"in 3 hours"`) routed through `t(...)` with `{{count}}` interpolation
