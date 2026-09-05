import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Retirement readiness ladder.
 *
 * Readiness is four states, gated on solvency: running out of money is the
 * only real failure. `funded` covers a plan that never reaches the FIRE
 * number but never depletes either — the FIRE number assumes the portfolio
 * funds 100% of retirement spending forever and never nets out pension /
 * Bituach Leumi, so a plan those carry for life is solvent without ever
 * hitting ~28x expenses.
 *
 * Each case needs its own projections payload, so these stub the API with
 * `page.route()` before load rather than driving the calculator form.
 */

function projectionSeries(depleting: boolean) {
  const points = [];
  for (let age = 35; age <= 90; age++) {
    const value = depleting
      ? 900_000 - (age - 35) * 40_000
      : 300_000 + (age - 35) * 12_000;
    points.push({
      age,
      net_worth_optimistic: Math.round(value * 1.1),
      net_worth_baseline: Math.round(value),
      net_worth_conservative: Math.round(value * 0.9),
    });
  }
  return points;
}

function stubProjections(
  page: Page,
  readiness: string,
  { depleting }: { depleting: boolean },
) {
  const series = projectionSeries(depleting);
  return page.route("**/api/retirement/projections", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        fire_number: 2_742_857,
        years_to_fire: -1,
        fire_age: -1,
        earliest_possible_retirement_age: -1,
        monthly_savings_needed: 4200,
        progress_pct: 32.1,
        readiness,
        portfolio_depleted_age: depleting ? 57 : null,
        target_retirement_age: 67,
        full_pension_age: 67,
        net_worth_projection: series,
        income_projection: series.map((p) => ({
          age: p.age,
          salary_savings: 0,
          portfolio_withdrawal: 0,
          pension: 9000,
          bituach_leumi: 2800,
          passive_income: 0,
          total_income: 11800,
          expenses: 8000,
        })),
      }),
    }),
  );
}

test.describe("Retirement readiness", () => {
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  // Regression: a plan that never reaches the FIRE number fell through to
  // off_track even when the portfolio never depleted, so a pension-carried
  // plan that always has money in it was reported as a failure.
  test("a solvent plan that never reaches FIRE reads as funded, not off track", async ({
    page,
  }) => {
    await stubProjections(page, "funded", { depleting: false });
    await navigateTo(page, "/early-retirement");

    await expect(page.getByText("Funded for Life").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Off Track")).toHaveCount(0);

    // --- the info icon explains what this state means ---
    // Tap (not hover) so the assertion also covers touch, where the
    // hover-only variant of this tooltip would be unreachable.
    await page
      .getByText("Readiness", { exact: true })
      .first()
      .locator("xpath=..")
      .getByRole("button", { name: /More info/i })
      .click();
    await expect(
      page.getByText(/pension and Bituach Leumi carry your retirement/i),
    ).toBeVisible();
  });

  test("a depleting plan still reads as off track", async ({ page }) => {
    await stubProjections(page, "off_track", { depleting: true });
    await navigateTo(page, "/early-retirement");

    await expect(page.getByText("Off Track").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText("Funded for Life")).toHaveCount(0);
  });
});
