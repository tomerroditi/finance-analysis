# Dashboard Bank-Balance Update Chip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user update a bank account's balance from the dashboard via a small "$" update chip on each account row in the expanded Total Bank Balance KPI card, using a shared modal that also replaces the inline balance editor on the DataSources page.

**Architecture:** A new self-contained `UpdateBankBalanceModal` owns its own `setBalance` mutation. It is rendered from two call sites: the dashboard `FinancialHealthHeader` (opened by a per-account amber chip) and the DataSources page (opened by the existing amber "$" button, replacing the current inline `<input>` editor). Both sites compute `isScrapedToday` from the existing `scrapingApi.getLastScrapes()` query to gate the trigger; the modal also guards internally.

**Tech Stack:** React 19, TypeScript (strict), TanStack Query, Tailwind CSS 4, i18next (en + he), Vitest + @testing-library/react (component tests), Playwright (e2e).

## Global Constraints

- All user-visible strings go through `t("section.key")`; add every new key to **both** `frontend/src/locales/en.json` and `frontend/src/locales/he.json` (Hebrew hand-translated). — `.claude/rules/frontend_i18n_checklist.md`
- Currency only via `formatCurrency()` from `utils/numberFormatting.ts`; never inline `Intl.NumberFormat`; never prepend `₪`. Helper output is bidi-stable — no `dir="ltr"` needed for a bare `formatCurrency()` span. — `.claude/rules/frontend_pitfalls.md`
- User-data text in a `truncate` element needs `dir="auto"`; translated chrome does not. — `.claude/rules/frontend_i18n.md`
- All React hooks must be called before any early `return`. — `.claude/rules/frontend_pitfalls.md`
- Use the shared `Modal` from `components/common/Modal.tsx` (it handles overlay, close button, `useScrollLock`, a11y). Do not hand-roll a modal.
- Mutations: narrow `invalidateQueries({ queryKey: [...] })` only — never argless `invalidateQueries()`. The bank-balances query key is `["bank-balances", isDemoMode]`; invalidating the prefix `["bank-balances"]` matches it. — `.claude/rules/frontend_components.md`
- Backend precondition (already enforced): `POST /bank-balances/` (trailing slash) rejects with HTTP 400 unless the `(provider, account_name)` account was scraped **today**. Balance update payload is exactly `{ provider, account_name, balance }` — no id, no currency (single-currency ILS).
- No new API endpoints → no PWA/service-worker/persister changes. — `.claude/rules/frontend_pwa.md`
- TypeScript strict: no unused locals/parameters (removing code may strand imports — the `tsc -b` build will flag them).

---

## File Structure

- **Create** `frontend/src/components/modals/UpdateBankBalanceModal.tsx` — the shared modal (owns the `setBalance` mutation, explanation copy, internal not-scraped guard).
- **Create** `frontend/src/components/modals/UpdateBankBalanceModal.test.tsx` — Vitest component test.
- **Modify** `frontend/src/locales/en.json` + `frontend/src/locales/he.json` — add the `bankBalance.*` section.
- **Modify** `frontend/src/pages/DataSources.tsx` — replace the inline balance editor with the shared modal; remove now-dead state/mutation/imports.
- **Modify** `frontend/src/pages/Dashboard.tsx` — add a `last-scrapes` query, thread it into `FinancialHealthHeader`, render a bank-specific breakdown with the chip, and mount the modal.
- **Create** `frontend/e2e/bank-balance-update-chip.spec.ts` — dashboard chip e2e (route-stubbed, deterministic).
- **Modify** `frontend/e2e/data-sources.spec.ts` — add a test that opens the shared modal from the DataSources "$" button and saves.

---

### Task 1: Shared `UpdateBankBalanceModal` component + i18n

**Files:**
- Create: `frontend/src/components/modals/UpdateBankBalanceModal.tsx`
- Create: `frontend/src/components/modals/UpdateBankBalanceModal.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/he.json`

