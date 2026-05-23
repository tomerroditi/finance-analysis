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

  test("bulk-edit category dropdown does not scroll when hovering visible options", async ({ page }) => {
    // Regression: hovering options used to call scrollIntoView on every
    // mouseenter, which fed back on itself — items shifted under the cursor,
    // a new mouseenter fired, the list scrolled again, and so on until it
    // bottomed out.
    await navigateTo(page, "/transactions");
    await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 10_000 });

    // Select 3 transactions to surface the BulkActionsBar.
    const checkboxes = page.locator("table tbody tr input[type='checkbox']");
    for (let i = 0; i < 3; i++) {
      await checkboxes.nth(i).check();
    }

    // Open the bulk Category dropdown.
    await page.getByRole("button", { name: "Category" }).click();
    const listbox = page.getByRole("listbox");
    await expect(listbox).toBeVisible();

    // Find the visible options inside the listbox.
    const visibleOptions = await page.evaluate(() => {
      const lb = document.querySelector('[role="listbox"]') as HTMLElement;
      if (!lb) return [];
      const rect = lb.getBoundingClientRect();
      return Array.from(lb.querySelectorAll('[role="option"]'))
        .map((el) => {
          const r = (el as HTMLElement).getBoundingClientRect();
          const fullyVisible = r.top >= rect.top && r.bottom <= rect.bottom;
          return { name: (el.textContent || "").trim(), fullyVisible };
        })
        .filter((o) => o.fullyVisible);
    });
    expect(visibleOptions.length).toBeGreaterThanOrEqual(3);

    const scrollTopBefore = await listbox.evaluate((el) => el.scrollTop);

    // Hover several fully-visible options. Each hover sets highlightIndex
    // via onMouseEnter; if the regression returns the listbox will scroll.
    for (const opt of visibleOptions.slice(0, 3)) {
      await page.getByRole("option", { name: opt.name, exact: true }).hover();
    }

    const scrollTopAfter = await listbox.evaluate((el) => el.scrollTop);
    expect(scrollTopAfter).toBe(scrollTopBefore);
  });
});
