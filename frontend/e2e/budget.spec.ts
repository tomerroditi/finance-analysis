import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("Budget", () => {
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

  // Every check here is a read-only interaction (tab switches, month
  // navigation, collapse/expand toggles), so they run as one journey on a
  // single navigation — the /budget cold load is the expensive step and it
  // used to be paid once per assertion group (8×).
  test("tabs, month navigation, trend chart, card toggles, and projects jump on one load", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await expectPageTitle(page, /Budget/);

    // --- Both tabs visible ---
    await expect(page.getByText(/Monthly Budget/i)).toBeVisible();
    await expect(page.getByText(/Project Budgets/i)).toBeVisible();

    // --- Tab switching: Projects hides the month header, Monthly restores it ---
    await page.getByText(/Project Budgets/i).click();
    await expect(
      page.getByRole("button", { name: "Previous" }).first(),
    ).toBeHidden();

    await page.getByText(/Monthly Budget/i).click();
    const prevMonth = page.getByRole("button", { name: "Previous" }).first();
    const nextMonth = page.getByRole("button", { name: "Next" }).first();
    await expect(prevMonth).toBeVisible();

    // --- Month navigation ---
    const monthLabel = page
      .locator("h2")
      .filter({ hasText: /\w+ \d{4}/ })
      .first();
    const initialMonth = await monthLabel.textContent();

    await prevMonth.click();
    await expect(monthLabel).not.toHaveText(initialMonth ?? "");

    await nextMonth.click();
    await expect(monthLabel).toHaveText(initialMonth ?? "");

    // --- Budget-vs-actual trend chart plots the Total Budget cap ---
    await page.waitForLoadState("networkidle");
    const trend = page.getByRole("button", { name: /Budget vs Actual/i });
    await expect(trend).toBeVisible();

    // Make sure the chart is expanded (collapsed by default on narrow viewports).
    const plot = page.locator(".recharts-wrapper").last();
    if (!(await plot.isVisible().catch(() => false))) {
      await trend.click();
    }
    await expect(plot).toBeVisible({ timeout: 15_000 });

    // Read the rendered bar series off the SVG. The budget series comes
    // from each month's "Total Budget" row; if the old per-category-rule sum
    // had crept back, the budget bars would be smaller than the gauge's cap.
    const barSeries = plot.locator(".recharts-bar");
    await expect(barSeries).toHaveCount(2);
    // The first series is the budget bars and the demo data defines a
    // Total Budget, so at least one month must plot a positive budget cap
    // (a bar with non-zero rendered height).
    const heights = await barSeries
      .first()
      .locator(".recharts-rectangle")
      .evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height));
    expect(heights.some((h) => h > 0)).toBe(true);

    // Collapse/expand the trend chart — should not throw and stays on the page.
    await trend.click();
    await page.waitForTimeout(300);
    await trend.click();
    await page.waitForTimeout(300);
    await expect(trend).toBeVisible();

    // --- Total Budget card collapses the rule list and shows month transactions ---
    const totalBudget = page.getByRole("button", { name: /^\s*Total Budget\s*$/ });
    if (await totalBudget.first().isVisible().catch(() => false)) {
      // Collapsing hides the per-rule rows; expanding shows them again.
      await totalBudget.first().click();
      await page.waitForTimeout(400);
      await totalBudget.first().click();
      await page.waitForTimeout(400);

      // "View month transactions" reveals a transactions table under the card.
      const viewMonth = page.getByRole("button", { name: /View month transactions/i });
      if (await viewMonth.first().isVisible().catch(() => false)) {
        await viewMonth.first().click();
        await page.waitForTimeout(500);
        await expect(
          page.getByRole("button", { name: /Hide Transactions/i }).first(),
        ).toBeVisible();
      }
    }

    // --- Pending Refunds section collapses from its header ---
    const refundsHeader = page.getByRole("button", { name: /Pending Refunds/i });
    if (await refundsHeader.first().isVisible().catch(() => false)) {
      await refundsHeader.first().click();
      await page.waitForTimeout(300);
      await refundsHeader.first().click();
      await page.waitForTimeout(300);
      await expect(refundsHeader.first()).toBeVisible();
    }

    // --- 'View all projects' jumps to the Projects tab ---
    const viewAll = page.getByRole("button", { name: /View all projects/i });
    if (await viewAll.isVisible().catch(() => false)) {
      await viewAll.click();
      await page.waitForTimeout(400);
      // Projects tab content: the project selector label appears.
      await expect(page.getByText(/Select Project/i).first()).toBeVisible();
    }
  });

  // Its own test because the assertion is about layout at a mobile width.
  // The tab bar previously used `flex-1` + `whitespace-nowrap`, so the three
  // tabs could not shrink below their text and pushed the document 53px past
  // the viewport — the whole page scrolled sideways on a phone.
  test("does not scroll horizontally at mobile width", async ({ page }) => {
    await navigateTo(page, "/budget");
    await expect(page.getByRole("navigation").first()).toBeVisible();

    await page.setViewportSize({ width: 375, height: 812 });
    // Anchor on the tab bar so the measurement can't race an unlaid-out page.
    await expect(
      page.getByRole("button", { name: /Project Budgets/i }).first(),
    ).toBeVisible();

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });

  test("alerts banner can be dismissed and alerts disabled from settings", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const dismissAll = page.getByRole("button", { name: /Dismiss all/i });
    if (await dismissAll.isVisible().catch(() => false)) {
      await dismissAll.click();
      await page.waitForTimeout(300);
      await expect(dismissAll).toHaveCount(0);
    }

    // Open Settings and toggle Budget Alerts off (the settings control is a
    // <label>; the mobile drawer tile uses a <span>, so scope to the label).
    await page.getByRole("button", { name: "Settings" }).first().click();
    const toggleRow = page.locator("label", { hasText: "Budget Alerts" }).first();
    await expect(toggleRow).toBeVisible();
    await toggleRow.click();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);

    // The in-page alerts banner must be gone once alerts are disabled.
    await expect(page.getByText(/budgets need attention/i)).toHaveCount(0);
  });
});
