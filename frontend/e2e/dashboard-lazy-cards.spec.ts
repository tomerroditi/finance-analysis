import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Below-the-fold dashboard cards defer mounting (and their analytics requests)
 * until scrolled near the viewport, so the pinned KPI header and the top cards
 * own the first paint. Eager (above-the-fold) cards must still render on load;
 * a deferred chart card must mount its Plotly chart only after it scrolls in.
 */
test.describe("Dashboard lazy card mounting", () => {
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
    // Start from the default layout (income_expenses + net_worth visible last).
    await page.addInitScript(() =>
      window.localStorage.removeItem("fa.dashboard.layout"),
    );
  });

  test("top cards render eagerly; a bottom chart card mounts on scroll", async ({
    page,
  }) => {
    // A short viewport keeps the trailing chart cards well below the fold.
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");

    // The pinned KPI header is always eager.
    await expect(page.getByText(/Net Worth/i).first()).toBeVisible({
      timeout: 45_000,
    });

    // The first eager chart card (Income by source, row 2) renders its plot
    // without any scrolling.
    await expect(
      page.locator('[data-card-id="income_by_source"] .js-plotly-plot').first(),
    ).toBeVisible({ timeout: 45_000 });

    // The trailing Net Worth card exists (placeholder reserves its height) but
    // has NOT mounted its chart yet — it's far below the fold.
    const netWorthCard = page.locator('[data-card-id="net_worth"]');
    await expect(netWorthCard).toBeVisible();
    await expect(netWorthCard.locator(".js-plotly-plot")).toHaveCount(0);

    // Scroll it into view — now it mounts and renders its Plotly chart.
    await netWorthCard.scrollIntoViewIfNeeded();
    await expect(netWorthCard.locator(".js-plotly-plot").first()).toBeVisible({
      timeout: 45_000,
    });
  });
});
