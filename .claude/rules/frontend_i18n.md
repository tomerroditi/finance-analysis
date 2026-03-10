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
- **Numbers:** Use `Intl.NumberFormat("he-IL")` for locale-aware formatting
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
4. Numeric values wrapped in `dir="ltr"` spans when inside translatable text
5. Directional icons flip based on `isRtl` check
6. New provider/service names added to both label maps in `textFormatting.ts`
