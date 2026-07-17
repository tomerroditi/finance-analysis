import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Sidebar.tsx no longer fetches the full transaction list to compute the
 * uncategorized badge — it calls the dedicated
 * GET /api/transactions/uncategorized-count endpoint instead. This spec
 * verifies the badge rendered on the /transactions nav link agrees with
 * that endpoint's count, covering both branches: a numeric badge when
 * count > 0, and no numeric badge when everything is categorized.
 */
test.describe("sidebar uncategorized badge", () => {
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

  test("badge count matches the backend count endpoint", async ({ page, request }) => {
    const res = await request.get(
      "http://localhost:8000/api/transactions/uncategorized-count",
    );
    expect(res.ok()).toBeTruthy();
    const { count } = await res.json();

    await page.goto("/");
    await page.waitForResponse(
      (r) => r.url().includes("/api/transactions/uncategorized-count") && r.ok(),
    );
    await page.waitForLoadState("domcontentloaded");

    const transactionsLink = page.getByRole("link", { name: /transactions/i }).first();
    await expect(transactionsLink).toBeVisible();

    if (count > 0) {
      await expect(transactionsLink).toContainText(String(count > 99 ? "99+" : count));
    } else {
      // No badge rendered when everything is categorized.
      await expect(transactionsLink).not.toContainText(/\d/);
    }
  });
});
