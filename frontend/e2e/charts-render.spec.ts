import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";
/**
 * Smoke-guard: every chart-bearing page must hydrate its Recharts figures.
 * (Successor of the old lazy-plotly spec — Plotly and its lazy-loading path
 * were removed; Recharts renders synchronously in the main bundle.)
 */
test.describe("Charts render", () => {
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
    test(`renders charts on the ${name} page`, async ({ page }) => {
      await navigateTo(page, path);
      // Generous timeout: the dev server compiles the route chunk on first
      // hit, which can take a while on slow CI/sandbox machines.
      await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
        timeout: 30_000,
      });
    });
  }
});
