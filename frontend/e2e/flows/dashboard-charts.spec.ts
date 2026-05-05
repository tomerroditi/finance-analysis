import { test, expect } from "@playwright/test";
import { setDemoMode, gotoAndWait } from "./_helpers";

/**
 * Verifies the dashboard's main Plotly chart mounts after demo data loads.
 * The dashboard ships with several chart tabs but the most reliable signal
 * that the chart pipeline is alive is the default Income & Expenses Totals
 * view rendering its Plotly figure.
 */
test.describe("Dashboard chart rendering flow", () => {
  test.beforeAll(async ({ request }) => {
    await setDemoMode(request, true);
  });
  test.afterAll(async ({ request }) => {
    await setDemoMode(request, false);
  });

  test("dashboard renders a Plotly chart on the default tab", async ({ page }) => {
    await gotoAndWait(page, "/");
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 30_000,
    });
  });
});
