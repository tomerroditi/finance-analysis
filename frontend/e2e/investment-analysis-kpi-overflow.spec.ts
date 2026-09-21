import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, navigateTo } from "./helpers";

/**
 * Overflow guards for the Investment Analysis modal's KPI row.
 *
 * Two defects shipped together on a phone-width screen: the formatted amount
 * ran underneath the KPI's icon tile, and a metric's InfoTooltip — anchored to
 * its icon and 220px wide — extended past the modal body, which scrolls
 * vertically with `overflow-x-hidden` and therefore clipped the text
 * mid-sentence ("COMPOUND ANNU…").
 *
 * This lives in its own file rather than as a block in `investments.spec.ts`
 * because the phone viewport must be set before the page boots. It performs no
 * backend writes, so it is listed in READ_ONLY_SPECS.
 */
test.describe("Investment Analysis KPI overflow", () => {
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  /** Open the first investment's analysis modal and wait for its KPIs. */
  async function openAnalysisModal(page: Page) {
    await navigateTo(page, "/investments");
    await page
      .getByRole("button", { name: /analysis|ניתוח/i })
      .first()
      .click();
    const kpis = page.getByTestId("analysis-kpi");
    await expect(kpis.first()).toBeVisible({ timeout: 30_000 });
    await expect(kpis).toHaveCount(4);
    // The value is rendered from the analysis query, so the row can be
    // visible while still showing nothing to measure.
    await expect(
      page.getByTestId("analysis-kpi-value").first(),
    ).not.toBeEmpty();
    return kpis;
  }

  /**
   * The modal body is the element that clips a tooltip: it scrolls
   * vertically and hides horizontal overflow.
   */
  const modalBody = (page: Page) =>
    page.locator(".modal-overlay .overflow-y-auto").first();

  test("amount never runs under the icon at phone width", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const kpis = await openAnalysisModal(page);

    const count = await kpis.count();
    for (let i = 0; i < count; i++) {
      const card = kpis.nth(i);
      const value = card.getByTestId("analysis-kpi-value");

      // The amount is laid out beside the icon tile, so its box already stops
      // short of it — what spilled under the icon was the *text*, which
      // overflows its box without widening it. `scrollWidth` is what sees it.
      const valueOverflow = await value.evaluate(
        (el) => el.scrollWidth - el.clientWidth,
      );
      expect(valueOverflow).toBeLessThanOrEqual(1);

      // Amount and icon still sit side by side, never stacked on top of one
      // another, and the icon stays inside the card. (A card-wide
      // `scrollWidth` check would be useless here: the tooltip panel is an
      // absolutely positioned descendant and counts toward it by design.)
      const cardBox = (await card.boundingBox())!;
      const valueBox = (await value.boundingBox())!;
      const iconBox = (await card
        .getByTestId("analysis-kpi-icon")
        .boundingBox())!;
      const gap = Math.max(
        iconBox.x - (valueBox.x + valueBox.width),
        valueBox.x - (iconBox.x + iconBox.width),
      );
      expect(gap).toBeGreaterThanOrEqual(0);
      expect(iconBox.x).toBeGreaterThanOrEqual(cardBox.x);
      expect(iconBox.x + iconBox.width).toBeLessThanOrEqual(
        cardBox.x + cardBox.width,
      );
    }
  });

  for (const { lang, width } of [
    { lang: "en", width: 390 },
    // RTL mirrors the panel to the opposite edge, so the metric that
    // overflowed in English is safe and its neighbour is at risk instead.
    { lang: "he", width: 1280 },
  ] as const) {
    test(`every KPI tooltip stays inside the modal (${lang})`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 844 });
      await page.addInitScript(
        (l) => localStorage.setItem("language", l),
        lang,
      );
      const kpis = await openAnalysisModal(page);
      const bodyBox = (await modalBody(page).boundingBox())!;

      const count = await kpis.count();
      for (let i = 0; i < count; i++) {
        const card = kpis.nth(i);
        // Tap to open — the desktop hover path resolves to the same
        // measured position.
        await card.getByRole("button").first().click();
        const panel = card.getByTestId("info-tooltip-panel");
        await expect(panel).toBeVisible();

        const panelBox = (await panel.boundingBox())!;
        expect(panelBox.width).toBeGreaterThan(0);
        // Fully inside the clipping container: nothing of the sentence is cut.
        expect(panelBox.x).toBeGreaterThanOrEqual(bodyBox.x);
        expect(panelBox.x + panelBox.width).toBeLessThanOrEqual(
          bodyBox.x + bodyBox.width,
        );

        // No text is clipped inside the panel either — it wrapped instead.
        const clipped = await panel.evaluate(
          (el) => el.scrollWidth - el.clientWidth,
        );
        expect(clipped).toBeLessThanOrEqual(1);

        // Close it again so the next card's panel is the only one open.
        await card.getByRole("button").first().click();
      }
    });
  }
});
