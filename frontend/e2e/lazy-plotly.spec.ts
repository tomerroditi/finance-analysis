import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";
/**
 * Plotly is code-split out of the main bundle (components/common/LazyPlot.tsx)
 * and loaded on demand when the first chart mounts. These tests guard the
 * lazy-loading path: charts on every Plotly-using page must still hydrate
 * from the Suspense skeleton into a rendered figure.
 */
test.describe("Lazy-loaded Plotly charts", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
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
      // resolves and the Suspense fallback is replaced. The dev server
      // serves the chunk unminified, so its first cold fetch+eval can take
      // tens of seconds on slow CI/sandbox machines — hence the generous
      // timeout.
      await expect(page.locator(".js-plotly-plot").first()).toBeVisible({
        timeout: 45_000,
      });
    });
  }
});