**Interfaces:**
- Consumes: `bankBalancesApi.setBalance(data: { provider: string; account_name: string; balance: number })` and the shared `Modal` from `../common/Modal`.
- Produces: `export function UpdateBankBalanceModal(props: { isOpen: boolean; onClose: () => void; provider: string; accountName: string; currentBalance: number | null; isScrapedToday: boolean })`. Tasks 2 and 3 import this.

- [ ] **Step 1: Add the `bankBalance.*` i18n block to `en.json`**

Insert this key (as a new top-level section — sibling of `dashboard`/`dataSources`; JSON key order does not matter) into `frontend/src/locales/en.json`:

```json
"bankBalance": {
  "title": "Update Balance",
  "explanation": "Enter the current balance shown in your bank. We combine it with your scraped transactions to compute your starting (prior) wealth, keeping your net worth accurate. The account must be scraped today first so the calculation uses up-to-date transactions.",
  "scrapeNote": "Scrape this account today first, then set its balance.",
  "balanceLabel": "Current balance",
  "placeholder": "Enter balance…",
  "current": "Currently",
  "failed": "Failed to set balance."
}
```

- [ ] **Step 2: Add the matching `bankBalance.*` block to `he.json`**

Insert into `frontend/src/locales/he.json` (hand-translated):

```json
"bankBalance": {
  "title": "עדכון יתרה",
  "explanation": "הזינו את היתרה הנוכחית המוצגת בבנק. אנו משלבים אותה עם התנועות שנסרקו כדי לחשב את ההון ההתחלתי שלכם, כך שהשווי הנקי נשאר מדויק. יש לסרוק את החשבון היום תחילה כדי שהחישוב יתבסס על תנועות מעודכנות.",
  "scrapeNote": "סרקו את החשבון היום תחילה, ולאחר מכן הגדירו את היתרה.",
  "balanceLabel": "יתרה נוכחית",
  "placeholder": "הזינו יתרה…",
  "current": "כעת",
  "failed": "הגדרת היתרה נכשלה."
}
```

- [ ] **Step 3: Write the failing component test**

Create `frontend/src/components/modals/UpdateBankBalanceModal.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { UpdateBankBalanceModal } from "./UpdateBankBalanceModal";
import { bankBalancesApi } from "../../services/api";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    bankBalancesApi: { ...actual.bankBalancesApi, setBalance: vi.fn() },
  };
});

describe("UpdateBankBalanceModal", () => {
  const baseProps = {
    isOpen: true,
    onClose: vi.fn(),
    provider: "hapoalim",
    accountName: "My Checking",
    currentBalance: 1234,
    isScrapedToday: true,
  };

  beforeEach(() => vi.clearAllMocks());

  it("shows the explanation, account name, and an enabled Save when scraped today", () => {
    renderWithProviders(<UpdateBankBalanceModal {...baseProps} />);
    expect(screen.getByText("My Checking")).toBeInTheDocument();
    expect(screen.getByText(/net worth/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Save$/ })).toBeEnabled();
  });

  it("submits provider, account_name, and parsed balance on Save", async () => {
    vi.mocked(bankBalancesApi.setBalance).mockResolvedValue({ data: {} } as never);
    const user = userEvent.setup();
    renderWithProviders(<UpdateBankBalanceModal {...baseProps} />);
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "5000");
    await user.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() =>
      expect(bankBalancesApi.setBalance).toHaveBeenCalledWith({
        provider: "hapoalim",
        account_name: "My Checking",
        balance: 5000,
      }),
    );
  });

  it("disables the input and Save and shows a scrape-first note when not scraped today", () => {
    renderWithProviders(
      <UpdateBankBalanceModal {...baseProps} isScrapedToday={false} />,
    );
    expect(screen.getByRole("spinbutton")).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Save$/ })).toBeDisabled();
    expect(screen.getByText(/then set its balance/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `cd frontend && npm test -- --run src/components/modals/UpdateBankBalanceModal.test.tsx`
Expected: FAIL — cannot resolve `./UpdateBankBalanceModal` (module not created yet).

- [ ] **Step 5: Implement the modal**

Create `frontend/src/components/modals/UpdateBankBalanceModal.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign } from "lucide-react";
import { Modal } from "../common/Modal";
import { bankBalancesApi } from "../../services/api";
import { useNotify } from "../../context/DialogContext";
import { humanizeProvider } from "../../utils/textFormatting";
import { formatCurrency } from "../../utils/numberFormatting";

