import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * Early retirement — the user's plan in the reverse-engineered reference
 * calculator, filled from tracked data.
 *
 * The journey covers one load: the form arrives filled from the demo
 * household (cash, investments, keren hishtalmut, pension, loans, and the old
 * retirement goal's age and spending), linked fields and sourced rows are
 * marked, conditional fields and rows behave, and Calculate returns the
 * verdict, goals and charts. The second test writes: it edits a linked field,
 * saves, reloads, and resets.
 */
test.describe("Early retirement plan", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("filled from tracked data: sections, links, rows, results", async ({ page }) => {
    await navigateTo(page, "/early-retirement");

    // --- every input section renders, filled from the demo household ------
    const sections = page.locator('[data-testid^="fire-section-"]');
    await expect(sections.first()).toBeVisible();
    await expect(sections).toHaveCount(13);
    await expect(page.locator('[data-testid="fire-row-portfolio-1"]')).toBeVisible();
    await expect(page.locator('[data-testid^="fire-row-keren-"]')).toHaveCount(3);
    await expect(page.locator('[data-testid^="fire-row-loan-"]')).toHaveCount(3);
    await expect(page.getByTestId("fire-plan-unsaved")).toBeVisible();

    // --- tracked values are marked as following the data ------------------
    await expect(page.getByTestId("fire-linked-balance")).toBeVisible();
    await expect(page.getByTestId("fire-linked-pensionBalance")).toBeVisible();
    await expect(
      page.locator('[data-testid="fire-row-keren-1"]').getByText(/Keren|קרן/).first(),
    ).toBeVisible();

    // --- conditional fields follow the control that gates them ------------
    const partnerSection = page.locator('[data-testid="fire-section-partner"]');
    await expect(partnerSection.locator("select")).toHaveCount(0);
    await partnerSection.getByRole("checkbox").check();
    await expect(partnerSection.locator("select").first()).toBeVisible();
    await partnerSection.getByRole("checkbox").uncheck();
    await expect(partnerSection.locator("select")).toHaveCount(0);

    // --- repeatable rows can be added and removed -------------------------
    const realEstate = page.locator('[data-testid="fire-section-realestate"]');
    await realEstate.getByRole("button", { name: /add|הוסף/i }).click();
    await expect(page.locator('[data-testid="fire-row-realestate-1"]')).toBeVisible();
    await page.locator('[data-testid="fire-row-realestate-1"]').getByRole("button").click();
    await expect(page.locator('[data-testid="fire-row-realestate-1"]')).toHaveCount(0);

    // --- the plan's own projection, then a fresh calculation --------------
    await expect(page.getByTestId("fire-verdict")).toBeVisible({ timeout: 60_000 });
    await page.getByTestId("fire-calculate").click();
    await expect(page.getByTestId("fire-preview-note")).toBeVisible({ timeout: 60_000 });
    const results = page.getByTestId("fire-results");
    await expect(page.getByTestId("fire-goal-living_expenses")).toBeVisible();
    for (const id of ["net-worth", "assets", "income", "spending"]) {
      await expect(page.getByTestId(`fire-chart-${id}`)).toBeVisible();
    }
    await expect(page.getByTestId("fire-snapshot-now")).toBeVisible();
    await expect(page.getByTestId("fire-snapshot-retirement")).toBeVisible();
    await expect(results.locator("svg.recharts-surface").first()).toBeVisible();

    // Legends name each row rather than leaking the engine's keys.
    const incomeChart = page.getByTestId("fire-chart-income");
    await expect(incomeChart.locator(".recharts-legend-item-text").first()).toBeVisible();
    await expect(incomeChart.getByText(/portfolio\d|keren\d|state_pension/)).toHaveCount(0);
  });

  test("typing over a linked value unlinks it; save keeps it; reset restores it", async ({
    page,
  }) => {
    await navigateTo(page, "/early-retirement");
    const cash = page
      .locator('[data-testid="fire-section-cash"]')
      .getByRole("spinbutton")
      .nth(1);
    await expect(page.getByTestId("fire-linked-balance")).toBeVisible();
    const tracked = await cash.inputValue();

    await cash.fill("12345");
    await expect(page.getByTestId("fire-linked-balance")).toHaveCount(0);
    await expect(page.getByTestId("fire-relink-balance")).toBeVisible();

    await page.getByTestId("fire-plan-save").click();
    await expect(page.getByTestId("fire-plan-unsaved")).toHaveCount(0, { timeout: 30_000 });

    await page.reload();
    await expect(cash).toHaveValue("12345");
    await expect(page.getByTestId("fire-relink-balance")).toBeVisible();

    const resetButtons = page.getByRole("button", { name: /^(Reset|איפוס)$/ });
    await resetButtons.first().click();
    // The confirmation's own Reset is the last one on the page.
    await expect(resetButtons).toHaveCount(2);
    await resetButtons.last().click();
    await expect(cash).toHaveValue(tracked);
    await expect(page.getByTestId("fire-linked-balance")).toBeVisible();
  });
});
