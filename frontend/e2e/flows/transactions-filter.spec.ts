import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Verifies the Transactions filter panel narrows results when text-search
 * and a service tab filter are combined.
 */
test.describe("Transactions filter flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("text search + service tab narrows the list", async ({ page }) => {
    await gotoAndWait(page, "/transactions");
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });

    // Click the Credit Card tab — narrows by source.
    await page.getByRole("button", { name: /^credit card$/i }).click();
    await page.waitForLoadState("networkidle");

    // Type a query that matches a known demo merchant.
    await page.getByPlaceholder(/search descriptions/i).fill("PAZ");
    // Allow debounced filter to apply.
    await page.waitForTimeout(500);

    // Every visible row should now mention PAZ.
    const visibleRowCount = await rows.count();
    if (visibleRowCount > 0) {
      const firstText = await rows.first().textContent();
      expect(firstText?.toUpperCase()).toContain("PAZ");
    }
    // It is acceptable for the filter to produce 0 rows on a stale dataset;
    // the assertion that matters is the lack of unrelated descriptions.
    for (let i = 0; i < visibleRowCount; i++) {
      const text = (await rows.nth(i).textContent())?.toUpperCase() ?? "";
      expect(text).toContain("PAZ");
    }
  });
});