interface UpdateBankBalanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider: string;
  accountName: string;
  currentBalance: number | null;
  isScrapedToday: boolean;
}

export function UpdateBankBalanceModal({
  isOpen,
  onClose,
  provider,
  accountName,
  currentBalance,
  isScrapedToday,
}: UpdateBankBalanceModalProps) {
  const { t } = useTranslation();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");

  // Re-seed the input whenever the modal (re)opens for a possibly different account.
  useEffect(() => {
    if (isOpen) setValue(currentBalance != null ? String(currentBalance) : "");
  }, [isOpen, currentBalance]);

  const mutation = useMutation({
    mutationFn: bankBalancesApi.setBalance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
      queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
      onClose();
    },
    onError: (error: unknown) => {
      const axiosErr = error as { response?: { data?: { detail?: string } } };
      notify.error(axiosErr.response?.data?.detail || t("bankBalance.failed"));
    },
  });

  const canSave = isScrapedToday && value.trim() !== "" && !mutation.isPending;

  const submit = () => {
    if (!canSave) return;
    mutation.mutate({
      provider,
      account_name: accountName,
      balance: parseFloat(value),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("bankBalance.title")}
      titleIcon={<DollarSign size={20} className="text-amber-400" />}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="text-[var(--text-muted)]">{humanizeProvider(provider)}</span>
          <span className="font-medium text-white truncate" dir="auto">{accountName}</span>
        </div>

        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          {t("bankBalance.explanation")}
        </p>

        {!isScrapedToday && (
          <p className="text-xs text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2">
            {t("bankBalance.scrapeNote")}
          </p>
        )}

        <div className="space-y-1">
          <label htmlFor="bank-balance-input" className="text-xs text-[var(--text-muted)]">
            {t("bankBalance.balanceLabel")}
          </label>
          <input
            id="bank-balance-input"
            type="number"
            value={value}
            disabled={!isScrapedToday}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder={t("bankBalance.placeholder")}
            autoFocus
            className="w-full px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--surface-light)] text-white text-sm focus:outline-none focus:border-[var(--primary)] disabled:opacity-50 disabled:cursor-not-allowed"
          />
          {currentBalance != null && (
            <p className="text-[11px] text-[var(--text-muted)]">
              {t("bankBalance.current")}: {formatCurrency(currentBalance)}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={submit}
            disabled={!canSave}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-amber-500/90 text-black hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd frontend && npm test -- --run src/components/modals/UpdateBankBalanceModal.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 7: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/modals/UpdateBankBalanceModal.tsx frontend/src/components/modals/UpdateBankBalanceModal.test.tsx frontend/src/locales/en.json frontend/src/locales/he.json
git commit -m "feat(frontend): add shared UpdateBankBalanceModal + bankBalance i18n"
```

---

### Task 2: Replace the DataSources inline balance editor with the shared modal

**Files:**
- Modify: `frontend/src/pages/DataSources.tsx`
- Modify: `frontend/e2e/data-sources.spec.ts`

**Interfaces:**
- Consumes: `UpdateBankBalanceModal` (Task 1); existing `isScrapedToday(provider, accountName)` and `getAccountBalance(provider, accountName)` helpers already in `DataSources.tsx`.
- Produces: no new exports.

- [ ] **Step 1: Write the failing e2e test**

Add this block to `frontend/e2e/data-sources.spec.ts`. Put the `import` additions at the top (merge with the existing import from `./helpers`; add `request` from `@playwright/test`) and the `test(...)` inside the existing `test.describe("DataSources", ...)`.

```ts
// --- add to the top-of-file imports ---
import { test, expect, request } from "@playwright/test";

// --- add inside test.describe("DataSources", () => { ... }) ---
test("opens the shared balance modal from the $ button and saves", async ({ page }) => {
  const API_BASE = "http://localhost:8000/api";
  const provider = "onezero";
  const accountName = "E2E Balance Bank";
  const today = new Date().toISOString();

  // Seed a throwaway bank credential so a bank row (with the $ button) renders.
  const ctx = await request.newContext();
  await ctx.post(`${API_BASE}/credentials/`, {
    data: {
      service: "banks",
      provider,
      account_name: accountName,
      credentials: {
        email: "e2e-balance@example.com",
        password: "e2e-password",
        phoneNumber: "+15551234567",
      },
    },
  });
  await ctx.dispose();

  try {
    // Deterministic scrape status + balance for the seeded account.
    await page.route("**/api/scraping/last-scrapes", async (route) => {
      await route.fulfill({
        json: [
          { service: "banks", provider, account_name: accountName, last_scrape_date: today },
        ],
      });
    });
    await page.route("**/api/bank-balances/", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: [
            {
              id: 99,
              provider,
              account_name: accountName,
              balance: 1000,
              prior_wealth_amount: 0,
              last_manual_update: null,
              last_scrape_update: today,
            },
          ],
        });
      } else {
        await route.fulfill({
          json: {
            id: 99,
            provider,
            account_name: accountName,
            balance: 7777,
            prior_wealth_amount: 0,
            last_manual_update: today,
            last_scrape_update: today,
          },
        });
      }
    });

    await page.goto("/");
    await page.evaluate(() =>
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now())),
    );
    await page.goto("/data-sources");
    await page.waitForLoadState("networkidle");

    // The seeded bank row's amber "$" button (enabled because scraped today).
    const setBtn = page.getByRole("button", { name: /^Set Balance$/ }).first();
    await expect(setBtn).toBeEnabled();
    await setBtn.click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/net worth/i)).toBeVisible();

    const [req] = await Promise.all([
      page.waitForRequest(
        (r) => r.url().includes("/api/bank-balances/") && r.method() === "POST",
      ),
      (async () => {
        await dialog.getByRole("spinbutton").fill("7777");
        await dialog.getByRole("button", { name: /^Save$/ }).click();
      })(),
    ]);
    expect(req.postDataJSON()).toEqual({ provider, account_name: accountName, balance: 7777 });
    await expect(dialog).toBeHidden();
  } finally {
    const cleanup = await request.newContext();
    await cleanup.delete(
      `${API_BASE}/credentials/banks/${provider}/${encodeURIComponent(accountName)}`,
    );
    await cleanup.dispose();
  }
});
```

- [ ] **Step 2: Run the e2e to verify it fails**

Run (starts both servers, runs one spec):
`python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/data-sources.spec.ts -g 'shared balance modal'"`
Expected: FAIL — clicking `$` opens the old inline `<input>`, not a `role="dialog"`; `getByRole("dialog")` times out.

