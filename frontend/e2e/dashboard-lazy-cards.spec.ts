import { test, expect } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Below-the-fold dashboard cards defer mounting (and their analytics requests)
 * until scrolled near the viewport, so the pinned KPI header and the top cards
 * own the first paint. Eager (above-the-fold) cards must still render on load;
 * a deferred chart card must mount its chart only after it scrolls in.
 */
test.describe("Dashboard lazy card mounting", () => {
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll. enableDemoMode's demo/prepare call is idempotent, so this
  // is still cheap and order-independent when sharded alongside mutating
  // specs.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
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

    // The eager cards render their own content without any scrolling — the
    // budget card's tab bar only exists once the card itself has mounted, so
    // it cannot be satisfied by the reserved placeholder.
    await expect(
      page.locator('[data-card-id="budget"] [data-testid="dashboard-budget-tabs"]'),
    ).toBeVisible({ timeout: 45_000 });

    // The trailing Net Worth card exists (placeholder reserves its height) but
    // has NOT mounted its chart yet — it's far below the fold.
    const netWorthCard = page.locator('[data-card-id="net_worth"]');
    await expect(netWorthCard).toBeVisible();
    await expect(netWorthCard.locator(".recharts-wrapper")).toHaveCount(0);

    // Scroll it into view — now it mounts and renders its chart.
    await netWorthCard.scrollIntoViewIfNeeded();
    await expect(netWorthCard.locator(".recharts-wrapper").first()).toBeVisible(
      {
        timeout: 45_000,
      },
    );
  });
});
