import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";

/**
 * One navigation covers the page smoke and the responsive layout of the
 * Insurance Covers panel: side-by-side rows on wide screens (so a policy
 * with many covers no longer stretches the whole account card), stacked
 * label-over-amount below xl, where the 4-column grid leaves a cover title
 * too little room to stay readable on one line.
 */
test.describe("Insurances", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("renders account cards with a compact insurance-covers panel", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await navigateTo(page, "/insurances");
    await expectPageTitle(page, /Insurance/);

    const rows = page.getByTestId("insurance-cover-row");
    await expect(rows.first()).toBeVisible({ timeout: 15_000 });

    // --- wide: title and amount share one line ---
    const wideRow = rows.first();
    const [wideTitle, wideAmount] = await Promise.all([
      wideRow.locator("span").first().boundingBox(),
      wideRow.locator("span").last().boundingBox(),
    ]);
    expect(wideTitle).not.toBeNull();
    expect(wideAmount).not.toBeNull();
    expect(Math.abs(wideTitle!.y - wideAmount!.y)).toBeLessThan(4);

    // The title must not be clipped at this width — truncation is what the
    // stacked fallback below xl exists to avoid.
    const clipped = await wideRow
      .locator("span")
      .first()
      .evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    expect(clipped).toBe(false);

    // --- narrow: the amount drops under its label ---
    await page.setViewportSize({ width: 1024, height: 800 });
    const narrowRow = rows.first();
    await expect(narrowRow).toBeVisible();
    const [narrowTitle, narrowAmount] = await Promise.all([
      narrowRow.locator("span").first().boundingBox(),
      narrowRow.locator("span").last().boundingBox(),
    ]);
    expect(narrowAmount!.y).toBeGreaterThan(narrowTitle!.y + 4);
  });
});
