import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle } from "./helpers";

/**
 * One navigation covers the page smoke, the classified cost figures and the
 * compacted covers block. The covers list used to live in the metrics grid,
 * where one row per cover set the grid's height and bloated the whole card;
 * it now sits in a footer section sharing an expansion slot with Deposit
 * History.
 */
test.describe("Insurances", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("classifies statement costs and keeps the covers block compact", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await navigateTo(page, "/insurances");
    await expectPageTitle(page, /Insurance/);

    const summary = page.getByTestId("insurance-covers-summary").first();
    await expect(summary).toBeVisible({ timeout: 15_000 });

    // --- costs are classified, not summed ---
    // PN-DEMO-001's statement: risk 1,440 + 690 = 2,130; fee 820. A blind
    // Σ|amount| over the eight rows would read 666,140.
    const riskCost = page.getByTestId("insurance-risk-cost").first();
    await expect(riskCost).toContainText("2,130");
    await expect(riskCost).not.toContainText("666,140");
    await expect(page.getByTestId("insurance-mgmt-fee").first()).toContainText("820");

    // --- the covers tile shows a headline, not a list ---
    await expect(summary).toContainText("Disability Insurance");
    // Collapsed, no cover row exists anywhere: the cover count can no longer
    // influence the card's resting height.
    await expect(page.getByTestId("insurance-cover-row")).toHaveCount(0);

    // The metrics grid must fit in a budget the old six-row layout blew past.
    const gridHeight = await summary.evaluate(
      (el) => el.parentElement!.getBoundingClientRect().height,
    );
    // Budget, not a measurement: the old six-row layout ran ~200px+. If the
    // real value lands within ~15px of this ceiling, raise the ceiling rather
    // than shaving the design to fit it.
    expect(gridHeight).toBeLessThan(160);

    // --- expanding reveals every cover, with its description ---
    await page.getByTestId("insurance-covers-toggle").first().click();
    const rows = page.getByTestId("insurance-cover-row");
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(1);
    await expect(rows.first()).toContainText("75% of salary");

    // --- opening deposits closes covers, so the card never doubles ---
    await page.getByTestId("insurance-deposits-toggle").first().click();
    await expect(page.getByTestId("insurance-cover-row")).toHaveCount(0);
  });
});
