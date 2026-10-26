import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData, scrollFeedUntil } from "./helpers";

/**
 * Rows under a budget pool explain how a refund changed its total.
 *
 * A pool totals what a month cost net of matched refunds, while its list
 * shows the real (gross) transactions. A refund landing in a later month is
 * netted into the purchase's month without being listed there, so the
 * purchase's row says what it counts for ("… after refunds"). The demo's
 * BUG ELECTRONICS charge has a partial refund eight days later, and that
 * refund lands in the next month for most of the month.
 *
 * The list is the dashboard's transaction feed, which mounts rows in batches
 * as it scrolls, so the test scrolls the feed until the charge has rendered.
 */
test.describe("Budget — refund-netted rows", () => {
  // Leaves the DB as it found it, but depends on the demo's refund links
  // being intact, so it starts from pristine data like any mutating spec.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  async function ensureTotalOpen(page: Page) {
    const hide = page.getByRole("button", { name: /Hide Transactions/i });
    if (await hide.isVisible().catch(() => false)) return;
    await page.getByRole("button", { name: /View month transactions/i }).click();
    await expect(hide).toBeVisible();
  }

  async function findInFeed(page: Page, text: string) {
    const feed = page.locator("[data-scroll-root]").filter({ visible: true }).first();
    const row = feed.getByTestId("recent-tx-row").filter({ hasText: text });
    return (await scrollFeedUntil(feed, row)) ? row.first() : null;
  }

  test("a refunded charge names its net amount and shows its date", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });

    // The charge is about three weeks old, so it sits in this month or the
    // one before it.
    let row = null;
    for (let attempt = 0; attempt < 3 && !row; attempt++) {
      await ensureTotalOpen(page);
      row = await findInFeed(page, "BUG ELECTRONICS");
      if (!row) {
        await page.locator("button .lucide-chevron-left").first().click();
        await page.waitForLoadState("networkidle");
      }
    }
    expect(row).not.toBeNull();
    await expect(row!).toBeVisible();

    // --- Gross amount listed, the netted figure beside it ---
    const note = row!.getByTestId("tx-net-amount");
    await expect(note).toBeVisible();
    await expect(note).toHaveText(/after refunds/i);
    await expect(row!).toContainText("1,162");

    // --- The details sheet reads the row's date ---
    await row!.getByRole("button", { name: /More actions/i }).click();
    await page.getByTestId("recent-tx-actions").getByRole("button", { name: /^Details$/i }).click();
    const dateValue = page
      .locator("dl dt", { hasText: /^Date$/ })
      .filter({ visible: true })
      .first()
      .locator("xpath=following-sibling::dd[1]");
    await expect(dateValue).toHaveText(/\d{4}/);
  });
});
