import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Monthly-budget "move transaction to prev/next month" feature.
 *
 * A transaction can be reassigned one month earlier/later for budget
 * bucketing only. The buttons live in the transactions-table actions
 * column and appear only on the monthly budget page.
 */
test.describe("Budget month override", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  /**
   * Ensure the Total Budget month-transactions list is expanded. The toggle
   * persists its open/closed state across month navigation, so it may read
   * either "View month transactions" (closed) or "Hide Transactions" (open).
   */
  async function ensureTotalOpen(page: Page) {
    const hide = page.getByRole("button", { name: /Hide Transactions/i });
    if (await hide.isVisible().catch(() => false)) return;
    const view = page.getByRole("button", { name: /View month transactions/i });
    if (await view.isVisible().catch(() => false)) {
      await view.click();
      await page.waitForTimeout(400);
    }
  }

  const moveNextButtons = (page: Page) =>
    page.locator("button .lucide-calendar-plus").filter({ visible: true });

  /**
   * Open the budget page and find a month (current, walking back if needed)
   * whose Total Budget list has transactions to move. Leaves the list open.
   */
  async function openMonthWithTransactions(page: Page): Promise<boolean> {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    for (let attempt = 0; attempt < 6; attempt++) {
      await ensureTotalOpen(page);
      if ((await moveNextButtons(page).count()) > 0) return true;
      await page.locator("button .lucide-chevron-left").first().click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
    }
    return false;
  }

  test("moves a transaction to the next month and shows the moved badge", async ({
    page,
  }) => {
    const found = await openMonthWithTransactions(page);
    test.skip(!found, "No month with transactions found in demo data");

    // Identify the row we're about to move by its stable data-testid.
    const firstBtn = moveNextButtons(page).first();
    const rowId = await firstBtn
      .locator("xpath=ancestor::tr")
      .getAttribute("data-testid");
    expect(rowId).toBeTruthy();

    // Click "move to next month" and wait for the override API call to succeed.
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/budget-month-overrides/") &&
          r.request().method() === "POST",
      ),
      firstBtn.click(),
    ]);
    expect(resp.ok()).toBeTruthy();
    await page.waitForTimeout(500);

    // The moved transaction leaves the current month's dataset entirely.
    await expect(page.locator(`[data-testid="${rowId}"]`)).toHaveCount(0);

    // Navigate to the next month — the moved transaction shows the badge.
    await page.locator("button .lucide-chevron-right").first().click();
    await page.waitForTimeout(300);
    await ensureTotalOpen(page);

    const movedRow = page.locator(`[data-testid="${rowId}"]`);
    await expect(movedRow).toBeVisible();
    await expect(movedRow.locator(".lucide-calendar-clock")).toBeVisible();

    // The "move to next month" button is now disabled (already +1 from origin).
    await expect(
      movedRow.locator("button:has(.lucide-calendar-plus)"),
    ).toBeDisabled();

    // Move it back to its real month to restore the demo DB state.
    await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/budget-month-overrides/") &&
          r.request().method() === "POST",
      ),
      movedRow.locator("button:has(.lucide-calendar-minus)").click(),
    ]);
    await page.waitForTimeout(400);
    await expect(page.locator(`[data-testid="${rowId}"]`)).toHaveCount(0);
  });
});
