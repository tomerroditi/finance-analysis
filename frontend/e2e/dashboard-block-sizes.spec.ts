import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Half-width dashboard cards: on wide (>=lg) viewports the customizable region
 * is a 2-column grid. `budget` and `recent` are both half-width and adjacent in
 * the default order, so they pair on one row; `charts` is full-width and spans
 * the row. Fill order is start->end and flips under RTL (Hebrew).
 */
test.describe("Dashboard half-width blocks", () => {
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

  async function boxOf(page: Page, id: string) {
    const el = page.locator(`[data-card-id="${id}"]`);
    await expect(el).toBeVisible({ timeout: 45_000 });
    const box = await el.boundingBox();
    if (!box) throw new Error(`no box for ${id}`);
    return box;
  }

  test("two half cards pair on one row; a full card spans the row (LTR)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");
    const charts = await boxOf(page, "charts");

    expect(Math.abs(budget.y - recent.y)).toBeLessThan(4);
    expect(Math.abs(budget.width - recent.width)).toBeLessThan(8);
    expect(budget.x).toBeLessThan(recent.x);
    expect(charts.width).toBeGreaterThan(budget.width * 1.8);
  });

  test("fill order flips under RTL (Hebrew)", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("language", "he"));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");

    expect(Math.abs(budget.y - recent.y)).toBeLessThan(4);
    expect(budget.x).toBeGreaterThan(recent.x);
  });

  test("below lg the cards stack full-width (single column)", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 1000 });
    await page.goto("/");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");

    expect(recent.y).toBeGreaterThan(budget.y + budget.height - 4);
    expect(Math.abs(budget.width - recent.width)).toBeLessThan(8);
  });
});
