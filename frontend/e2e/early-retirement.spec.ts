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
    // The partner's pension appears only once a partner is included.
    await expect(sections).toHaveCount(12);
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
    const partnerPension = page.getByTestId("fire-section-partnerPension");
    await expect(partnerPension).toHaveCount(0);
    await partnerSection.getByRole("checkbox").check();
    await expect(partnerSection.locator("select").first()).toBeVisible();
    await expect(partnerPension).toBeVisible();
    await partnerSection.getByRole("checkbox").uncheck();
    await expect(partnerSection.locator("select")).toHaveCount(0);
    await expect(partnerPension).toHaveCount(0);

    // As on the reference, the maximum age belongs to "retire ASAP" alone.
    const problem = page.getByTestId("fire-section-problem");
    const hint = page.getByTestId("fire-hint-problem");
    const asapHint = await hint.textContent();
    await problem.locator("select").first().selectOption("retire_at_age");
    await expect(page.getByTestId("fire-help-base_problem_max_age")).toHaveCount(0);
    await expect(page.getByTestId("fire-help-wanted_retire_age")).toBeVisible();
    await expect(hint).not.toHaveText(asapHint ?? "");
    await problem.locator("select").first().selectOption("retire_asap");
    await expect(page.getByTestId("fire-help-base_problem_max_age")).toBeVisible();

    // --- every field explains itself behind an info icon ------------------
    const help = page.getByTestId("fire-help-balance");
    await help.getByRole("button").click();
    const panel = help.getByTestId("info-tooltip-panel");
    await expect(panel).toHaveCSS("opacity", "1");
    await expect(panel).toContainText(/checking account|עובר ושב/);

    // --- a one-time row asks for a date and an amount, nothing more -------
    const expenses = page.locator('[data-testid^="fire-row-expense-"]');
    const expenseRows = await expenses.count();
    const added = expenseRows + 1;
    await page
      .getByTestId("fire-section-expense")
      .getByRole("button", { name: /add|הוסף/i })
      .click();
    const oneTime = page.getByTestId(`fire-row-expense-${added}`);
    await expect(page.getByTestId(`fire-help-expenseEndType${added}`)).toBeVisible();
    await oneTime.locator("select").first().selectOption("one_time");
    await expect(page.getByTestId(`fire-help-expenseStartDate${added}`)).toBeVisible();
    await expect(page.getByTestId(`fire-help-expenseEndType${added}`)).toHaveCount(0);
    await expect(page.getByTestId(`fire-help-expenseRise${added}`)).toHaveCount(0);
    await page.getByTestId(`fire-remove-expense-${added}`).click();
    await expect(expenses).toHaveCount(expenseRows);

    // --- portfolios can be reordered: the order is the fill/draw order ----
    const portfolios = page.locator('[data-testid^="fire-row-portfolio-"]');
    const last = (await portfolios.count()) + 1;
    await page
      .getByTestId("fire-section-portfolio")
      .getByRole("button", { name: /add|הוסף/i })
      .click();
    const balanceOf = (row: number) =>
      page.getByTestId(`fire-row-portfolio-${row}`).getByLabel(/^(Balance|יתרה)$/);
    await balanceOf(last).fill("4242");
    await expect(page.getByTestId(`fire-move-down-portfolio-${last}`)).toBeDisabled();
    await page.getByTestId(`fire-move-up-portfolio-${last}`).click();
    await expect(balanceOf(last - 1)).toHaveValue("4242");
    await page.getByTestId(`fire-remove-portfolio-${last - 1}`).click();
    await expect(portfolios).toHaveCount(last - 1);

    // --- repeatable rows can be added and removed -------------------------
    const realEstate = page.locator('[data-testid="fire-section-realestate"]');
    await realEstate.getByRole("button", { name: /add|הוסף/i }).click();
    await expect(page.locator('[data-testid="fire-row-realestate-1"]')).toBeVisible();
    await page.getByTestId("fire-remove-realestate-1").click();
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
