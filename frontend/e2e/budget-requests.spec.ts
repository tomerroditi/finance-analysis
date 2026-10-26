import { test, expect, request, type Page } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * What the budget screens ask the server for.
 *
 * - A month's neighbours are prefetched, but never a month after the current
 *   one: the first read of an empty future month auto-fills it (a write).
 *   The dashboard card used to prefetch eleven months at once on mount.
 * - `/budget/analysis` lists each row once: the Total Budget entry sends no
 *   rows of its own, and "View month transactions" shows the union of the
 *   other rules' rows.
 * - The Overview reads its attention rows off the month's analysis instead
 *   of asking `/budget/alerts` for the same rules again.
 */

const now = new Date();
const currentIndex = now.getFullYear() * 12 + now.getMonth();

/** Every `/budget/analysis/{y}/{m}` the page requests, as month indexes. */
function trackAnalysisMonths(page: Page): number[] {
  const months: number[] = [];
  page.on("request", (req) => {
    const match = new URL(req.url()).pathname.match(/\/budget\/analysis\/(\d+)\/(\d+)$/);
    if (match) months.push(Number(match[1]) * 12 + Number(match[2]) - 1);
  });
  return months;
}

test.describe("budget requests", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("the Monthly tab prefetches past neighbours only, and lists each row once", async ({ page }) => {
    const months = trackAnalysisMonths(page);
    const alerts: string[] = [];
    page.on("request", (req) => {
      if (new URL(req.url()).pathname.includes("/budget/alerts/")) alerts.push(req.url());
    });

    // --- Overview: attention rows come from the analysis, not /alerts ---------
    await navigateTo(page, "/budget");
    await expect(page.getByText(/^Spent$/).first()).toBeVisible({ timeout: 30_000 });

    // --- Monthly: the viewed month, then its past neighbours, one at a time --
    await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
    await expect(page.getByTestId("budget-status-band")).toBeVisible({ timeout: 30_000 });
    await expect
      .poll(() => new Set(months).size, { timeout: 15_000 })
      .toBeGreaterThanOrEqual(3);
    await page.waitForLoadState("networkidle");
    expect(months.filter((index) => index > currentIndex)).toEqual([]);
    expect(new Set(months)).toEqual(
      new Set([currentIndex, currentIndex - 1, currentIndex - 2]),
    );
    expect(alerts.filter((url) => !url.includes("/alerts/current"))).toEqual([]);

    // --- the month's list is the union of the rules' rows --------------------
    const ctx = await request.newContext({ extraHTTPHeaders: { "X-FAD-Demo": "1" } });
    const res = await ctx.get(
      `${API_BASE}/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`,
    );
    const body = (await res.json()) as {
      rules: { rule: { name: string }; data: unknown[] }[];
      uncategorized_count: number;
    };
    await ctx.dispose();
    const total = body.rules.find((r) => r.rule.name === "Total Budget")!;
    expect(total.data).toEqual([]);
    expect(typeof body.uncategorized_count).toBe("number");
    const listed = body.rules
      .filter((r) => r !== total)
      .reduce((sum, r) => sum + r.data.length, 0);
    expect(listed).toBeGreaterThan(0);

    await page.getByRole("button", { name: "View month transactions" }).click();
    await expect(
      page.getByTestId("budget-status-band").locator("tr[data-testid^='transaction-row-']").first(),
    ).toBeVisible();
  });

  test("the dashboard card prefetches past neighbours one at a time, not eleven months", async ({ page }) => {
    const months = trackAnalysisMonths(page);
    await navigateTo(page, "/");
    const card = page.getByTestId("dashboard-budget-tabs");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await card.getByRole("button", { name: /monthly/i }).first().click();
    await expect.poll(() => new Set(months).size, { timeout: 30_000 }).toBeGreaterThanOrEqual(3);
    await page.waitForLoadState("networkidle");

    expect(months.filter((index) => index > currentIndex)).toEqual([]);
    expect(new Set(months).size).toBeLessThanOrEqual(3);
  });
});
