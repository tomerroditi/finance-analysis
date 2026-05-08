# Empty States Redesign

**Date:** 2026-05-08
**Status:** Approved

## Summary

Improve all empty-state screens across the dashboard. Replace ad-hoc inline text with a consistent, actionable pattern that guides users to either connect their accounts or try demo mode.

---

## Two Variants

### Variant 1 — Onboarding (scrape-sourced pages)

Used on pages whose data comes entirely from scraping. Shows a 3-step flow to make clear what the user needs to do.

**Structure:**
- Title (bold, `text-xl`)
- Description (muted, `text-sm`)
- Three step cards: **Connect → Scrape → Analyse**, separated by `→` arrows. Each card has a bold title and one short description line. No icons or numbers inside the cards.
- Two buttons: **Connect accounts** (primary, navigates to `/data-sources`) and **Try demo mode** (secondary, triggers inline confirmation)

**Pages:**
| Page | Title | Description |
|---|---|---|
| Dashboard | No data yet | Connect your accounts to see your full financial picture. |
| Transactions | No transactions yet | Connect your accounts to start importing your transactions. |

**Filter-empty distinction:** On the Transactions page, if filters are active and return no results, show a plain `EmptyState` (no steps, no buttons) with title "No transactions found" and description "Try adjusting your filters." The onboarding variant only shows when the database is completely empty (zero transactions across all sources).

### Variant 2 — Simple (manually-created pages)

Used on pages where the user creates items directly. No step cards.

**Structure:**
- Title (bold, `text-xl`)
- Description (muted, `text-sm`)
- Two buttons: **Add [item]** (primary, opens the existing add modal/form) and **Try demo mode** (secondary, triggers inline confirmation)

**Pages:**
| Page | Title | Description | Primary CTA label |
|---|---|---|---|
| Budget | No budgets configured | Add a budget to start tracking your monthly spending. | + Add budget |
| Investments | No active investments | Create your first investment to start tracking your portfolio. | + Add investment |
| Liabilities | No liabilities tracked | Add a loan or debt to monitor what you owe. | + Add liability |
| Insurance | No insurance policies | Add a policy to keep track of your coverage. | + Add policy |

---

## "Try demo mode" Confirmation Popover

Clicking "Try demo mode" opens a small popover anchored below the button (not a full modal). Contents:

- One line of copy: *"Switches to sample data — your real data won't be affected."*
- **Enable demo mode** button (calls `toggleDemoMode(true)` from `DemoModeContext`, then shows a success toast)
- **Cancel** text link

On confirm: `toggleDemoMode(true)` handles the API call and `queryClient.resetQueries()` internally. Show a toast: *"Demo mode enabled"*. The page re-renders with demo data automatically.

The popover is a small `div` rendered inline (not via portal), positioned with `absolute` below the button. It dismisses on outside click via a transparent backdrop.

---

## Component Changes

### `EmptyState` — add `steps` prop

Extend the existing component with one new optional prop:

```ts
steps?: Array<{ title: string; description: string }>
```

When `steps` is provided, render the step cards between the description and the CTA buttons. Each card uses the same `bg-[var(--surface-light)]` background as existing inner surfaces. Arrows between cards use `text-[var(--primary)]`.

No other changes to `EmptyState`. The existing `cta` / `secondary` / `size` props remain unchanged.

### New `DemoModeConfirmPopover` component

A small, self-contained component used inside the `secondary.onClick` handler via local `useState`. Lives in `components/common/`. Props:

```ts
interface DemoModeConfirmPopoverProps {
  isOpen: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLButtonElement>;
}
```

Internally calls `useDemoMode()` and `useTranslation()`. Shows the confirmation copy and two actions.

---

## i18n Keys

New keys to add to both `en.json` and `he.json` under `emptyStates.*`:

```
emptyStates.connectStep.title       "Connect"
emptyStates.connectStep.description "Add your bank or credit card accounts"
emptyStates.scrapeStep.title        "Scrape"
emptyStates.scrapeStep.description  "Import your transactions"
emptyStates.analyseStep.title       "Analyse"
emptyStates.analyseStep.description "See your full financial picture"

emptyStates.dashboard.title         "No data yet"
emptyStates.dashboard.description   "Connect your accounts to see your full financial picture."
emptyStates.transactions.title      "No transactions yet"
emptyStates.transactions.description "Connect your accounts to start importing your transactions."
emptyStates.transactionsFiltered.title       "No transactions found"
emptyStates.transactionsFiltered.description "Try adjusting your filters."

emptyStates.budget.title            "No budgets configured"
emptyStates.budget.description      "Add a budget to start tracking your monthly spending."
emptyStates.investments.title       "No active investments"
emptyStates.investments.description "Create your first investment to start tracking your portfolio."
emptyStates.liabilities.title       "No liabilities tracked"
emptyStates.liabilities.description "Add a loan or debt to monitor what you owe."
emptyStates.insurance.title         "No insurance policies"
emptyStates.insurance.description   "Add a policy to keep track of your coverage."

emptyStates.connectAccounts         "Connect accounts"
emptyStates.tryDemoMode             "Try demo mode"
emptyStates.demoConfirmDescription  "Switches to sample data — your real data won't be affected."
emptyStates.demoConfirmEnable       "Enable demo mode"
emptyStates.demoConfirmCancel       "Cancel"
emptyStates.demoModeEnabled         "Demo mode enabled"
```

---

## Pages Not in Scope

- **Categories** — pre-seeded with defaults, no meaningful empty state
- **Early Retirement** — calculator, no data dependency
- **Data Sources** — already handles its own "no accounts" state

---

## Out of Scope

- Animation / illustration assets
- Loading skeleton states
- Any backend changes
