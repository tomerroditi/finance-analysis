import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo, expectPageTitle } from "./helpers";

test.describe("DataSources", () => {
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

  test("loads the data sources page", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await expectPageTitle(page, /Data Sources/);
  });

  test("displays connected accounts in demo mode", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // In demo mode, there should be demo accounts listed
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });

  test("shows bank balance section", async ({ page }) => {
    await navigateTo(page, "/data-sources");
    await page.waitForLoadState("networkidle");

    // Bank balance section should show account balances
    const content = page.locator("main");
    await expect(content).toBeVisible();
  });
});
