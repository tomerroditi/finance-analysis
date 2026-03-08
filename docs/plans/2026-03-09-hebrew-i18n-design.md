# Hebrew i18n + Settings Popup — Design

## Overview

Add Hebrew language support to the finance analysis dashboard with full RTL layout flipping, controlled via a new settings popup accessible from the sidebar.

## Settings Popup

- **Trigger:** Gear icon (`Settings` from lucide-react) at the bottom of the sidebar, below nav items
- **UI:** Popover anchored to the right of the icon, styled consistently with existing app (dark surface `bg-[var(--surface)]`, rounded, shadow, blur backdrop)
- **Contents:**
  - Language toggle — English / Hebrew (segmented control)
  - Demo Mode toggle — relocated from sidebar footer
- **Behavior:** Closes on outside click or Escape key. Expandable for future settings.

## Internationalization

- **Library:** `react-i18next` + `i18next` + `i18next-browser-languagedetector`
- **Translation files:** Single JSON per language — `frontend/src/locales/en.json` and `frontend/src/locales/he.json`
- **Key structure:** Nested by component area (e.g. `sidebar.dashboard`, `dashboard.totalIncome`, `transactions.table.date`)
- **Persistence:** `localStorage` key (via i18next-browser-languagedetector or manual)
- **Integration:** `useTranslation()` hook in components, replacing all hardcoded strings

## RTL Support

- **Direction switching:** `document.documentElement.dir` set to `"rtl"` or `"ltr"`, `lang` attribute set to `"he"` or `"en"`
- **Tailwind RTL:** Tailwind v4 supports `dir` attribute natively. Use `rtl:` variant for directional styles (margins, paddings, border-radius, flex)
- **Sidebar:** Flips to right side in RTL mode. Main content margin adjusts accordingly.
- **Charts (Plotly):** Stay LTR — numerical/chart data doesn't need flipping
- **Currency:** Already uses `he-IL` locale via `Intl.NumberFormat`, no changes needed

## String Extraction Scope

All user-facing hardcoded text:

| Area | Files |
|------|-------|
| Sidebar | `Sidebar.tsx` — nav labels, logo text |
| GlobalSearch | `GlobalSearch.tsx` — placeholder, result labels |
| Pages (7) | `Dashboard.tsx`, `Transactions.tsx`, `Budget.tsx`, `Categories.tsx`, `Investments.tsx`, `Insurances.tsx`, `DataSources.tsx` |
| Modals (8) | `ConfirmationModal.tsx`, `TransactionFormModal.tsx`, `TransactionEditorModal.tsx`, `SplitTransactionModal.tsx`, `LinkRefundModal.tsx`, `ProjectModal.tsx`, `BudgetRuleModal.tsx`, `RuleManager.tsx` |
| Common components | `TransactionsTable.tsx`, `DateRangePicker.tsx`, filter panels, `SelectDropdown.tsx` |
| Utilities | `textFormatting.ts` — `humanizeProvider()`, `humanizeAccountType()` |

## Out of Scope

- Backend i18n (API responses stay English)
- User-generated content translation (category names, transaction descriptions)
- Complex pluralization rules
- Date format changes (date-fns already handles locale-aware formatting)