- [ ] **Step 3: Import the modal and add modal state in `DataSources.tsx`**

At the top of `frontend/src/pages/DataSources.tsx`, add the import (next to the other component imports):

```tsx
import { UpdateBankBalanceModal } from "../components/modals/UpdateBankBalanceModal";
```

Replace the two inline-editor state declarations at lines 173–174:

```tsx
  const [editingBalance, setEditingBalance] = useState<string | null>(null);
  const [balanceInput, setBalanceInput] = useState("");
```

with a single modal-target state:

```tsx
  const [balanceModalAccount, setBalanceModalAccount] = useState<
    { provider: string; account_name: string; balance: number | null } | null
  >(null);
```

- [ ] **Step 4: Remove the now-dead mutation and `notify`**

Delete the entire `setBalanceMutation` block (lines 158–171). Delete `const notify = useNotify();` (line 69). Update the DialogContext import (line 37) from `import { useConfirm, useNotify } from "../context/DialogContext";` to:

```tsx
import { useConfirm } from "../context/DialogContext";
```

Remove `Check` from the `lucide-react` import list (it is only used by the inline editor being deleted). Leave `X` and `DollarSign` (still used elsewhere / by the new button).

- [ ] **Step 5: Replace the inline-editor IIFE with a modal trigger**

Replace the whole `acc.service === "banks" && (() => { ... })()` block (lines 370–469 — the version with `isEditing`, the number `<input>`, and the Check/X buttons) with:

