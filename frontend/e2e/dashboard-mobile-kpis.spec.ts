import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * On phones the four financial-health KPIs stack one per row instead of the
 * old 2x2 grid, and each collapsed card packs its label, value and MoM badge
 * onto a single line. A full-width single-line row is easy to overflow — a long
 * Hebrew label beside a seven-figure balance — so the layout assertions are
 * paired with a clipping check, in both locales, collapsed and expanded.
 *
 * This lives in its own file rather than as a block in `dashboard.spec.ts`
 * because it needs a mobile viewport, which must be set before the page boots.
 * The Net Worth change-chip row is checked here too, for the same reason.
 * It performs no backend writes, so it is listed in READ_ONLY_SPECS.
 */
test.describe("dashboard mobile KPI cards", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  /** Geometry of every KPI card, plus how far its content overflows it. */
  const measure = (page: Page) =>
    page.getByTestId("kpi-card").evaluateAll((els) =>
      els.map((el) => {
        const r = el.getBoundingClientRect();
        return {
          top: r.top,
          height: r.height,
          width: r.width,
          // The card is `overflow-hidden`, so scrollWidth still reports content
          // that sticks out — a positive delta means text is being clipped.
          overflow: el.scrollWidth - el.clientWidth,
        };
      }),
    );

  for (const lang of ["en", "he"] as const) {
    test(`four full-width single-line rows, no overflow (${lang})`, async ({ page }) => {
      // The app reads its locale from localStorage["language"] on boot, so
      // seeding it here lands the first navigation directly in that locale.
      await page.addInitScript((l) => localStorage.setItem("language", l), lang);
      await page.goto("/");

      const grid = page.getByTestId("health-kpis");
      await expect(grid).toBeVisible();
      const cards = page.getByTestId("kpi-card");
      await expect(cards).toHaveCount(4);
      await expect(cards.last()).toBeVisible();

      const gridBox = await grid.boundingBox();
      expect(gridBox).not.toBeNull();

      const boxes = await measure(page);

      boxes.forEach((box, i) => {
        // Full-width: a 2-column grid would make every card roughly half this.
        expect(box.width).toBeGreaterThan(gridBox!.width - 2);
        // One KPI per row: tops strictly increase, never share a line.
        if (i > 0) {
          expect(box.top).toBeGreaterThan(boxes[i - 1].top + boxes[i - 1].height - 1);
        }
        // Single line of content — the stacked `sm:` card is taller than this.
        expect(box.height).toBeLessThan(56);
        expect(box.overflow).toBeLessThanOrEqual(0);
      });

      expect(await grid.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

      // Tapping the header expands every card's account breakdown; the rows
      // grow taller but must still not overflow sideways.
      await cards.first().click();
      await expect(page.getByTestId("kpi-card").first()).toBeVisible();
      const expandedBoxes = await measure(page);
      expect(expandedBoxes.some((box) => box.height >= 56)).toBe(true);
      for (const box of expandedBoxes) {
        expect(box.width).toBeGreaterThan(gridBox!.width - 2);
        expect(box.overflow).toBeLessThanOrEqual(0);
      }
      expect(await grid.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);

      // --- Net Worth change chips: one horizontally scrollable row ---
      // Seven periods (10Y..1M) never fit a phone, so the row scrolls sideways
      // instead of wrapping onto a second line.
      const netWorth = page.locator('[data-card-id="net_worth"]');
      await netWorth.scrollIntoViewIfNeeded();
      const chipRow = page.getByTestId("net-worth-change-chips");
      await expect(chipRow).toBeVisible({ timeout: 45_000 });
      const chips = chipRow.locator(":scope > div");
      await expect(chips).toHaveCount(7);
      const chipTops = await chips.evaluateAll((els) =>
        els.map((el) => Math.round(el.getBoundingClientRect().top)),
      );
      expect(new Set(chipTops).size).toBe(1);
      expect(await chipRow.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeGreaterThan(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
      ).toBeLessThanOrEqual(0);
    });
  }
});
