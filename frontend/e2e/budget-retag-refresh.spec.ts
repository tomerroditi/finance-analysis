import { test, expect, request, type Page } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Retagging a transaction from a monthly-budget rule's list moves it to its
 * new rule — and a reload straight after the write must show it there.
 *
 * The reload is the regression: the query cache is restored from IndexedDB,
 * whose snapshot is written through a throttle and so can predate the write.
 * Restored entries kept their original fetch time, anything younger than
 * `staleTime` was trusted as fresh, and the pre-write budget stuck on screen
 * across reloads.
 */

interface LedgerTx {
  unique_id: number;
  source: string;
  category: string | null;
  amount: number;
}

interface AnalysisRule {
  rule: { name: string };
  current_amount: number;
  data: LedgerTx[];
}

const TARGET_RULE = "Entertainment Budget";
const TARGET_CATEGORY = "Entertainment";

/** An untagged expense the current month's "Other Expenses" list holds. */
async function pickUntaggedExpense(): Promise<LedgerTx> {
  const now = new Date();
  const ctx = await request.newContext({ extraHTTPHeaders: { "X-FAD-Demo": "1" } });
  try {
    const res = await ctx.get(
      `${API_BASE}/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`,
    );
    expect(res.ok()).toBeTruthy();
    const { rules } = (await res.json()) as { rules: AnalysisRule[] };
    const other = rules.find((r) => r.rule.name === "Other Expenses");
    const tx = other?.data.find(
      (row) => !row.category && row.amount < 0 && row.source !== "cash_transactions",
    );
    if (!tx) throw new Error("demo data has no untagged expense this month");
    return tx;
  } finally {
    await ctx.dispose();
  }
}

/** The figures cell of one monthly rule row, e.g. "0 ₪ / 800 ₪". */
const ruleFigures = (page: Page, name: string) =>
  page
    .locator("div.rounded-xl", { has: page.getByText(name, { exact: true }) })
    .getByTestId("ledger-figures")
    .filter({ visible: true })
    .first();

async function openMonthly(page: Page) {
  await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
  await expect(page.getByTestId("budget-status-band")).toBeVisible({ timeout: 30_000 });
}

test.describe("Monthly budget retag", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("a retagged row moves rules and survives an immediate reload", async ({ page }) => {
    const tx = await pickUntaggedExpense();

    await navigateTo(page, "/budget");
    await openMonthly(page);
    const before = (await ruleFigures(page, TARGET_RULE).textContent()) ?? "";

    await page.getByText("Other Expenses", { exact: true }).first().click();
    const row = page.getByTestId(`transaction-row-${tx.source}_${tx.unique_id}`);
    await row.locator('input[type="checkbox"]').check();

    await page.locator("button", { hasText: /^Category$/ }).last().click();
    await page.getByRole("option", { name: TARGET_CATEGORY, exact: true }).click();
    await page.locator("button", { hasText: /^Tag$/ }).last().click();
    await page.getByRole("option").first().click();

    // Give the persister time to write the pre-write snapshot, as it would
    // for anyone who looked at the page for a moment before tagging.
    await page.waitForTimeout(1500);

    const written = page.waitForResponse(
      (r) => r.url().includes("/transactions/bulk-tag") && r.ok(),
    );
    await page
      .locator("div", { hasText: "selected" })
      .locator("button:has(svg.lucide-circle-check), button:has(svg.lucide-check-circle)")
      .first()
      .click();
    await written;

    await page.reload();
    await openMonthly(page);
    await expect(ruleFigures(page, TARGET_RULE)).not.toHaveText(before, { timeout: 15_000 });

    await page.getByText("Other Expenses", { exact: true }).first().click();
    await expect(page.locator("tr[data-testid^='transaction-row-']").first()).toBeVisible();
    await expect(page.getByTestId(`transaction-row-${tx.source}_${tx.unique_id}`)).toHaveCount(0);
  });
});