```tsx
{acc.service === "banks" &&
  (() => {
    const bal = getAccountBalance(acc.provider, acc.account_name);
    const canSetBalance = isScrapedToday(acc.provider, acc.account_name);
    return (
      <div className="flex items-center gap-2">
        {bal ? (
          <span className="text-sm font-semibold text-amber-400">
            {formatCurrency(bal.balance)}
          </span>
        ) : (
          <span className="text-xs text-[var(--text-muted)] italic">
            {t("dataSources.noBalanceSet")}
          </span>
        )}
        <button
          onClick={() =>
            setBalanceModalAccount({
              provider: acc.provider,
              account_name: acc.account_name,
              balance: bal ? bal.balance : null,
            })
          }
          disabled={!canSetBalance}
          className={`p-1.5 rounded-lg transition-all ${
            canSetBalance
              ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
              : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
          }`}
          title={
            canSetBalance
              ? t("dataSources.setBalance")
              : t("dataSources.scrapeFirstToSetBalance")
          }
        >
          <DollarSign size={16} />
        </button>
      </div>
    );
  })()}
```

- [ ] **Step 6: Mount the modal**

Find where the page renders its other modals (search for `isAddOpen &&` in `DataSources.tsx`) and add the shared modal as a sibling, just before the final closing tag of the component's returned JSX:

```tsx
<UpdateBankBalanceModal
  isOpen={balanceModalAccount !== null}
  onClose={() => setBalanceModalAccount(null)}
  provider={balanceModalAccount?.provider ?? ""}
  accountName={balanceModalAccount?.account_name ?? ""}
  currentBalance={balanceModalAccount?.balance ?? null}
  isScrapedToday={
    balanceModalAccount
      ? isScrapedToday(balanceModalAccount.provider, balanceModalAccount.account_name)
      : false
  }
/>
```

- [ ] **Step 7: Type-check (catches any stranded import/var)**

Run: `cd frontend && npx tsc -b`
Expected: no errors. If `tsc` reports an unused `X` or other symbol, remove it.

- [ ] **Step 8: Run the e2e to verify it passes**

Run: `python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/data-sources.spec.ts"`
Expected: PASS (existing DataSources tests + the new "shared balance modal" test).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/DataSources.tsx frontend/e2e/data-sources.spec.ts
git commit -m "refactor(datasources): use shared UpdateBankBalanceModal instead of inline editor"
```

---

### Task 3: Dashboard KPI-card update chip + modal

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Create: `frontend/e2e/bank-balance-update-chip.spec.ts`

**Interfaces:**
- Consumes: `UpdateBankBalanceModal` (Task 1); `scrapingApi.getLastScrapes()` and its row type `{ service: string; provider: string; account_name: string; last_scrape_date: string | null }`; existing `BankBalance` type.
- Produces: no new exports.

- [ ] **Step 1: Write the failing dashboard e2e**

Create `frontend/e2e/bank-balance-update-chip.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

