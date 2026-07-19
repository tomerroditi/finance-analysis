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

  // Pure read-only assertions (table smoke, pagination, column sizing, eraser
  // alignment, service-tab + text-search filtering) against one rendered page
  // — a single navigation covers all of them.
  test("table, pagination, column sizing, eraser alignment, and filters on one load", async ({
    page,
  }) => {
    await navigateTo(page, "/transactions");
    await expectPageTitle(page, /Transactions/);

    // Transaction table has rows.
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Pagination summary renders.
    await expect(page.getByText(/Showing/i)).toBeVisible({ timeout: 10_000 });

    // --- Description column width regression ---
    // The table is `table-fixed` and every column except the description had
    // an explicit pixel width. With the old `min-w-[800px]` the fixed columns
    // consumed almost the whole table, collapsing the description column to
    // ~20px (≈3 characters). It now has a 150px width floor.
    const descHeader = page.locator("thead th").filter({ hasText: /Description/i }).first();
    await expect(descHeader).toBeVisible();
    const headerBox = await descHeader.boundingBox();
    expect(headerBox).not.toBeNull();
    expect(headerBox!.width).toBeGreaterThan(110);

    // Sanity-check a body cell in the same column matches the header width,
    // so the data cell isn't independently squeezed.
    const firstRow = rows.first();
    const descCell = firstRow.locator("td").nth(await descHeader.evaluate((th) => {
      // Column index of the description header among its sibling <th> cells.
      return Array.from(th.parentElement!.children).indexOf(th);
    }));
    const cellBox = await descCell.boundingBox();
    expect(cellBox).not.toBeNull();
    expect(cellBox!.width).toBeGreaterThan(110);

    // --- Eraser alignment: every row renders exactly one eraser button so
    // the action column lines up regardless of whether the row is tagged.
    // (The disabled-when-untagged behavior is verified deterministically in
    // the per-row eraser test below.)
    await page.waitForLoadState("networkidle");
    const rowCount = await rows.count();
    const erasers = page.locator('table tbody button[aria-label="Clear category and tag"]');
    await expect(erasers).toHaveCount(rowCount);

    // --- Service tab + text search narrow the list together ---
    await page.getByRole("button", { name: /Credit Card/i }).click();
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Type a query that matches a known demo merchant.
    await page.getByPlaceholder(/search descriptions/i).fill("PAZ");
    await page.waitForTimeout(500); // debounced filter

    // Every visible row must now mention PAZ (0 rows is acceptable on a
    // stale dataset; the assertion that matters is no unrelated rows).
    const visibleRowCount = await rows.count();
    for (let i = 0; i < visibleRowCount; i++) {
      const text = (await rows.nth(i).textContent())?.toUpperCase() ?? "";
      expect(text).toContain("PAZ");
    }
  });

  test("per-row eraser clears category and tag from a transaction", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for the table to populate
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // The eraser button renders on every row but is disabled for rows with no
    // category/tag (so the action column stays aligned). Find the first
    // *enabled* eraser — that's a row with a category or tag.
    const clearButton = page
      .locator('table tbody button[aria-label="Clear category and tag"]:enabled')
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

    // Re-locate the same row by its stable data-testid. The eraser is still
    // present (kept for alignment) but now disabled — the category and tag
    // were cleared, so `disabled={... || !hasTagging}` evaluates true.
    const updatedRow = page.locator(`[data-testid="${rowTestId}"]`);
    await expect(
      updatedRow.locator('button[aria-label="Clear category and tag"]'),
    ).toBeDisabled();
  });

  test("bulk eraser clears category and tag from selected transactions", async ({ page }) => {
    await navigateTo(page, "/transactions");

    // Wait for the table to populate.
    const rows = page.locator("table tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 10_000 });

    // Find rows whose per-row eraser is *enabled* — these are the rows with
    // a category or tag assigned (the button renders on every row but is
    // disabled when untagged). We need at least two such rows.
    const candidateRows = page
      .locator("table tbody tr")
      .filter({ has: page.locator('button[aria-label="Clear category and tag"]:enabled') });

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

    // Both rows now have a disabled per-row eraser — the category and tag have
    // been cleared, so the button stays (for alignment) but `disabled` is true.
    await expect(
      page
        .locator(`[data-testid="${firstRowId}"]`)
        .locator('button[aria-label="Clear category and tag"]'),
    ).toBeDisabled();
    await expect(
      page
        .locator(`[data-testid="${secondRowId}"]`)
        .locator('button[aria-label="Clear category and tag"]'),
    ).toBeDisabled();
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

    // Open the bulk Category dropdown. Use exact match — otherwise the per-row
    // eraser buttons (aria-label="Clear category and tag") also match the
    // substring "Category" and Playwright's strict mode fails on 9+ matches.
    await page.getByRole("button", { name: "Category", exact: true }).click();
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
