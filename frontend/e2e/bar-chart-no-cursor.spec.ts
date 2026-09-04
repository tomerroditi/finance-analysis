import { test, expect, type Page } from "@playwright/test";
import { navigateTo } from "./helpers";

/**
 * Toggle Demo Mode through the frontend dev-server proxy (relative ``/api``)
 * so the toggle follows Playwright's ``baseURL`` and the Vite proxy.
 */
async function setDemoMode(page: Page, enabled: boolean) {
  const res = await page.request.post("/api/testing/toggle_demo_mode", {
    data: { enabled },
  });
  expect(res.ok()).toBeTruthy();
}

test.describe("Bar chart hover shows the tooltip without the cursor rectangle", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, true);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await setDemoMode(page, false);
    await page.close();
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

    // Scroll before measuring: mouse coordinates are viewport-relative, so a
    // move computed against a below-the-fold box never reaches the chart.
    await bar.scrollIntoViewIfNeeded();
    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);

    // The data tooltip appears (positive anchor before the negative assertion,
    // so the cursor check can't pass vacuously against an un-hovered chart).
    await expect(card.locator(".recharts-tooltip-wrapper")).toBeVisible();

    // Recharts' default bar cursor (the grey/white rectangle behind the bar)
    // is disabled via ``cursor={false}`` on the <Tooltip>, so it must not
    // render even while the tooltip is showing.
    await expect(page.locator(".recharts-tooltip-cursor")).toHaveCount(0);
  });
});
