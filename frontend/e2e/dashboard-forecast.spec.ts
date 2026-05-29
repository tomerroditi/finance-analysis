import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * E2E coverage for the Israeli-finance-app feature additions:
 * the "This Month" cash-flow forecast hero, insight cards,
 * subscriptions/recurring panel, savings goals, and the spending heatmap.
 */
test.describe("Dashboard — forecast, recurring, goals", () => {
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

  test("shows the This Month cash-flow forecast hero", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByText("This Month").first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Safe to spend/i).first()).toBeVisible();
    await expect(page.getByText(/Projected end balance/i).first()).toBeVisible();
  });

  test("shows the subscriptions / recurring panel", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Subscriptions & Recurring/i).first()).toBeVisible({
      timeout: 45_000,
    });
  });

  test("shows the savings goals panel and spending calendar", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Savings Goals/i).first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText(/Spending Calendar/i).first()).toBeVisible();
  });

  test("can open the add-goal editor modal", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Add goal/i }).first().waitFor({ timeout: 45_000 });
    await page.getByRole("button", { name: /Add goal/i }).first().click();
    await expect(page.getByText(/New savings goal/i)).toBeVisible();
    await expect(page.getByPlaceholder(/Vacation/i)).toBeVisible();
  });
});
