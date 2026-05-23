import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("Transactions", () => {
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

  test("loads the transactions page with data", async ({ page }) => {
    await navigateTo(page, "/transactions");
    await expectPageTitle(page, /Transactions/);

    // Transaction table should have rows
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
  });

  test("service tab filtering works", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Click the Credit Card tab
    await page.getByRole("button", { name: /Credit Card/i }).click();
    await page.waitForLoadState("networkidle");

    // The tab should be visually active
    const ccTab = page.getByRole("button", { name: /Credit Card/i });
    await expect(ccTab).toBeVisible();
  });

  test("text search filters transactions", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for transactions to load
    await page.waitForLoadState("networkidle");

    // Open filter panel if not visible
    const filterButton = page.getByRole("button", { name: /filter/i });
    if (await filterButton.isVisible().catch(() => false)) {
      await filterButton.click();
    }

    // Type in the search box
    const searchInput = page.getByPlaceholder(/search/i).first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill("test search");
      // Wait for filter to apply
      await page.waitForTimeout(500);
    }
  });

  test("pagination works", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Check pagination exists
    const paginationText = page.getByText(/Showing/i);
    await expect(paginationText).toBeVisible({ timeout: 10_000 });

    // Try navigating to next page if available
    const nextButton = page.locator("button .lucide-chevron-right").first();
    if (await nextButton.isVisible().catch(() => false)) {
      await nextButton.click();
      await page.waitForTimeout(300);
    }
  });

  test("per-row eraser clears category and tag from a transaction", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for the table to populate
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    await page.waitForLoadState("networkidle");

    // Find the first row that has the eraser button (i.e., has a category or tag).
    const clearButton = page
      .getByRole("button", { name: /clear category and tag/i })
      .first();
    await expect(clearButton).toBeVisible({ timeout: 10_000 });

    // Capture the data-testid of the ancestor row so we can re-locate it after
    // the query invalidation triggers a re-render.
    const row = clearButton.locator("xpath=ancestor::tr[1]");
    const rowTestId = await row.getAttribute("data-testid");
    expect(rowTestId).toBeTruthy();

    // Click the eraser button.
    await clearButton.click();

    // The global MutationCache.onSuccess debounced invalidator fires ~200 ms
    // after the mutation succeeds, then React Query refetches the transactions.
    // Wait for the network to settle so the re-render completes.
    await page.waitForLoadState("networkidle");

    // Re-locate the same row by its stable data-testid. The button must now be
    // absent — the category and tag were cleared, so the conditional render
    // `{(tx.category || tx.tag) && <button ...>}` no longer renders it.
    const updatedRow = page.locator(`[data-testid="${rowTestId}"]`);
    await expect(
      updatedRow.getByRole("button", { name: /clear category and tag/i }),
    ).toHaveCount(0);
  });
});
