import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode, disableDemoMode } from "./helpers";

/**
 * Half-width dashboard cards: on wide (>=lg) viewports the customizable region
 * is a 2-column grid. `budget` and `recent` are both half-width and adjacent in
 * the default order, so they pair on one row; `income_expenses` is full-width
 * and spans the row. Fill order is start->end and flips under RTL (Hebrew).
 */
test.describe("Dashboard half-width blocks", () => {
  test.beforeAll(async ({ browser }) => {
    const page = await browser.newPage();
    await enableDemoMode(page);
    await page.close();
  });

  test.afterAll(async ({ browser }) => {
    const page = await browser.newPage();
    await disableDemoMode(page);
    await page.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.removeItem("fa.dashboard.layout"));
  });

  async function boxOf(page: Page, id: string) {
    const el = page.locator(`[data-card-id="${id}"]`);
    await expect(el).toBeVisible({ timeout: 45_000 });
    const box = await el.boundingBox();
    if (!box) throw new Error(`no box for ${id}`);
    return box;
  }

  test("two half cards pair on one row; a full card spans the row (LTR)", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");
    const incomeExpenses = await boxOf(page, "income_expenses");

    expect(Math.abs(budget.y - recent.y)).toBeLessThan(4);
    expect(Math.abs(budget.width - recent.width)).toBeLessThan(8);
    expect(budget.x).toBeLessThan(recent.x);
    expect(incomeExpenses.width).toBeGreaterThan(budget.width * 1.8);
  });

  test("blocks are capped and scroll overflow; paired cards share a row height (>=lg)", async ({
    page,
  }) => {
    // 39rem at the default 16px root font size — the max card height.
    const CAP = 624;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    const ids = ["budget", "recent", "heatmap", "income_by_source", "income_expenses"];
    const boxes: Record<string, { height: number }> = {};
    for (const id of ids) boxes[id] = await boxOf(page, id);

    // No block grows past the cap — taller content scrolls inside instead.
    for (const id of ids) {
      expect(boxes[id].height, `${id} should not exceed the cap`).toBeLessThanOrEqual(CAP + 2);
    }

    // Two half cards sharing a row are the same height (the taller of the two).
    expect(Math.abs(boxes.budget.height - boxes.recent.height)).toBeLessThan(2);
    expect(Math.abs(boxes.heatmap.height - boxes.income_by_source.height)).toBeLessThan(2);

    // Every block enables internal scrolling.
    const allOverflows = await page
      .locator("[data-card-id] > *")
      .evaluateAll((els) => els.map((el) => getComputedStyle(el).overflowY));
    expect(allOverflows.length).toBeGreaterThan(0);
    expect(allOverflows.every((o) => o === "auto")).toBe(true);

    // All cards except `recent` are height-capped. `recent` is intentionally
    // uncapped so it can show more transactions than the cap allows.
    const cappedStyles = await page
      .locator("[data-card-id]:not([data-card-id='recent']) > *")
      .evaluateAll((els) =>
        els.map((el) => getComputedStyle(el).maxHeight),
      );
    expect(cappedStyles.length).toBeGreaterThan(0);
    expect(cappedStyles.every((h) => h === `${CAP}px`)).toBe(true);

    const recentMaxH = await page
      .locator("[data-card-id='recent'] > *")
      .evaluateAll((els) => els.map((el) => getComputedStyle(el).maxHeight));
    expect(recentMaxH.every((h) => h === "none")).toBe(true);

    // At least one card is clamped to the cap rather than sized to its own
    // content — proving the cap binds rather than every card just being short.
    // The full-width chart cards carry a fixed ~600px chart region plus a
    // header, so their natural height exceeds the cap and they clamp to it
    // exactly. (Chart cards resize their plot to fit instead of overflowing at
    // the card level; list-heavy cards scroll inside their own inner regions.)
    const tallest = Math.max(...ids.map((id) => boxes[id].height));
    expect(tallest, "a card should reach the height cap").toBeGreaterThanOrEqual(CAP - 2);
  });

  test("fill order flips under RTL (Hebrew)", async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("language", "he"));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");

    expect(Math.abs(budget.y - recent.y)).toBeLessThan(4);
    expect(budget.x).toBeGreaterThan(recent.x);
  });

  test("below lg the cards stack full-width (single column)", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 1000 });
    await page.goto("/");

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");

    expect(recent.y).toBeGreaterThan(budget.y + budget.height - 4);
    expect(Math.abs(budget.width - recent.width)).toBeLessThan(8);
  });
});
