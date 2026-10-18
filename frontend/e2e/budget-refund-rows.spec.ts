import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

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
 * The same rows feed the edit dialog, whose `<input type="date">` stays blank
 * unless the row's date is a plain `YYYY-MM-DD`. The budget ledger used to
 * serve `YYYY-MM-DD 00:00:00`.
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

  test("a refunded charge names its net amount and opens with its date", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });

    const row = page.locator("tr").filter({ hasText: "BUG ELECTRONICS" });
    // The charge is about three weeks old, so it sits in this month or the
    // one before it.
    for (let attempt = 0; attempt < 3; attempt++) {
      await ensureTotalOpen(page);
      await page
        .getByPlaceholder(/Search/i)
        .filter({ visible: true })
        .first()
        .fill("BUG ELECTRONICS");
      await page.waitForLoadState("networkidle");
      if ((await row.count()) > 0) break;
      await page.locator("button .lucide-chevron-left").first().click();
      await page.waitForLoadState("networkidle");
    }
    await expect(row.first()).toBeVisible();

    // --- Gross amount listed, the netted figure beside it ---
    const note = row.first().getByTestId("tx-net-amount");
    await expect(note).toBeVisible();
    await expect(note).toHaveText(/after refunds/i);
    await expect(row.first()).toContainText("1,162.36");

    // --- The edit dialog's date input is filled ---
    await row.first().getByRole("button", { name: /Edit transaction/i }).click();
    const dateInput = page.locator('input[type="date"]').filter({ visible: true });
    await expect(dateInput).toHaveValue(/^\d{4}-\d{2}-\d{2}$/);
  });
});
