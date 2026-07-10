import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * The former single tabbed "Charts & analytics" panel is now four independent
 * dashboard cards. Income & Expenses + Net Worth ship visible; Cash Flow +
 * Categories ship hidden (opt-in) but — unlike beta cards — carry no Beta pill.
 * Each card is reorderable/hideable via Settings → Dashboard like any other.
 */
test.describe("Dashboard per-chart cards", () => {
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

  test.beforeEach(async ({ page }) => {
    // Start each test from a clean (default) layout.
    await page.addInitScript(() => window.localStorage.removeItem("fa.dashboard.layout"));
  });

  test("Income & Expenses and Net Worth render as separate cards by default", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-card-id="income_expenses"]')).toBeVisible({ timeout: 45_000 });
    await expect(page.locator('[data-card-id="net_worth"]')).toBeVisible();

    // Cash Flow + Categories are opt-in: not rendered on the default dashboard.
    await expect(page.locator('[data-card-id="cash_flow"]')).toHaveCount(0);
    await expect(page.locator('[data-card-id="category"]')).toHaveCount(0);
  });

  test("Cash Flow sits in Hidden cards with no Beta badge", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-card-id="income_expenses"]')).toBeVisible({ timeout: 45_000 });

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // Cash Flow is under Hidden cards…
    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();
    const cashFlowRow = page.getByText("Cash Flow", { exact: true }).locator("xpath=..");
    await expect(cashFlowRow).toBeVisible();
    // …but it is default-hidden, NOT beta, so it carries no Beta pill (contrast
    // the forecast card, which does).
    await expect(cashFlowRow.getByText(/^Beta$/i)).toHaveCount(0);
    const forecastRow = page.getByText("This Month (forecast)", { exact: true }).locator("xpath=..");
    await expect(forecastRow.getByText(/^Beta$/i)).toBeVisible();
  });

  test("opting Cash Flow in via Settings shows it on the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-card-id="income_expenses"]')).toBeVisible({ timeout: 45_000 });
    await expect(page.locator('[data-card-id="cash_flow"]')).toHaveCount(0);

    await page.getByRole("button", { name: /^Settings$/ }).first().click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    const cashFlowRow = page.getByText("Cash Flow", { exact: true }).locator("xpath=..");
    await cashFlowRow.getByRole("button", { name: /Show card/i }).click();
    await page.keyboard.press("Escape");

    await expect(page.locator('[data-card-id="cash_flow"]')).toBeVisible({ timeout: 30_000 });
  });
});
