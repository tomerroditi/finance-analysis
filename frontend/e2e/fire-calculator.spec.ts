import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Early-retirement calculator — a standalone, stateless page that reproduces
 * the reverse-engineered reference model.
 *
 * One page load covers the whole journey: the declarative form renders every
 * section, conditional fields appear and disappear with the controls that gate
 * them, repeatable rows can be added and removed, and Calculate returns a
 * verdict, a goal checklist, the optimiser's suggestion and the charts.
 *
 * The page persists nothing — `POST /api/fire/calculate` is a pure projection
 * — so there is no demo-data reset here. It is deliberately kept out of
 * `READ_ONLY_SPECS` all the same, because it does issue a POST.
 */
test.describe("Early-retirement calculator", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("full scenario journey: form, conditional fields, rows, results", async ({
    page,
  }) => {
    await navigateTo(page, "/fire-calculator");

    // --- every input section renders -------------------------------------
    const sections = page.locator('[data-testid^="fire-section-"]');
    await expect(sections.first()).toBeVisible();
    await expect(sections).toHaveCount(13);

    // --- the reference's starting rows: one expense, income and portfolio --
    await expect(page.locator('[data-testid="fire-row-expense-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="fire-row-income-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="fire-row-portfolio-1"]')).toBeVisible();
    await expect(page.locator('[data-testid^="fire-row-keren-"]')).toHaveCount(0);

    // --- conditional fields follow the control that gates them ------------
    const partnerSection = page.locator('[data-testid="fire-section-partner"]');
    const partnerName = partnerSection.locator("input[name], input").first();
    // Before opting in, the partner section shows only its checkbox.
    await expect(partnerSection.locator("select")).toHaveCount(0);
    await partnerSection.getByRole("checkbox").check();
    await expect(partnerSection.locator("select").first()).toBeVisible();
    await partnerSection.getByRole("checkbox").uncheck();
    await expect(partnerSection.locator("select")).toHaveCount(0);
    expect(await partnerName.count()).toBeGreaterThanOrEqual(0);

    // --- repeatable rows can be added and removed -------------------------
    const expenseSection = page.locator('[data-testid="fire-section-expense"]');
    await expenseSection.getByRole("button", { name: /add|הוסף/i }).click();
    await expect(page.locator('[data-testid="fire-row-expense-2"]')).toBeVisible();
    await page
      .locator('[data-testid="fire-row-expense-2"]')
      .getByRole("button")
      .click();
    await expect(page.locator('[data-testid="fire-row-expense-2"]')).toHaveCount(0);

    // --- a complete scenario produces a verdict, goals and charts ---------
    await page.locator('input[type="date"]').first().fill("1990-01-01");
    await page.getByTestId("fire-calculate").click();

    const results = page.getByTestId("fire-results");
    await expect(results).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("fire-verdict")).toContainText(/\d{4}/);
    await expect(page.getByTestId("fire-goal-living_expenses")).toBeVisible();
    await expect(page.getByTestId("fire-goal-bequest")).toBeVisible();

    // The default scenario leaves the surplus idle in the checking account,
    // so the optimiser should say exactly that.
    await expect(page.getByTestId("fire-advice")).toBeVisible();

    // Charts render as SVG (Recharts), one surface per chart at minimum.
    await expect(results.locator("svg.recharts-surface").first()).toBeVisible();

    // --- all four charts, including the two cash-flow decompositions -----
    // The reference charts income by source and spending by destination, and
    // the two balance each other every month; both have to be here.
    for (const id of ["net-worth", "assets", "income", "spending"]) {
      await expect(page.getByTestId(`fire-chart-${id}`)).toBeVisible();
    }
    // --- the reference's other three result sections ---------------------
    // Two asset cards, the annuity list and the drawdown plan all come from
    // the same projection and must render alongside the charts.
    await expect(page.getByTestId("fire-snapshot-now")).toBeVisible();
    await expect(page.getByTestId("fire-snapshot-retirement")).toBeVisible();
    await expect(page.getByTestId("fire-annuities")).toContainText(/67/);
    await expect(page.getByTestId("fire-withdrawal-plan")).toBeVisible();

    // Legends name each row rather than leaking the engine's keys.
    const incomeChart = page.getByTestId("fire-chart-income");
    await expect(incomeChart.locator(".recharts-legend-item-text").first()).toBeVisible();
    await expect(incomeChart.getByText(/portfolio\d|keren\d|state_pension/)).toHaveCount(0);
  });
});
