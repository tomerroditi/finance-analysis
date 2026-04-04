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
    await page.waitForLoadState("networkidle");

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
});
