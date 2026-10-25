import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData, scrollFeedUntil } from "./helpers";

/**
 * Monthly-budget "move transaction to prev/next month" feature.
 *
 * A transaction can be reassigned one month earlier/later for budget
 * bucketing only. The buttons live in each row's action bar (the "More
 * actions" toggle) and appear only on the monthly budget page.
 */
test.describe("Budget month override", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
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

  const feed = (page: Page) =>
    page.locator("[data-scroll-root]").filter({ visible: true }).first();
  const rowFor = (page: Page, key: string) =>
    page.locator(`[data-tx-key="${key}"]`).filter({ visible: true });

  /** Open a row's action bar, where the month-move buttons live. */
  async function openActions(page: Page, key: string) {
    const row = rowFor(page, key);
    if (!(await row.getByTestId("recent-tx-actions").isVisible())) {
      await row.getByRole("button", { name: /More actions/i }).click();
    }
    await expect(row.getByTestId("recent-tx-actions")).toBeVisible();
    return row;
  }

  /**
   * Open the budget page and find a month (current, walking back if needed)
   * whose Total Budget list has transactions to move. Leaves the list open
   * and returns the first row's key.
   */
  async function openMonthWithTransactions(page: Page): Promise<string | null> {
    await navigateTo(page, "/budget");
    // Overview is the landing tab; this flow needs the monthly ledger.
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });
    await page.waitForLoadState("networkidle");

    for (let attempt = 0; attempt < 6; attempt++) {
      await ensureTotalOpen(page);
      const first = page.locator("[data-tx-key]").filter({ visible: true }).first();
      if ((await first.count()) > 0) return first.getAttribute("data-tx-key");
      await page.locator("button .lucide-chevron-left").first().click();
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(300);
    }
    return null;
  }

  test("moves a transaction to the next month and shows the moved badge", async ({
    page,
  }) => {
    const rowId = await openMonthWithTransactions(page);
    test.skip(!rowId, "No month with transactions found in demo data");
    const key = rowId!;

    const row = await openActions(page, key);
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/api/budget-month-overrides/") &&
          r.request().method() === "POST",
      ),
      row.locator("button:has(.lucide-calendar-plus)").click(),
    ]);
    expect(resp.ok()).toBeTruthy();
    await page.waitForTimeout(500);

    // The moved transaction leaves the current month's dataset entirely.
    await expect(page.locator(`[data-tx-key="${key}"]`)).toHaveCount(0);

    // Navigate to the next month — the moved transaction shows the badge.
    // It keeps its real (earlier) date, so it sorts last and may sit past
    // the first rendered batch.
    await page.locator("button .lucide-chevron-right").first().click();
    await page.waitForTimeout(300);
    await ensureTotalOpen(page);
    expect(await scrollFeedUntil(feed(page), rowFor(page, key))).toBe(true);

    const movedRow = rowFor(page, key);
    await expect(movedRow.getByTestId("recent-tx-month-moved")).toBeVisible();

    // --- The badge does not shift its row's columns: every row in the list,
    //     moved or not, lays its cells out at the same offsets and widths ---
    const layouts = await feed(page).evaluate((el) => [
      ...new Set(
        [...el.querySelectorAll('[data-testid="recent-tx-row"]')].map((row) =>
          [...row.children]
            .map((cell) => {
              const box = cell.getBoundingClientRect();
              return `${Math.round(box.left)}:${Math.round(box.width)}`;
            })
            .join("|"),
        ),
      ),
    ]);
    expect(layouts).toHaveLength(1);

    // The "move to next month" button is now disabled (already +1 from origin).
    await openActions(page, key);
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
    await expect(page.locator(`[data-tx-key="${key}"]`)).toHaveCount(0);
  });
});
