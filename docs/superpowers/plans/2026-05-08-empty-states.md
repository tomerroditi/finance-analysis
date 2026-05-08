# Empty States Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ad-hoc empty-state copy across Dashboard, Transactions, Budget, Investments, Liabilities, and Insurances with consistent `EmptyState` components that guide the user to connect accounts or try demo mode.

**Architecture:** Extend `EmptyState` with an optional `steps` prop (renders the 3-step onboarding flow) and make `icon` optional. Add a `DemoModeConfirmPopover` component (self-contained inline confirmation). Each page manages local `showDemoConfirm` state and passes the popover through the existing `footer` slot.

**Tech Stack:** React 19, TypeScript, Tailwind CSS 4, i18next, Vitest + Testing Library, MSW

---

## File Map

| Action | Path | Change |
|---|---|---|
| Modify | `frontend/src/components/common/EmptyState.tsx` | Make `icon` optional, add `steps` prop |
| Modify | `frontend/src/components/common/EmptyState.test.tsx` | Add tests for `steps` and icon-less rendering |
| Create | `frontend/src/components/common/DemoModeConfirmPopover.tsx` | Inline demo mode confirmation |
| Create | `frontend/src/components/common/DemoModeConfirmPopover.test.tsx` | Tests |
| Modify | `frontend/src/locales/en.json` | Add `emptyStates.*` keys |
| Modify | `frontend/src/locales/he.json` | Add translated `emptyStates.*` keys |
| Modify | `frontend/src/pages/Dashboard.tsx` | Onboarding empty state (3-step) |
| Modify | `frontend/src/pages/Transactions.tsx` | Onboarding empty state (3-step) |
| Modify | `frontend/src/components/budget/MonthlyBudgetView.tsx` | Simple empty state for no budgets |
| Modify | `frontend/src/pages/Investments.tsx` | Remove icon, add demo mode secondary |
| Modify | `frontend/src/pages/Liabilities.tsx` | Remove icon, add demo mode secondary |
| Modify | `frontend/src/pages/Insurances.tsx` | Replace ad-hoc div with `EmptyState` |

---

## Task 1: Extend `EmptyState` — `steps` prop + optional `icon`

**Files:**
- Modify: `frontend/src/components/common/EmptyState.tsx`
- Modify: `frontend/src/components/common/EmptyState.test.tsx`

- [ ] **Step 1.1: Add failing tests**

Open `frontend/src/components/common/EmptyState.test.tsx` and append these two tests inside the `describe` block (after the last `it`):

```tsx
it("renders without an icon when icon prop is omitted", () => {
  renderWithProviders(<EmptyState title="No data" />);
  expect(screen.getByRole("status")).toBeInTheDocument();
  // No SVG icon wrapper present
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

it("renders step cards with arrows when steps prop is provided", () => {
  renderWithProviders(
    <EmptyState
      title="No data"
      steps={[
        { title: "Connect", description: "Add your accounts" },
        { title: "Scrape", description: "Import transactions" },
        { title: "Analyse", description: "See your picture" },
      ]}
    />,
  );
  expect(screen.getByText("Connect")).toBeInTheDocument();
  expect(screen.getByText("Add your accounts")).toBeInTheDocument();
  expect(screen.getByText("Scrape")).toBeInTheDocument();
  expect(screen.getByText("Analyse")).toBeInTheDocument();
  // Two arrows between three steps
  expect(screen.getAllByText("→")).toHaveLength(2);
});
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd frontend && npm test -- --run src/components/common/EmptyState.test.tsx
```

Expected: 2 new tests FAIL (type error on missing `icon` and missing `steps` rendering).

- [ ] **Step 1.3: Update `EmptyState.tsx`**

Replace the full file content:

