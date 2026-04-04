import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, expectPageTitle } from "./helpers";

test.describe("Dashboard", () => {
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

  test("loads the dashboard with KPI cards", async ({ page }) => {
    await page.goto("/");
    await expectPageTitle(page, /Dashboard/);

    // KPI cards should be visible
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible();
    await expect(page.getByText(/Bank Balance/i).first()).toBeVisible();
  });

  test("displays charts and visualizations", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Check for chart containers (Plotly renders into div.js-plotly-plot)
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("shows recent transactions feed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Recent Transactions/i)).toBeVisible();
  });

  test("shows budget progress section", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Budget Progress/i)).toBeVisible();
  });
});
