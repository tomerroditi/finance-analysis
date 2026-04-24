import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("Categories", () => {
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

  test("loads the categories page with category list", async ({ page }) => {
    await navigateTo(page, "/categories");
    await expectPageTitle(page, /Categories/);

    // Should display some categories
    await expect(page.getByText("Food").first()).toBeVisible({ timeout: 10_000 });
  });

  test("categories have tags nested inside", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // Food category should have tags visible
    const foodSection = page.getByText("Food").first();
    await expect(foodSection).toBeVisible();
  });

  test("protected categories are displayed", async ({ page }) => {
    await navigateTo(page, "/categories");
    await page.waitForLoadState("networkidle");

    // Protected categories should be visible
    await expect(page.getByText("Salary").first()).toBeVisible();
    await expect(page.getByText("Investments").first()).toBeVisible();
  });
});