test.describe("Dashboard bank-balance update chip", () => {
  test.beforeAll(async () => {
    await enableDemoMode();
  });
  test.afterAll(async () => {
    await disableDemoMode();
  });

  test.beforeEach(async ({ page }) => {
    const today = new Date().toISOString();
    await page.route("**/api/bank-balances/", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          json: [
            { id: 1, provider: "hapoalim", account_name: "Fresh Checking", balance: 1000, prior_wealth_amount: 0, last_manual_update: null, last_scrape_update: today },
            { id: 2, provider: "leumi", account_name: "Stale Savings", balance: 2000, prior_wealth_amount: 0, last_manual_update: null, last_scrape_update: null },
          ],
        });
      } else {
        await route.fulfill({
          json: { id: 1, provider: "hapoalim", account_name: "Fresh Checking", balance: 4242, prior_wealth_amount: 0, last_manual_update: today, last_scrape_update: today },
        });
      }
    });
    await page.route("**/api/scraping/last-scrapes", async (route) => {
      await route.fulfill({
        json: [
          { service: "banks", provider: "hapoalim", account_name: "Fresh Checking", last_scrape_date: today },
          { service: "banks", provider: "leumi", account_name: "Stale Savings", last_scrape_date: "2020-01-01T00:00:00" },
        ],
      });
    });
    await page.goto("/");
    await page.evaluate(() =>
      sessionStorage.setItem("onboardingDismissedAt", String(Date.now())),
    );
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("shows an update chip per account; disabled when not scraped today", async ({ page }) => {
    await page.getByText("Bank Balance", { exact: true }).click(); // expand KPI header
    await expect(page.getByText("Fresh Checking")).toBeVisible();
    await expect(page.getByText("Stale Savings")).toBeVisible();
    const staleChip = page.getByRole("button", {
      name: /scrape first to set balance/i,
    });
    await expect(staleChip).toBeVisible();
    await expect(staleChip).toBeDisabled();
  });

  test("opens the modal, saves a balance, and keeps the card expanded", async ({ page }) => {
    await page.getByText("Bank Balance", { exact: true }).click();
    await expect(page.getByText("Fresh Checking")).toBeVisible();

    await page.getByRole("button", { name: /^Set Balance$/ }).first().click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/net worth/i)).toBeVisible();
    // stopPropagation worked — the breakdown is still expanded behind the modal.
    await expect(page.getByText("Fresh Checking")).toBeVisible();

    const [req] = await Promise.all([
      page.waitForRequest(
        (r) => r.url().includes("/api/bank-balances/") && r.method() === "POST",
      ),
      (async () => {
        await dialog.getByRole("spinbutton").fill("4242");
        await dialog.getByRole("button", { name: /^Save$/ }).click();
      })(),
    ]);
    expect(req.postDataJSON()).toEqual({
      provider: "hapoalim",
      account_name: "Fresh Checking",
      balance: 4242,
    });
    await expect(dialog).toBeHidden();
  });
});
```

- [ ] **Step 2: Run the e2e to verify it fails**

Run: `python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/bank-balance-update-chip.spec.ts"`
Expected: FAIL — no `Set Balance` / `scrape first` chip exists in the dashboard breakdown yet.

- [ ] **Step 3: Add imports + the `last-scrapes` query in `Dashboard.tsx`**

Add to the `services/api` import (line 4–12 block) so it includes `scrapingApi`; add the `DollarSign` icon and the modal import near the other imports:

```tsx
import { DollarSign } from "lucide-react";
import { UpdateBankBalanceModal } from "../components/modals/UpdateBankBalanceModal";
```

(For `scrapingApi`: add it to the existing `import { analyticsApi, cashBalancesApi, bankBalancesApi, investmentsApi, transactionsApi, taggingApi, type BankBalance } from "../services/api";` line.)

Inside `export function Dashboard()`, after the existing `bankBalances` query (around line 248), add:

```tsx
  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes", isDemoMode],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
  });
```

- [ ] **Step 4: Pass `lastScrapes` into `FinancialHealthHeader`**

At the render site (line 346), add the prop:

```tsx
      <FinancialHealthHeader
        netWorthData={netWorthData}
        cashBalances={cashBalances}
        bankBalances={bankBalances}
        portfolioAllocation={portfolioData?.allocation}
        lastScrapes={lastScrapes}
        isLoading={netWorthLoading}
      />
```

