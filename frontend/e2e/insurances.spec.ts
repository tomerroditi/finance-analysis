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

    // --- the detector is quiet when every deduction is recognised ---
    // `insurance-unclassified` renders only for negative statement rows that
    // matched no bucket. Zero of them across the demo data is the assertion:
    // if a key ever stops matching, the classified figures above go quiet and
    // this line appears instead of nothing at all. Safe as a count-0 check —
    // the card is already rendered (the two assertions above waited on it).
    await expect(page.getByTestId("insurance-unclassified")).toHaveCount(0);

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

  /**
   * Its own test because it needs a `page.route()` stub in place before the
   * page boots — it cannot join the journey above, which has already loaded.
   * No backend write happens, so the spec stays in READ_ONLY_SPECS.
   */
  test("surfaces a renamed risk-cost row instead of showing no cost at all", async ({
    page,
  }) => {
    // The real regression this guards: the provider restyles a statement row
    // title, every risk key stops matching, and the card would otherwise just
    // drop its red line — indistinguishable from a policy with no risk cover.
    await page.route("**/api/insurance-accounts/", async (route) => {
      const response = await route.fetch();
      const accounts = await response.json();
      for (const account of accounts) {
        if (typeof account.insurance_costs === "string") {
          account.insurance_costs = account.insurance_costs.replaceAll(
            "risk cost",
            "risk charge",
          );
        }
      }
      await route.fulfill({ response, json: accounts });
    });

    await navigateTo(page, "/insurances");

    // 1,440 + 690, now unrecognised — reported as money we could not name.
    const unclassified = page.getByTestId("insurance-unclassified").first();
    await expect(unclassified).toBeVisible({ timeout: 15_000 });
    await expect(unclassified).toContainText("2,130");
    // The classified line is genuinely gone; the amber line is what replaces it.
    await expect(page.getByTestId("insurance-risk-cost")).toHaveCount(0);
    // The unmatched *positive* rows (balances, deposits, gains) stay excluded.
    await expect(unclassified).not.toContainText("666,140");
  });
});
