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
    const requested: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/")) requested.push(req.url());
    });
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

    // --- The deferred cards wait for the first load, not just the fold ---
    // While the cards above were loading skeletons, the Income & Expenses
    // placeholder sat inside the observer's margin and fired its two heavy
    // requests with the first paint. Once the page has settled it is still
    // unrequested, because measured against the real layout it is far away.
    // Zero is the expected count here, so wait for the page to go quiet.
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    expect(requested.filter((url) => url.includes("expenses-by-category-over-time"))).toEqual([]);

    // --- The KPI header's breakdowns load when it is expanded ---
    expect(requested.filter((url) => url.includes("/api/bank-balances/"))).toEqual([]);
    const bankBalances = page.waitForRequest((req) => req.url().includes("/api/bank-balances/"));
    await page.getByTestId("health-kpis").click();
    await bankBalances;

    // Scroll it into view — now it mounts and renders its chart.
    await netWorthCard.scrollIntoViewIfNeeded();
    await expect(netWorthCard.locator(".recharts-wrapper").first()).toBeVisible(
      {
        timeout: 45_000,
      },
    );
  });
});