- [ ] **Step 5: Extend the `FinancialHealthHeader` signature + add scrape/modal logic**

Update the component's prop type (lines 97–111) to add `lastScrapes`:

```tsx
function FinancialHealthHeader({
  netWorthData,
  cashBalances,
  bankBalances,
  portfolioAllocation,
  lastScrapes,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]
    | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  bankBalances: BankBalance[] | undefined;
  portfolioAllocation: { name: string; balance: number }[] | undefined;
  lastScrapes:
    | { service: string; provider: string; account_name: string; last_scrape_date: string | null }[]
    | undefined;
  isLoading: boolean;
}) {
```

Immediately after `const [expanded, setExpanded] = useState(false);` (line 113), add the modal state and the scrape helper (all hooks/consts before the existing early `return` on `isLoading`):

```tsx
  const [balanceModalAccount, setBalanceModalAccount] = useState<
    { provider: string; account_name: string; balance: number } | null
  >(null);

  const isScrapedToday = (provider: string, accountName: string): boolean => {
    const scrape = lastScrapes?.find(
      (s) => s.provider === provider && s.account_name === accountName,
    );
    if (!scrape?.last_scrape_date) return false;
    const d = new Date(scrape.last_scrape_date);
    const now = new Date();
    return (
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    );
  };
```

- [ ] **Step 6: Replace the bank breakdown with a chip-bearing list**

In the Bank Balance card, replace the breakdown block (lines 190–194):

```tsx
        {expanded && bankBalances && bankBalances.length > 0 && (
          <BreakdownList
            items={bankBalances.map((b) => ({ name: b.account_name, amount: b.balance }))}
          />
        )}
```

with a bank-specific list that carries `provider` and renders the update chip:

```tsx
        {expanded && bankBalances && bankBalances.length > 0 && (
          <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
            {bankBalances.map((b) => {
              const canUpdate = isScrapedToday(b.provider, b.account_name);
              return (
                <div
                  key={`${b.provider}|${b.account_name}`}
                  className="flex items-center justify-between text-xs gap-2"
                >
                  <span className="text-[var(--text-muted)] truncate me-1" dir="auto">
                    {b.account_name}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="tabular-nums font-medium">{formatCurrency(b.balance)}</span>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (canUpdate) {
                          setBalanceModalAccount({
                            provider: b.provider,
                            account_name: b.account_name,
                            balance: b.balance,
                          });
                        }
                      }}
                      disabled={!canUpdate}
                      aria-label={t("dataSources.setBalance")}
                      title={
                        canUpdate
                          ? t("dataSources.setBalance")
                          : t("dataSources.scrapeFirstToSetBalance")
                      }
                      className={`p-1 rounded-md transition-all ${
                        canUpdate
                          ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                          : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
                      }`}
                    >
                      <DollarSign size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
```

- [ ] **Step 7: Wrap the return in a fragment and mount the modal as a sibling of the grid**

The modal must be a sibling of the clickable grid (not a descendant) so clicks inside the modal don't bubble to the grid's `onClick` toggle. Change the component's `return (` (line 166) so the grid `<div>...</div>` and the modal are both children of a `<>` fragment. Immediately after the grid's closing `</div>` (line 223), add:

```tsx
      <UpdateBankBalanceModal
        isOpen={balanceModalAccount !== null}
        onClose={() => setBalanceModalAccount(null)}
        provider={balanceModalAccount?.provider ?? ""}
        accountName={balanceModalAccount?.account_name ?? ""}
        currentBalance={balanceModalAccount?.balance ?? null}
        isScrapedToday={
          balanceModalAccount
            ? isScrapedToday(balanceModalAccount.provider, balanceModalAccount.account_name)
            : false
        }
      />
```

So the structure becomes:

```tsx
  return (
    <>
      <div
        className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 cursor-pointer"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* ...four cards unchanged... */}
      </div>
      <UpdateBankBalanceModal ... />
    </>
  );
```

