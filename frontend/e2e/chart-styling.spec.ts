import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";
/**
 * Guards the "soft gradient" chart style (see utils/chartStyle.ts and
 * components/charts/).
 *
 * These assertions lock in the signature ingredients of the look so a future
 * refactor of the shared theme/helpers can't silently revert them:
 *   1. charts still render after the restyle (regression guard),
 *   2. trend/area charts emit an SVG <linearGradient> (AreaGradientDef),
 *   3. allocation donuts show a center total (DonutChart centerLabel).
 *
 * Run via with_server.py so both backend + frontend are up. Demo Mode supplies
 * the Cohen-family investments/liabilities the charts need.
 */
test.describe("Chart styling (soft gradient)", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("dashboard charts render after the restyle", async ({ page }) => {
    await navigateTo(page, "/");
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 30_000,
    });
  });

  test("investment analysis chart uses a gradient area fill", async ({ page }) => {
    await navigateTo(page, "/investments");
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 15_000,
    });

    // The gradient area fill lives in the single-series balance chart inside
    // the Investment Analysis modal (multi-line charts keep clean lines).
    await page.getByRole("button", { name: /analysis/i }).first().click();
    const modalPlot = page.locator(".recharts-wrapper").last();
    await expect(modalPlot).toBeVisible({ timeout: 15_000 });

    // AreaGradientDef renders as an SVG <linearGradient> in the chart's <defs>
    // (a non-rendered node, so assert presence by count, not visibility).
    await expect(
      modalPlot.locator("defs linearGradient"),
    ).not.toHaveCount(0, { timeout: 15_000 });
  });

  test("investment allocation donut shows a center total", async ({ page }) => {
    await navigateTo(page, "/investments");
    // The donut center label renders the formatted total (e.g. "… ₪") as an
    // HTML overlay inside the DonutChart wrapper.
    await expect(
      page.getByTestId("donut-chart").getByText(/₪/).first(),
    ).toBeVisible({ timeout: 15_000 });
  });
});
