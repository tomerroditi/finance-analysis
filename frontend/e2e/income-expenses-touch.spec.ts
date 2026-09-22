import { test, expect, type Page, type Locator } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * The Income & Expenses breakdown on a touch device.
 *
 * A phone has no hover: the browser synthesizes the mouse events and the click
 * from one tap, so a slice that filtered on click could never be *read* — the
 * readout naming it would be replaced by the filtered view in the same
 * gesture. A tap therefore pins the readout, and filtering is a second,
 * deliberate tap on a button inside it. The all-scope donut takes the same
 * problem from the other side (a tap is also what opens Recharts' own
 * tooltip), so there the slices are not clickable at all and the legend —
 * open by default on touch — carries every amount and the filter.
 *
 * This lives in its own file rather than as a block in `income-expenses-card`
 * because it needs a touch-capable mobile context, which must be configured
 * before the page boots. It performs no backend writes.
 */
test.describe("Income & Expenses on touch", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  async function openCard(page: Page): Promise<Locator> {
    await navigateTo(page, "/");
    const card = page.locator('[data-card-id="income_expenses"]');
    await expect(card).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();
    await expect(
      card.getByRole("heading", { name: "Income & Expenses" }),
    ).toBeVisible({ timeout: 45_000 });
    return card;
  }

  test("a tap reads a slice; only the readout's button filters", async ({ page }) => {
    const card = await openCard(page);
    await card.getByRole("button", { name: "Expenses Breakdown" }).click();

    const segments = card
      .getByTestId("composition-row")
      .first()
      .getByTestId("composition-segment");
    await expect(segments.first()).toBeVisible({ timeout: 45_000 });

    // --- The first tap names the slice instead of filtering ---
    const label = await segments.first().getAttribute("aria-label");
    await segments.first().tap();

    const tooltip = page.getByTestId("composition-tooltip");
    await expect(tooltip).toBeVisible();
    // Amount and share, which is the whole reason a tap must not navigate.
    await expect(tooltip).toHaveText(/.+: .*\d.*\(\d+%\)/);
    await expect(card.getByTestId("series-focus-row")).toHaveCount(0);

    // --- Tapping off it dismisses it, still without filtering ---
    await page.getByTestId("composition-tooltip-backdrop").tap();
    await expect(tooltip).toHaveCount(0);
    await expect(card.getByTestId("series-focus-row")).toHaveCount(0);

    // --- The button inside the readout is what filters ---
    await segments.first().tap();
    await page.getByTestId("composition-tooltip-filter").tap();
    await expect(card.getByTestId("series-focus-row").first()).toBeVisible({
      timeout: 45_000,
    });
    await expect(card.getByTestId("series-focus-chip")).toContainText(
      label!.split(":")[0],
    );
    // The readout goes away with the view it belonged to.
    await expect(tooltip).toHaveCount(0);

    await card.getByTestId("series-focus-chip").tap();
    await expect(card.getByTestId("composition-row").first()).toBeVisible();
  });

  test("the all-time donut leads with its legend and filters from a row", async ({
    page,
  }) => {
    const card = await openCard(page);
    await card.getByTestId("scope-toggle").getByRole("button", { name: "All time" }).tap();
    await card.getByRole("button", { name: "Income Breakdown" }).tap();

    await expect(card.getByTestId("donut-chart")).toBeVisible({ timeout: 45_000 });

    // Open by default here: a tap cannot filter a slice on touch, so the
    // legend is the only place a phone can read the figures or reach a series.
    const legendRows = card.getByTestId("breakdown-legend-row");
    await expect(legendRows.first()).toBeVisible({ timeout: 45_000 });
    await expect(card.getByTestId("breakdown-legend-scroll")).toContainText("100.0%");

    // A slice is inert here — it must not filter (a tap is also what opens
    // the chart's own tooltip), or the donut would navigate away from the
    // reading it just produced. The chart layer only carries a pointer cursor
    // when it has a click handler, so that is what says whether it does.
    const slice = card.locator(".recharts-sector").first();
    await expect(slice).toBeVisible();
    expect(
      await slice.evaluate((el) => getComputedStyle(el).cursor),
    ).not.toBe("pointer");

    // The legend row is the filter.
    await legendRows.first().tap();
    await expect(card.getByTestId("series-focus-row").first()).toBeVisible({
      timeout: 45_000,
    });
  });
});