```tsx
import { Fragment, type ComponentType, type ReactNode } from "react";
import { type LucideProps } from "lucide-react";

interface EmptyStateProps {
  /** Lucide icon component shown above the title. Omit for icon-less variant. */
  icon?: ComponentType<LucideProps>;
  /** Headline — short, sentence case. Already-translated string. */
  title: string;
  /** Optional supporting copy. Already-translated string. */
  description?: string;
  /**
   * Optional 2–4 step cards rendered between the description and the CTA
   * buttons. Use for onboarding flows where the user needs a sequence of
   * actions to get data flowing (connect → scrape → analyse).
   */
  steps?: Array<{ title: string; description: string }>;
  /**
   * Primary call-to-action. Use a single CTA per empty state — the goal
   * is to give the user one obvious next step.
   */
  cta?: {
    label: string;
    onClick: () => void;
  };
  /**
   * Secondary supporting action (e.g. "Try demo mode"). Render only when
   * the primary CTA is present and a true alternative exists.
   */
  secondary?: {
    label: string;
    onClick: () => void;
  };
  /**
   * Optional fully-rendered footer slot for cases where the action isn't
   * a single button (e.g. inline confirmation dialogs).
   */
  footer?: ReactNode;
  /** Compact variant for inline / in-card usage. Default is page-level. */
  size?: "page" | "inline";
  className?: string;
}

/**
 * Per-page empty-state placeholder with an optional 3-step onboarding flow
 * and a single primary CTA.
 *
 * The component is presentational: callers are responsible for translating
 * all string props via i18next before passing them in.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  steps,
  cta,
  secondary,
  footer,
  size = "page",
  className = "",
}: EmptyStateProps) {
  const isPage = size === "page";

  const containerClasses = isPage
    ? "bg-[var(--surface)] border border-dashed border-[var(--surface-light)] rounded-3xl p-8 md:p-16 text-center"
    : "bg-[var(--surface-light)]/40 border border-dashed border-[var(--surface-light)] rounded-2xl p-6 md:p-8 text-center";

  const iconClasses = isPage
    ? "p-4 bg-[var(--surface-light)] rounded-2xl w-fit mx-auto mb-6 text-[var(--text-muted)]"
    : "p-3 bg-[var(--surface-light)] rounded-xl w-fit mx-auto mb-4 text-[var(--text-muted)]";

  const titleClasses = isPage
    ? "text-xl md:text-2xl font-bold mb-2"
    : "text-lg font-bold mb-2";

  return (
    <div role="status" className={`${containerClasses} ${className}`}>
      {Icon && (
        <div className={iconClasses}>
          <Icon size={isPage ? 32 : 24} />
        </div>
      )}
      <h2 className={titleClasses}>{title}</h2>
      {description && (
        <p className="text-sm text-[var(--text-muted)] max-w-md mx-auto">
          {description}
        </p>
      )}
      {steps && steps.length > 0 && (
        <div className="flex items-start gap-2 justify-center mt-6 max-w-sm mx-auto">
          {steps.map((step, i) => (
            <Fragment key={i}>
              <div className="flex-1 min-w-0 bg-[var(--surface-light)] rounded-xl p-3 text-center">
                <p className="text-sm font-semibold text-[var(--text)]">
                  {step.title}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  {step.description}
                </p>
              </div>
              {i < steps.length - 1 && (
                <span
                  className="text-[var(--primary)] text-base shrink-0 mt-3"
                  dir="ltr"
                  aria-hidden="true"
                >
                  →
                </span>
              )}
            </Fragment>
          ))}
        </div>
      )}
      {(cta || secondary) && (
        <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
          {cta && (
            <button
              type="button"
              onClick={cta.onClick}
              className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white font-medium hover:bg-[var(--primary)]/90 transition-colors w-full sm:w-auto"
            >
              {cta.label}
            </button>
          )}
          {secondary && (
            <button
              type="button"
              onClick={secondary.onClick}
              className="px-4 py-2 rounded-lg bg-transparent text-[var(--text)] font-medium border border-[var(--surface-light)] hover:bg-[var(--surface-light)]/40 transition-colors w-full sm:w-auto"
            >
              {secondary.label}
            </button>
          )}
        </div>
      )}
      {footer && <div className="mt-4">{footer}</div>}
    </div>
  );
}
```

