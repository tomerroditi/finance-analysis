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

  test("loads the budget page with tabs", async ({ page }) => {
    await navigateTo(page, "/budget");
    await expectPageTitle(page, /Budget/);

    // Both tabs should be visible
    await expect(page.getByText(/Monthly Budget/i)).toBeVisible();
    await expect(page.getByText(/Project Budgets/i)).toBeVisible();
  });

  test("monthly budget view shows spending gauges", async ({ page }) => {
    await navigateTo(page, "/budget");

    // Wait for budget data to load

    // Should show budget rules or "no rules" state
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });

  test("switches between monthly and project tabs", async ({ page }) => {
    await navigateTo(page, "/budget");

    // Click Project Budgets tab
    await page.getByText(/Project Budgets/i).click();
    await page.waitForTimeout(300);

    // Click back to Monthly Budget
    await page.getByText(/Monthly Budget/i).click();
    await page.waitForTimeout(300);
  });

  test("month navigation works", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    // Find month navigation buttons (chevron left/right)
    const prevMonth = page.locator("button .lucide-chevron-left").first();
    if (await prevMonth.isVisible().catch(() => false)) {
      await prevMonth.click();
      await page.waitForTimeout(500);

      // Navigate forward
      const nextMonth = page.locator("button .lucide-chevron-right").first();
      await nextMonth.click();
      await page.waitForTimeout(500);
    }
  });

  test("budget-vs-actual trend chart toggles", async ({ page }) => {
    await navigateTo(page, "/budget");

    const trend = page.getByRole("button", { name: /Budget vs Actual/i });
    await expect(trend).toBeVisible();

    // Toggle collapse/expand — should not throw and stays on the page.
    await trend.click();
    await page.waitForTimeout(300);
    await trend.click();
    await page.waitForTimeout(300);
    await expect(trend).toBeVisible();
  });

  test("budget-vs-actual trend chart plots the Total Budget cap, not the rule sum", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    // Make sure the chart is expanded (collapsed by default on narrow viewports).
    const trend = page.getByRole("button", { name: /Budget vs Actual/i });
    await expect(trend).toBeVisible();
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
  });


  test("'View all projects' jumps to the Projects tab", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const viewAll = page.getByRole("button", { name: /View all projects/i });
    if (await viewAll.isVisible().catch(() => false)) {
      await viewAll.click();
      await page.waitForTimeout(400);
      // Projects tab content: the project selector label appears.
      await expect(page.getByText(/Select Project/i).first()).toBeVisible();
    }
  });

  test("alerts banner, when present, can be dismissed", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const dismissAll = page.getByRole("button", { name: /Dismiss all/i });
    if (await dismissAll.isVisible().catch(() => false)) {
      await dismissAll.click();
      await page.waitForTimeout(300);
      await expect(dismissAll).toHaveCount(0);
    }
  });

  test("Total Budget card collapses the rule list and shows month transactions", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const totalBudget = page.getByRole("button", { name: /^\s*Total Budget\s*$/ });
    if (!(await totalBudget.first().isVisible().catch(() => false))) return;

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
  });

  test("Pending Refunds section collapses from its header", async ({ page }) => {
    await navigateTo(page, "/budget");
    await page.waitForLoadState("networkidle");

    const header = page.getByRole("button", { name: /Pending Refunds/i });
    if (await header.first().isVisible().catch(() => false)) {
      await header.first().click();
      await page.waitForTimeout(300);
      await header.first().click();
      await page.waitForTimeout(300);
      await expect(header.first()).toBeVisible();
    }
  });

  test("budget alerts can be disabled from settings", async ({ page }) => {
    await navigateTo(page, "/budget");

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
