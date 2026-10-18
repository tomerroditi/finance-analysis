import { test, expect } from "@playwright/test";
import { enableDemoMode, resetDemoData } from "./helpers";

/**
 * The former single tabbed "Charts & analytics" panel became independent
 * dashboard cards. Income & Expenses + Net Worth ship visible. The Cash Flow
 * (Sankey) card was retired; a layout that still names it simply drops it.
 * Each card is reorderable/hideable via Settings → Dashboard like any other.
 *
 * One dashboard load covers the default card set and the Hidden-cards badge
 * rules — the cold dashboard boot is the expensive step.
 */
test.describe("Dashboard per-chart cards", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test.beforeEach(async ({ page }) => {
    // Start from a clean (default) layout.
    await page.addInitScript(() =>
      window.localStorage.removeItem("fa.dashboard.layout"),
    );
  });

  test("default cards and the Hidden-cards badges on one load", async ({
    page,
  }) => {
    await page.goto("/");

    // Income & Expenses and Net Worth render as separate cards by default;
    // the retired Cash Flow card is gone.
    await expect(page.locator('[data-card-id="income_expenses"]')).toBeVisible({
      timeout: 45_000,
    });
    await expect(page.locator('[data-card-id="net_worth"]')).toBeVisible();
    await expect(page.locator('[data-card-id="cash_flow"]')).toHaveCount(0);

    // --- Net Worth → Debt Payments draws monthly bars + an outstanding-debt line ---
    // Like the per-series views: one stacked bar per loan tag (the demo has a
    // mortgage and a car loan) and an "Outstanding Debt" line.
    const netWorthCard = page.locator('[data-card-id="net_worth"]');
    await netWorthCard.scrollIntoViewIfNeeded();
    await netWorthCard.getByRole("button", { name: /^Debt Payments$/ }).click();
    const netWorthChart = netWorthCard.getByTestId("net-worth-chart");
    await expect(netWorthChart.locator(".recharts-bar-rectangle").first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(netWorthChart.locator(".recharts-bar")).toHaveCount(2);
    await expect(netWorthChart.locator(".recharts-line")).toHaveCount(1);
    // The debt line reads the liabilities' balances, so it must draw a path.
    await expect(netWorthChart.locator(".recharts-line-curve")).toHaveAttribute("d", /\d/);
    await expect(netWorthChart.locator(".recharts-area")).toHaveCount(0);
    await expect(netWorthChart.getByText("Outstanding Debt").first()).toBeVisible();

    await page
      .getByRole("button", { name: /^Settings$/ })
      .first()
      .click();
    await page.getByRole("button", { name: /^Dashboard$/ }).click();

    // A default-hidden card that is not beta (Early Retirement) carries no
    // Beta pill; the forecast card, which is beta, does.
    // Rows are matched by their show button, since the sidebar also names
    // "Early Retirement".
    await expect(page.getByText("Hidden cards", { exact: true })).toBeVisible();
    const hiddenRows = page.locator("div").filter({
      has: page.getByRole("button", { name: "Show card" }),
      hasNot: page.locator("div"),
    });
    const retirementRow = hiddenRows.filter({ hasText: "Early Retirement" });
    await expect(retirementRow).toHaveCount(1);
    await expect(retirementRow.getByText(/^Beta$/i)).toHaveCount(0);
    const forecastRow = hiddenRows.filter({ hasText: "This Month (forecast)" });
    await expect(forecastRow.getByText(/^Beta$/i)).toBeVisible();

    // The retired Cash Flow card is not offered any more.
    await expect(hiddenRows.filter({ hasText: "Cash Flow" })).toHaveCount(0);
    await expect(page.getByText("Cash Flow", { exact: true })).toHaveCount(0);
  });
});