- [ ] **Step 1.4: Run tests — all must pass**

```bash
cd frontend && npm test -- --run src/components/common/EmptyState.test.tsx
```

Expected: all 8 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
git add frontend/src/components/common/EmptyState.tsx \
        frontend/src/components/common/EmptyState.test.tsx
git commit -m "feat(ui): extend EmptyState with optional icon and steps prop"
```

---

## Task 2: Create `DemoModeConfirmPopover`

**Files:**
- Create: `frontend/src/components/common/DemoModeConfirmPopover.tsx`
- Create: `frontend/src/components/common/DemoModeConfirmPopover.test.tsx`

- [ ] **Step 2.1: Write the failing test**

Create `frontend/src/components/common/DemoModeConfirmPopover.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DemoModeConfirmPopover } from "./DemoModeConfirmPopover";
import { renderWithProviders } from "../../test-utils";

describe("DemoModeConfirmPopover", () => {
  it("renders the confirmation description and both action buttons", () => {
    renderWithProviders(<DemoModeConfirmPopover onClose={vi.fn()} />);
    expect(
      screen.getByText(/sample data/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /enable demo mode/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /cancel/i }),
    ).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<DemoModeConfirmPopover onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2.2: Run test to confirm it fails**

```bash
cd frontend && npm test -- --run src/components/common/DemoModeConfirmPopover.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 2.3: Create `DemoModeConfirmPopover.tsx`**

Create `frontend/src/components/common/DemoModeConfirmPopover.tsx`:

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";

interface DemoModeConfirmPopoverProps {
  onClose: () => void;
}

/**
 * Inline confirmation shown when the user clicks "Try demo mode" inside an
 * empty-state component. Enables demo mode on confirm and calls onClose when
 * done. Pass this as the `footer` prop of `EmptyState`.
 */
export function DemoModeConfirmPopover({
  onClose,
}: DemoModeConfirmPopoverProps) {
  const { toggleDemoMode } = useDemoMode();
  const { t } = useTranslation();
  const [isPending, setIsPending] = useState(false);

  const handleConfirm = async () => {
    setIsPending(true);
    try {
      await toggleDemoMode(true);
      onClose();
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="mt-2 p-4 bg-[var(--surface-light)] rounded-xl border border-[var(--surface-light)] text-sm text-center">
      <p className="text-[var(--text-muted)] mb-3">
        {t("emptyStates.demoConfirmDescription")}
      </p>
      <div className="flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={isPending}
          className="px-4 py-1.5 rounded-lg bg-[var(--primary)] text-white font-medium hover:bg-[var(--primary)]/90 transition-colors disabled:opacity-50"
        >
          {t("emptyStates.demoConfirmEnable")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {t("emptyStates.demoConfirmCancel")}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2.4: Run tests — all must pass**

```bash
cd frontend && npm test -- --run src/components/common/DemoModeConfirmPopover.test.tsx
```

Expected: 2 tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add frontend/src/components/common/DemoModeConfirmPopover.tsx \
        frontend/src/components/common/DemoModeConfirmPopover.test.tsx
git commit -m "feat(ui): add DemoModeConfirmPopover inline confirmation component"
```

---

## Task 3: Add i18n keys

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

- [ ] **Step 3.1: Add English keys**

In `frontend/src/locales/en.json`, add a top-level `"emptyStates"` section (place it alphabetically, e.g. after `"dashboard"`):

```json
"emptyStates": {
  "connectStep": {
    "title": "Connect",
    "description": "Add your bank or credit card accounts"
  },
  "scrapeStep": {
    "title": "Scrape",
    "description": "Import your transactions"
  },
  "analyseStep": {
    "title": "Analyse",
    "description": "See your full financial picture"
  },
  "dashboard": {
    "title": "No data yet",
    "description": "Connect your accounts to see your full financial picture."
  },
  "transactions": {
    "title": "No transactions yet",
    "description": "Connect your accounts to start importing your transactions."
  },
  "transactionsFiltered": {
    "title": "No transactions found",
    "description": "Try adjusting your filters."
  },
  "budget": {
    "title": "No budgets configured",
    "description": "Add a budget to start tracking your monthly spending."
  },
  "investments": {
    "title": "No active investments",
    "description": "Create your first investment to start tracking your portfolio."
  },
  "liabilities": {
    "title": "No liabilities tracked",
    "description": "Add a loan or debt to monitor what you owe."
  },
  "insurance": {
    "title": "No insurance data yet",
    "description": "Connect your insurance accounts to get started."
  },
  "connectAccounts": "Connect accounts",
  "tryDemoMode": "Try demo mode",
  "demoConfirmDescription": "Switches to sample data — your real data won't be affected.",
  "demoConfirmEnable": "Enable demo mode",
  "demoConfirmCancel": "Cancel"
},
```

- [ ] **Step 3.2: Add Hebrew keys**

In `frontend/src/locales/he.json`, add the matching section:

```json
"emptyStates": {
  "connectStep": {
    "title": "חיבור",
    "description": "הוסף את חשבון הבנק או כרטיס האשראי שלך"
  },
  "scrapeStep": {
    "title": "סריקה",
    "description": "ייבא את העסקאות שלך"
  },
  "analyseStep": {
    "title": "ניתוח",
    "description": "ראה את התמונה הפיננסית המלאה שלך"
  },
  "dashboard": {
    "title": "אין נתונים עדיין",
    "description": "חבר את חשבונותיך כדי לראות את התמונה הפיננסית המלאה שלך."
  },
  "transactions": {
    "title": "אין עסקאות עדיין",
    "description": "חבר את חשבונותיך כדי להתחיל לייבא עסקאות."
  },
  "transactionsFiltered": {
    "title": "לא נמצאו עסקאות",
    "description": "נסה לשנות את הסינון."
  },
  "budget": {
    "title": "לא הוגדרו תקציבים",
    "description": "הוסף תקציב כדי להתחיל לעקוב אחרי ההוצאות החודשיות שלך."
  },
  "investments": {
    "title": "אין השקעות פעילות",
    "description": "צור את ההשקעה הראשונה שלך כדי להתחיל לעקוב אחרי תיק ההשקעות שלך."
  },
  "liabilities": {
    "title": "לא עוקבים אחרי התחייבויות",
    "description": "הוסף הלוואה או חוב כדי לעקוב אחרי מה שאתה חייב."
  },
  "insurance": {
    "title": "אין נתוני ביטוח עדיין",
    "description": "חבר את חשבונות הביטוח שלך כדי להתחיל."
  },
  "connectAccounts": "חבר חשבונות",
  "tryDemoMode": "נסה מצב הדגמה",
  "demoConfirmDescription": "עובר לנתוני דוגמה — הנתונים האמיתיים שלך לא יושפעו.",
  "demoConfirmEnable": "הפעל מצב הדגמה",
  "demoConfirmCancel": "ביטול"
},
```

- [ ] **Step 3.3: Verify no missing keys**

```bash
cd frontend && npm run build 2>&1 | grep -i "i18n\|missing\|key" | head -20
# Should produce no i18n warnings
```

- [ ] **Step 3.4: Commit**

```bash
git add frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(i18n): add emptyStates translation keys (en + he)"
```

---

## Task 4: Dashboard — onboarding empty state

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

The Dashboard already fetches `allTransactions` (line ~268). When it is an empty array and not loading, the whole dashboard is empty. Show the onboarding variant instead of all the charts.

- [ ] **Step 4.1: Add imports at the top of `Dashboard.tsx`**

Add these imports to the existing import block:

```tsx
import { useState } from "react";                        // already present — skip if so
import { useNavigate } from "react-router-dom";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
```

`useState` is already imported; add only what is missing.

- [ ] **Step 4.2: Add `showDemoConfirm` state and `navigate` inside the main `Dashboard` component function**

Locate the `Dashboard` function (the default export at the bottom of the file). Add near the top of the function body (after the existing `useQuery` hooks):

```tsx
const navigate = useNavigate();
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 4.3: Add the empty-state guard before the main return**

Directly before the final `return (` in the `Dashboard` function, insert:

```tsx
const isDbEmpty =
  !transactionsLoading && (allTransactions?.length ?? 0) === 0;

if (isDbEmpty) {
  return (
    <EmptyState
      title={t("emptyStates.dashboard.title")}
      description={t("emptyStates.dashboard.description")}
      steps={[
        {
          title: t("emptyStates.connectStep.title"),
          description: t("emptyStates.connectStep.description"),
        },
        {
          title: t("emptyStates.scrapeStep.title"),
          description: t("emptyStates.scrapeStep.description"),
        },
        {
          title: t("emptyStates.analyseStep.title"),
          description: t("emptyStates.analyseStep.description"),
        },
      ]}
      cta={{
        label: t("emptyStates.connectAccounts"),
        onClick: () => navigate("/data-sources"),
      }}
      secondary={{
        label: t("emptyStates.tryDemoMode"),
        onClick: () => setShowDemoConfirm(true),
      }}
      footer={
        showDemoConfirm ? (
          <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
        ) : undefined
      }
    />
  );
}
```

- [ ] **Step 4.4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4.5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(dashboard): show onboarding empty state when database is empty"
```

---

## Task 5: Transactions — onboarding empty state

**Files:**
- Modify: `frontend/src/pages/Transactions.tsx`

The `transactions` query already fetches all transactions when `selectedService === "all"`. If it returns an empty array on the "all" tab with no loading, the DB is empty — show the onboarding EmptyState instead of the table.

- [ ] **Step 5.1: Add imports**

Add to the existing imports in `Transactions.tsx`:

```tsx
import { useNavigate } from "react-router-dom";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
```

- [ ] **Step 5.2: Add state and navigate**

Inside the `Transactions` component function, after the existing `useState` declarations, add:

```tsx
const navigate = useNavigate();
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 5.3: Add the onboarding guard**

Locate the block inside the JSX that renders the table content (currently around line 338 — the `bg-[var(--surface)] rounded-xl` card). Inside the card, after the `isLoading` skeleton branch and before the `<TransactionsTable .../>`, insert a check. The structure should become:

```tsx
{selectedService === "refunds" ? (
  <RefundsView />
) : isLoading ? (
  <div className="p-8 space-y-4">
    <Skeleton variant="text" lines={1} className="w-48" />
    <Skeleton variant="card" className="h-64" />
  </div>
) : selectedService === "all" && (transactions?.length ?? 0) === 0 ? (
  <EmptyState
    title={t("emptyStates.transactions.title")}
    description={t("emptyStates.transactions.description")}
    steps={[
      {
        title: t("emptyStates.connectStep.title"),
        description: t("emptyStates.connectStep.description"),
      },
      {
        title: t("emptyStates.scrapeStep.title"),
        description: t("emptyStates.scrapeStep.description"),
      },
      {
        title: t("emptyStates.analyseStep.title"),
        description: t("emptyStates.analyseStep.description"),
      },
    ]}
    cta={{
      label: t("emptyStates.connectAccounts"),
      onClick: () => navigate("/data-sources"),
    }}
    secondary={{
      label: t("emptyStates.tryDemoMode"),
      onClick: () => setShowDemoConfirm(true),
    }}
    footer={
      showDemoConfirm ? (
        <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
      ) : undefined
    }
  />
) : (
  <>
    {selectedService === "cash" && <CashBalancesCard queryClient={queryClient} />}
    {/* ... rest of existing JSX (uncategorized banner + TransactionsTable) ... */}
  </>
)}
```

Keep all existing JSX inside the final `<>` block unchanged.

- [ ] **Step 5.4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 5.5: Commit**

```bash
git add frontend/src/pages/Transactions.tsx
git commit -m "feat(transactions): show onboarding empty state when no transactions exist"
```

---

## Task 6: Budget — empty state for no budget rules

**Files:**
- Modify: `frontend/src/components/budget/MonthlyBudgetView.tsx`

`MonthlyBudgetView` already has `budgetRules` (derived from the API's `rules` array) and `setIsRuleModalOpen`. When `budgetRules.length === 0`, render an `EmptyState` pointing to the add-budget modal.

- [ ] **Step 6.1: Add imports**

Add to the existing imports in `MonthlyBudgetView.tsx`:

```tsx
import { useState } from "react";   // already present — skip if so
import { EmptyState } from "../common/EmptyState";
import { DemoModeConfirmPopover } from "../common/DemoModeConfirmPopover";
```

- [ ] **Step 6.2: Add `showDemoConfirm` state**

Inside the `MonthlyBudgetView` component function, after existing `useState` declarations, add:

```tsx
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 6.3: Insert the empty-state block**

Find the `{/* Budget Rules */}` comment (around line 417). Directly before the `<div className="space-y-4">` that renders the rules list, insert:

```tsx
{budgetRules.length === 0 && (
  <EmptyState
    title={t("emptyStates.budget.title")}
    description={t("emptyStates.budget.description")}
    cta={{
      label: t("budget.addRule"),
      onClick: () => setIsRuleModalOpen(true),
    }}
    secondary={{
      label: t("emptyStates.tryDemoMode"),
      onClick: () => setShowDemoConfirm(true),
    }}
    footer={
      showDemoConfirm ? (
        <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
      ) : undefined
    }
  />
)}
```

Note: `t("budget.addRule")` already exists in the locale files. Verify with:
```bash
grep '"addRule"' frontend/src/locales/en.json
```
If the key is missing, use `t("common.add")` instead and add `"addRule": "Add rule"` to both locale files.

- [ ] **Step 6.4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 6.5: Commit**

```bash
git add frontend/src/components/budget/MonthlyBudgetView.tsx
git commit -m "feat(budget): show empty state when no budget rules are configured"
```

---

## Task 7: Investments — remove icon, add demo mode secondary

**Files:**
- Modify: `frontend/src/pages/Investments.tsx`

The existing `EmptyState` at line ~582 has `icon={TrendingUp}`. Remove the icon and add the demo mode secondary button. Only the "normal" case (categories exist) gets the demo mode button; the "no tags" case keeps its categories CTA as the sole action.

- [ ] **Step 7.1: Add imports**

Add to existing imports in `Investments.tsx`:

```tsx
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
```

- [ ] **Step 7.2: Add `showDemoConfirm` state**

Inside `Investments`, after existing `useState` declarations, add:

```tsx
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 7.3: Update the `EmptyState` call**

Locate the `EmptyState` at line ~582. Replace it with:

```tsx
<EmptyState
  title={
    Object.keys(filteredCategories).length === 0
      ? t("investments.noActiveInvestments")
      : t("emptyStates.investments.title")
  }
  description={
    Object.keys(filteredCategories).length === 0
      ? t("investments.noTagsAvailable")
      : t("emptyStates.investments.description")
  }
  cta={
    Object.keys(filteredCategories).length === 0
      ? {
          label: t("sidebar.categories"),
          onClick: () => navigate("/categories"),
        }
      : {
          label: t("investments.addFirstInvestment"),
          onClick: () => setIsAddOpen(true),
        }
  }
  secondary={
    Object.keys(filteredCategories).length > 0
      ? {
          label: t("emptyStates.tryDemoMode"),
          onClick: () => setShowDemoConfirm(true),
        }
      : undefined
  }
  footer={
    showDemoConfirm ? (
      <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
    ) : undefined
  }
/>
```

- [ ] **Step 7.4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 7.5: Commit**

```bash
git add frontend/src/pages/Investments.tsx
git commit -m "feat(investments): remove icon from empty state, add demo mode secondary"
```

---

## Task 8: Liabilities — remove icon, add demo mode secondary

**Files:**
- Modify: `frontend/src/pages/Liabilities.tsx`

The existing `EmptyState` at line ~671 has `icon={Landmark}`. Remove it and add the demo mode secondary.

- [ ] **Step 8.1: Add imports**

```tsx
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
```

- [ ] **Step 8.2: Add `showDemoConfirm` state**

```tsx
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 8.3: Update the `EmptyState` call**

Replace the `EmptyState` at line ~671:

```tsx
<EmptyState
  title={t("emptyStates.liabilities.title")}
  description={t("emptyStates.liabilities.description")}
  cta={{
    label: t("liabilities.addFirstLiability"),
    onClick: () => setIsAddOpen(true),
  }}
  secondary={{
    label: t("emptyStates.tryDemoMode"),
    onClick: () => setShowDemoConfirm(true),
  }}
  footer={
    showDemoConfirm ? (
      <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
    ) : undefined
  }
/>
```

- [ ] **Step 8.4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

- [ ] **Step 8.5: Commit**

```bash
git add frontend/src/pages/Liabilities.tsx
git commit -m "feat(liabilities): remove icon from empty state, add demo mode secondary"
```

---

## Task 9: Insurances — replace ad-hoc empty div with `EmptyState`

**Files:**
- Modify: `frontend/src/pages/Insurances.tsx`

The current empty state at line ~515 is a custom `div` with an icon and two paragraphs. Replace it with the `EmptyState` component. Insurance data comes from scraping, so the CTA navigates to Data Sources. No 3-step flow (single CTA is sufficient).

- [ ] **Step 9.1: Add imports**

```tsx
import { useNavigate } from "react-router-dom";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
```

- [ ] **Step 9.2: Add state and navigate**

Inside the `Insurances` component, add:

```tsx
const navigate = useNavigate();
const [showDemoConfirm, setShowDemoConfirm] = useState(false);
```

- [ ] **Step 9.3: Replace the ad-hoc empty div**

Find (line ~515):

```tsx
if (accounts.length === 0) {
  return (
    <div className="flex flex-col items-center justify-center h-96 text-[var(--text-muted)] gap-4">
      <Shield size={48} className="opacity-30" />
      <p className="text-lg">{t("insurance.noAccountsFound")}</p>
      <p className="text-sm">{t("insurance.scrapeToGetStarted")}</p>
    </div>
  );
}
```

Replace with:

```tsx
if (accounts.length === 0) {
  return (
    <EmptyState
      title={t("emptyStates.insurance.title")}
      description={t("emptyStates.insurance.description")}
      cta={{
        label: t("emptyStates.connectAccounts"),
        onClick: () => navigate("/data-sources"),
      }}
      secondary={{
        label: t("emptyStates.tryDemoMode"),
        onClick: () => setShowDemoConfirm(true),
      }}
      footer={
        showDemoConfirm ? (
          <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
        ) : undefined
      }
    />
  );
}
```

`Shield` can now be removed from the lucide imports if it is no longer used elsewhere in the file. Check with:
```bash
grep -n "Shield" frontend/src/pages/Insurances.tsx
```

- [ ] **Step 9.4: Verify TypeScript compiles and tests pass**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30 && npm test -- --run 2>&1 | tail -20
```

Expected: no type errors, all tests pass.

- [ ] **Step 9.5: Commit**

```bash
git add frontend/src/pages/Insurances.tsx
git commit -m "feat(insurance): replace ad-hoc empty div with EmptyState component"
```

---

## Final Check

- [ ] **Run the full test suite**

```bash
cd frontend && npm test -- --run
```

Expected: all tests pass, no regressions.

- [ ] **TypeScript full check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors.
