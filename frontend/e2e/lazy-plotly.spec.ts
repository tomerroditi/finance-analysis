import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * Plotly is code-split out of the main bundle (components/common/LazyPlot.tsx)
 * and loaded on demand when the first chart mounts. These tests guard the
 * lazy-loading path: charts on every Plotly-using page must still hydrate
 * from the Suspense skeleton into a rendered figure.
 */
test.describe("Lazy-loaded Plotly charts", () => {
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

  const pagesWithCharts: [string, string][] = [
    ["dashboard", "/"],
    ["budget", "/budget"],
    ["investments", "/investments"],
    ["liabilities", "/liabilities"],
  ];

  for (const [name, path] of pagesWithCharts) {
    test(`renders Plotly charts on the ${name} page`, async ({ page }) => {
      await navigateTo(page, path);
      // Plotly renders into div.js-plotly-plot only after the lazy chunk
      // resolves and the Suspense fallback is replaced.
      await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
        timeout: 15_000,
      });
    });
  }
});