- [ ] **Step 8: Type-check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 9: Run the dashboard e2e to verify it passes**

Run: `python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/bank-balance-update-chip.spec.ts"`
Expected: PASS (2 tests).

- [ ] **Step 10: Manual Playwright-MCP walkthrough (required for UI patches)**

Per `CLAUDE.md`, drive the real flow (not stubbed) once. With Demo Mode enabled and both servers running (`python .claude/scripts/with_server.py -- sleep 600` or the running dev servers), use the Playwright MCP to: open `/`, click the Bank Balance card to expand, confirm each demo bank account shows a "$" chip. To exercise the enabled path, first run a demo scrape of a bank account from `/data-sources` (demo scrapers generate data instantly; one scrape per account per day), return to `/`, confirm that account's chip is now enabled, click it, verify the modal shows the explanation, enter a balance, Save, and confirm the modal closes and the breakdown/headline refresh. Note any focus/scroll/RTL issues and fix before committing. (Re-enable then disable Demo Mode as needed; toggling re-copies the frozen demo snapshot.)

- [ ] **Step 11: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/e2e/bank-balance-update-chip.spec.ts
git commit -m "feat(dashboard): update-balance chip on the bank KPI card breakdown"
```

---

### Task 4: Full verification pass

**Files:** none (verification only).

- [ ] **Step 1: Run the whole frontend unit suite**

Run: `cd frontend && npm test -- --run`
Expected: PASS (including the new modal test).

- [ ] **Step 2: Lint + build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no lint errors; `tsc -b && vite build` succeeds.

- [ ] **Step 3: Run the full e2e suite (or at least the two touched specs)**

Run: `python .claude/scripts/with_server.py -- bash -c "cd frontend && npx playwright test e2e/bank-balance-update-chip.spec.ts e2e/data-sources.spec.ts"`
Expected: PASS.

- [ ] **Step 4: i18n key audit**

Run:
```bash
cd frontend && node -e "const en=require('./src/locales/en.json'),he=require('./src/locales/he.json');const k=Object.keys(en.bankBalance||{});const miss=k.filter(x=>!(he.bankBalance||{})[x]);console.log(miss.length?('MISSING he: '+miss.join(',')):'bankBalance keys mirrored OK')"
```
Expected: `bankBalance keys mirrored OK`.

- [ ] **Step 5: Final commit if anything changed during verification**

```bash
git add -A
git commit -m "test: verify bank-balance update chip end-to-end" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- Chip on each account in expanded Bank Balance card → Task 3 (Step 6).
- Modal popup with explanatory copy → Task 1 (`explanation`, `scrapeNote`).
- Reused on DataSources (replaces inline editor) → Task 2.
- Disabled chip + "scrape first" tooltip when not scraped today → Task 2 (Step 5), Task 3 (Step 6).
- Modal guards internally (`isScrapedToday` prop) → Task 1 (Step 5 code + Step 3 test).
- New `bankBalance.*` i18n section, en + he → Task 1 (Steps 1–2), audited in Task 4 (Step 4).
- `stopPropagation` so the chip doesn't collapse the card → Task 3 (Step 6 handler) + modal-as-sibling (Step 7), asserted in the dashboard e2e.
- Narrow invalidation (`bank-balances` + `net-worth-over-time`) → Task 1 (Step 5).
- e2e specs + Playwright-MCP walkthrough → Tasks 2, 3, 4.
- No backend/PWA changes → honored (no such files touched).

**Placeholder scan:** none — every code step contains complete code; every run step has an exact command + expected result.

**Type consistency:** `UpdateBankBalanceModal` prop names (`isOpen`, `onClose`, `provider`, `accountName`, `currentBalance`, `isScrapedToday`) are identical across Task 1 definition and the Task 2 / Task 3 call sites. `bankBalancesApi.setBalance` payload `{ provider, account_name, balance }` matches the service signature and the e2e `postDataJSON()` assertions. `lastScrapes` row shape matches `scrapingApi.getLastScrapes()`.
