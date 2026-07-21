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

  test("hovering a budget trend bar shows only the data tooltip, no grey highlight", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");

    // The monthly Budget view renders the trend BarChart.
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({
      timeout: 20_000,
    });
    const bar = page
      .locator(".recharts-bar-rectangle, .recharts-rectangle")
      .first();
    await expect(bar).toBeVisible({ timeout: 10_000 });

    // Hover the centre of the bar to open the tooltip.
    const box = await bar.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);

    // The data tooltip appears (positive anchor before the negative assertion,
    // so the cursor check can't pass vacuously against an un-hovered chart).
    const tooltip = page.locator(".recharts-tooltip-wrapper").first();
    await expect(tooltip).toBeVisible();

    // Recharts' default bar cursor (the grey/white rectangle behind the bar)
    // is disabled via ``cursor={false}`` on the <Tooltip>, so it must not
    // render even while the tooltip is showing.
    await expect(page.locator(".recharts-tooltip-cursor")).toHaveCount(0);
  });
});
