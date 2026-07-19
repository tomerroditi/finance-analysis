import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";

/**
 * Investments page smoke + soft-gradient chart styling.
 *
 * All assertions are read-only checks against one rendered page, so they run
 * as a single test on a single navigation (the page load is the expensive
 * step — it used to be paid once per assertion group across three spec files:
 * investments, chart-styling, and the English half of info-tooltip).
 *
 * Chart-styling coverage (formerly chart-styling.spec.ts) locks in the
 * signature ingredients of the "soft gradient" look so a future refactor of
 * the shared theme/helpers can't silently revert them:
 *   1. charts still render after the restyle (regression guard),
 *   2. trend/area charts emit an SVG <linearGradient> (AreaGradientDef),
 *   3. allocation donuts show a center total (DonutChart centerLabel).
 */
test.describe("Investments", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  test("page renders cards, portfolio, closed toggle, donut total, tooltip label, and gradient chart", async ({
    page,
  }) => {
    await navigateTo(page, "/investments");
    await expectPageTitle(page, /Investments/);

    // Investment cards render with names.
    const cards = page.locator("[class*='rounded-2xl']");
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });

    // Portfolio section is visible, and the page hydrates its Recharts
    // figures (chart-render smoke, formerly charts-render.spec.ts).
    await expect(page.getByText(/Portfolio/i).first()).toBeVisible();
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 30_000,
    });

    // The allocation donut renders the formatted total (e.g. "… ₪") as an
    // HTML overlay inside the DonutChart wrapper.
    await expect(
      page.getByTestId("donut-chart").getByText(/₪/).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Demo investments carry `notes`, so the shared InfoTooltip renders. Its
    // accessible name must be the i18n value (`common.moreInfo` = "More
    // info"), never empty / a key leak. (The Hebrew half of this check lives
    // in info-tooltip-aria-label.spec.ts.)
    const infoButton = page.getByRole("button", { name: "More info" }).first();
    await expect(infoButton).toBeVisible({ timeout: 30_000 });
    await expect(infoButton).toHaveAttribute("aria-label", "More info");

    // Demo data always includes closed investments, so the section renders
    // unconditionally — assert it instead of skipping (the old conditional
    // body passed vacuously when the button was missing).
    await expect(page.getByText(/Closed Investments/i).first()).toBeVisible();

    // The balance-over-time chart's closed toggle defaults ON ("Hide
    // Closed") and flips its label per state.
    const hideToggle = page.getByRole("button", { name: "Hide Closed" });
    await expect(hideToggle).toBeVisible();
    await hideToggle.click();

    const includeToggle = page.getByRole("button", { name: "Include Closed" });
    await expect(includeToggle).toBeVisible();
    await includeToggle.click();
    await expect(hideToggle).toBeVisible();

    // The gradient area fill lives in the single-series balance chart inside
    // the Investment Analysis modal (multi-line charts keep clean lines).
    await page.getByRole("button", { name: /analysis/i }).first().click();
    const modalPlot = page.locator(".recharts-wrapper").last();
    await expect(modalPlot).toBeVisible({ timeout: 15_000 });

    // AreaGradientDef renders as an SVG <linearGradient> in the chart's <defs>
    // (a non-rendered node, so assert presence by count, not visibility).
    await expect(modalPlot.locator("defs linearGradient")).not.toHaveCount(0, {
      timeout: 15_000,
    });
  });
});
