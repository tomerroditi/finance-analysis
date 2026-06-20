import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * The Spending Calendar (`heatmap`) card shows two months (previous + current)
 * side by side when it sits at half-row width on wide (>=lg) screens, and a
 * single current month when it's full-width or in the single-column mobile
 * layout.
 *
 * The card ships visible by default (non-beta), so no custom layout seeding is
 * needed — it renders at its configured half width.
 */
test.describe("Dashboard spending calendar months", () => {
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
    await page.addInitScript(() => window.localStorage.removeItem("fa.dashboard.layout"));
  });

  /** Count the 7-column weekday-header rows inside the heatmap card — one per month. */
  async function monthGridCount(page: Page) {
    const card = page.locator('[data-card-id="heatmap"]');
    await expect(card).toBeVisible({ timeout: 45_000 });
    // Each month renders a weekday header: a 7-column grid whose first cell is a
    // single-letter weekday label. The header uses mb-1 (gap was mb-1.5 before
    // the compact-cell refactor).
    return card.locator("div.grid.grid-cols-7.mb-1").count();
  }

  test("shows two months at half-row width (>=lg)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect.poll(() => monthGridCount(page), { timeout: 45_000 }).toBe(2);
  });

  test("shows a single month in the single-column mobile layout", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 1000 });
    await page.goto("/");

    await expect.poll(() => monthGridCount(page), { timeout: 45_000 }).toBe(1);
  });
});
