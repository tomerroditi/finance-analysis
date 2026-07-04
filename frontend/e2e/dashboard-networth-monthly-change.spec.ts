import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

// A "MMM yyyy" month-row label, e.g. "Jul 2026" — rendered only inside the
// expanded Net Worth card's per-month change breakdown.
const MONTH_ROW = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+20\d{2}\b/;

test.describe("Dashboard net worth monthly change", () => {
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

  test("expanding the KPI cards reveals the last-3-months net worth change with percent", async ({ page }) => {
    await page.goto("/");

    // "Cash Balance" is text unique to the pinned KPI header (the chart filter
    // chips read Bank Balance / Investment Value / Net Worth / Debt Payments,
    // never "Cash Balance"). Waiting on it guarantees the header finished
    // loading before we interact — otherwise the still-skeleton header would
    // let a locator resolve to a same-named chart tab further down the page.
    const cashBalanceLabel = page.getByText("Cash Balance", { exact: true });
    await expect(cashBalanceLabel).toBeVisible({ timeout: 45_000 });

    // Scope to the Net Worth KPI card via its label's card ancestor.
    const netWorthCard = page
      .getByText("Net Worth", { exact: true })
      .first()
      .locator("xpath=ancestor::*[contains(@class,'rounded-xl')][1]");

    // Collapsed: no per-month breakdown rows yet.
    await expect(netWorthCard).not.toContainText(MONTH_ROW);

    // The whole KPI grid is one click target that toggles the breakdowns.
    const kpiGrid = cashBalanceLabel.locator(
      "xpath=ancestor::*[contains(@class,'cursor-pointer')][1]",
    );
    await kpiGrid.click();

    // Expanded: the Net Worth card lists up to three month rows, each with a
    // signed currency delta and a percentage in parentheses.
    await expect(netWorthCard).toContainText(MONTH_ROW);
    await expect(netWorthCard).toContainText(/[+-].*%\)/);

    // Collapsing hides the breakdown again.
    await kpiGrid.click();
    await expect(netWorthCard).not.toContainText(MONTH_ROW);
  });
});
