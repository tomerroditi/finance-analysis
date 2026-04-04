---
paths:
  - "frontend/src/utils/**/*.{ts,tsx}"
  - "frontend/src/hooks/**/*.{ts,tsx}"
  - "frontend/src/types/**/*.{ts,tsx}"
  - "frontend/src/stores/**/*.{ts,tsx}"
  - "frontend/src/services/**/*.{ts,tsx}"
---

# Frontend Non-Component Layers — Utils, Hooks, Types, Stores, Services

## Directory Overview

```
frontend/src/
├── utils/          # Pure helper functions (no React, no side effects)
├── hooks/          # Custom React hooks (data fetching, shared state logic)
├── types/          # Canonical TypeScript type definitions
├── stores/         # Zustand global state stores
├── services/       # API client (axios-based)
├── context/        # React Context providers
├── locales/        # i18n translation files (en.json, he.json)
└── mocks/          # Demo mode mock data
```

## Utils (`utils/`)

Pure helper functions — stateless, no React, no side effects.

| File | Purpose | Key Exports |
|------|---------|-------------|
| `numberFormatting.ts` | Currency display | `formatCurrency(value, maxDigits?)`, `formatCompactCurrency(value)` |
| `dateFormatting.ts` | Date display (date-fns, Hebrew locale) | `formatDate()`, `formatMonth()` |
| `textFormatting.ts` | Provider/service labels (bilingual) | `humanizeProvider()`, `humanizeService()`, `PROVIDER_LABELS`, `PROVIDER_LABELS_HE` |
| `taggingRuleEval.ts` | Evaluate tagging rule conditions against transactions | `findMatchingRule()`, `evalConditionTree()` |
| `plotlyLocale.ts` | Plotly chart theme, Hebrew locale, touch detection | `chartTheme`, `plotlyConfig()`, `isTouchDevice` |

**Rules:**
- Always use `formatCurrency()` from `numberFormatting.ts` — never inline `new Intl.NumberFormat()`
- When adding a new provider, add its label to BOTH `PROVIDER_LABELS` and `PROVIDER_LABELS_HE` in `textFormatting.ts`

## Hooks (`hooks/`)

Custom React hooks for shared data fetching and stateful logic.

| Hook | Replaces | Query Key |
|------|----------|-----------|
| `useCategories()` | 10+ duplicate `useQuery(["categories"])` calls | `["categories"]` |
| `useCashBalances()` | 5 duplicate cash balance queries | `["cashBalances"]` |
| `useTaggingRules()` | 4 duplicate tagging rule queries | `["taggingRules"]` |
| `useTransactionFilters()` | Complex filter state management | N/A (local state) |
| `useCategoryTagCreate()` | Category/tag creation mutation logic | N/A (mutation) |
| `useScraping()` | Scraping progress state machine | N/A (state) |
| `useScrollLock(isOpen)` | Body scroll prevention for modals | N/A (side effect) |

**When to create a new shared hook:**
- The same `useQuery` pattern (same `queryKey` + `queryFn`) appears in **3+ components**
- Complex stateful logic is duplicated across components

**When NOT to create a hook:**
- A query is used in only 1–2 places — inline `useQuery` is fine
- Simple one-liner state — `useState` in the component is fine

## Types (`types/`)

Canonical type definitions shared across the frontend.

| File | Key Types |
|------|-----------|
| `transaction.ts` | `Transaction` — the universal transaction interface |

**Rules:**
- Import `Transaction` from `../../types/transaction` — this is the canonical source
- Do NOT re-export types from component files
- When multiple components need the same interface, define it in `types/`

## Stores (`stores/`)

Zustand stores for global client-side state.

| Store | Purpose |
|-------|---------|
| `appStore.ts` | App-wide UI state: sidebar collapse, mobile sidebar, language, demo mode, date range |

**Use Zustand for:** UI state shared across unrelated components (sidebar, language, date range).
**Use React Query for:** All server/API data. Never duplicate API data in Zustand.

## Services (`services/`)

| File | Purpose |
|------|---------|
| `api.ts` | Centralized axios client with all API endpoint functions, organized by domain (taggingApi, budgetApi, bankApi, etc.) |

**Rules:**
- All API calls go through `services/api.ts` — never import axios directly in components
- API functions return `AxiosResponse` — callers access `.data` on the result
