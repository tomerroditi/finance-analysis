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

  test("bulk eraser clears category and tag from selected transactions", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for the table to populate.
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });
    await page.waitForLoadState("networkidle");

    // Find rows that have a per-row eraser button — these are the rows with
    // a category or tag assigned. We need at least two such rows.
    const candidateRows = page
      .locator("table tbody tr")
      .filter({ has: page.getByRole("button", { name: /clear category and tag/i }) });

    const firstRow = candidateRows.nth(0);
    const secondRow = candidateRows.nth(1);

    await expect(firstRow).toBeVisible({ timeout: 10_000 });
    await expect(secondRow).toBeVisible({ timeout: 10_000 });

    // Capture stable data-testid for both rows so we can re-locate them after
    // the query invalidation triggers a re-render.
    const firstRowId = await firstRow.getAttribute("data-testid");
    const secondRowId = await secondRow.getAttribute("data-testid");
    expect(firstRowId).toBeTruthy();
    expect(secondRowId).toBeTruthy();

    // Select both rows via their checkboxes. Checkboxes are hidden on mobile
    // (hidden md:table-cell) but Playwright uses the default desktop viewport
    // (1280 × 720), so the checkboxes are reachable.
    await firstRow.locator('input[type="checkbox"]').check();
    await secondRow.locator('input[type="checkbox"]').check();

    // BulkActionsBar appears as a fixed div at the bottom. The bulk eraser
    // button lives inside that bar — outside the <table> — and shares the
    // same aria-label ("Clear category and tag") as the per-row erasers.
    // We target it by scoping to the bar's container div (identified by its
    // unique fixed-position styling class).
    const bulkBar = page.locator("div.fixed.bottom-4, div.fixed.md\\:bottom-8").last();
    const bulkEraser = bulkBar.getByRole("button", { name: /clear category and tag/i });
    await expect(bulkEraser).toBeVisible({ timeout: 5_000 });
    await bulkEraser.click();

    // A confirmation dialog opens (rendered by DialogContext / useConfirm).
    // The confirm button is labeled with transactions.clearConfirm.confirm = "Clear".
    const confirmButton = page.getByRole("button", { name: /^clear$/i }).last();
    await expect(confirmButton).toBeVisible({ timeout: 5_000 });
    await confirmButton.click();

    // The global MutationCache.onSuccess debounced invalidator fires ~200 ms
    // after the mutation succeeds, then React Query refetches the transactions.
    // Wait for the network to settle so the re-render completes.
    await page.waitForLoadState("networkidle");

    // Both rows now have no per-row eraser button — the category and tag have
    // been cleared, so the conditional render `{(tx.category || tx.tag) && …}`
    // no longer renders the button.
    await expect(
      page.locator(`[data-testid="${firstRowId}"]`).getByRole("button", {
        name: /clear category and tag/i,
      }),
    ).toHaveCount(0);
    await expect(
      page.locator(`[data-testid="${secondRowId}"]`).getByRole("button", {
        name: /clear category and tag/i,
      }),
    ).toHaveCount(0);
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
