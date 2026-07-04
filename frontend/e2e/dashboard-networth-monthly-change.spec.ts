import { test, expect } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

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

  test("expanding the KPI cards reveals the last-3-months net worth change", async ({ page }) => {
    await page.goto("/");

    // "Cash Balance" is text unique to the pinned KPI header (the chart filter
    // chips read Bank Balance / Investment Value / Net Worth / Debt Payments,
    // never "Cash Balance"). Waiting on it guarantees the header finished
    // loading before we interact — otherwise the still-skeleton header would
    // let a locator resolve to a same-named chart tab further down the page.
    const cashBalanceLabel = page.getByText("Cash Balance", { exact: true });
    await expect(cashBalanceLabel).toBeVisible({ timeout: 45_000 });

    // The whole KPI grid is one click target that toggles the expanded
    // breakdowns; the monthly-change block is hidden until then.
    const kpiGrid = cashBalanceLabel.locator(
      "xpath=ancestor::*[contains(@class,'cursor-pointer')][1]",
    );
    const monthlyChangeTitle = page.getByText(/Monthly Change \(last 3 months\)/i);
    await expect(monthlyChangeTitle).toHaveCount(0);

    await kpiGrid.click();
    await expect(monthlyChangeTitle).toBeVisible();

    // The Net Worth card lists up to three month rows once expanded; each row
    // carries a signed (+/-) currency delta.
    const netWorthCard = monthlyChangeTitle.locator(
      "xpath=ancestor::*[contains(@class,'rounded-xl')][1]",
    );
    await expect(netWorthCard).toContainText(/[+-]/);

    // Collapsing hides the breakdown again.
    await kpiGrid.click();
    await expect(monthlyChangeTitle).toHaveCount(0);
  });
});
