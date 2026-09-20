import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

test.describe("Bar chart hover shows the tooltip without the cursor rectangle", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("hovering a net-worth bar shows only the data tooltip, no grey highlight", async ({
    page,
  }) => {
    // The dashboard's Net Worth card is the reference BarChart for this guard.
    // It was the budget page's trend chart, which has since been replaced by
    // an inline SVG figure in the budget summary band.
    await navigateTo(page, "/");

    // The card mounts lazily, well below the fold.
    const card = page.locator('[data-card-id="net_worth"]');
    await expect(card).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();
    await expect(card.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 45_000,
    });

    // The default "All" view is a LineChart; the per-series views draw the
    // monthly-change bars this guard is about.
    await card.getByRole("button", { name: /^Net Worth$/ }).click();

    const bar = card.locator(".recharts-bar-rectangle, .recharts-rectangle").first();
    await expect(bar).toBeVisible({ timeout: 10_000 });

    // `hover()` rather than scroll-measure-move by hand. It ends in the same
    // real pointer move to the bar's centre, and scrolls it into view first
    // (mouse coordinates are viewport-relative, so a move computed against a
    // below-the-fold box never reaches the chart) — but it re-resolves the
    // element and retries when the node goes away mid-action. Recharts
    // replaces its <rect> nodes on every re-render, so the hand-rolled
    // version raced: under CI load the bar was detached between the
    // visibility check and the scroll ("Element is not attached to the DOM").
    await bar.hover();

    // The data tooltip appears (positive anchor before the negative assertion,
    // so the cursor check can't pass vacuously against an un-hovered chart).
    await expect(card.locator(".recharts-tooltip-wrapper")).toBeVisible();

    // Recharts' default bar cursor (the grey/white rectangle behind the bar)
    // is disabled via ``cursor={false}`` on the <Tooltip>, so it must not
    // render even while the tooltip is showing.
    await expect(page.locator(".recharts-tooltip-cursor")).toHaveCount(0);
  });
});
