import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Default-layout dashboard geometry + behavior, on as few (expensive) cold
 * dashboard loads as possible:
 *
 * - Half-width cards: on wide (>=lg) viewports the customizable region is a
 *   2-column grid. `budget` and `recent` are both half-width and adjacent in
 *   the default order, so they pair on one row; `income_expenses` is
 *   full-width and spans the row. Fill order is start->end and flips under
 *   RTL (Hebrew).
 * - Blocks are capped at `--dash-card-h` (39rem) and scroll overflow inside.
 * - The Spending Calendar (`heatmap`) card shows two months at half-row width
 *   (>=lg) and a single month in the single-column mobile layout.
 * - Expanding the KPI grid reveals the Net Worth card's last-3-months change
 *   breakdown.
 *
 * The responsive layout is CSS-driven, so the below-lg cases are covered by
 * resizing the viewport mid-test instead of paying a second dashboard load.
 * Only the RTL scenario needs its own load (language must be seeded before
 * the app boots).
 */

// A compact "MM.yy" month-row label, e.g. "07.26" — rendered only inside the
// expanded Net Worth card's per-month change breakdown. Currency deltas and
// percentages in the card use at most one fractional digit, so a two-digit.
// two-digit pattern is unique to these month labels.
const MONTH_ROW = /\b\d{2}\.\d{2}\b/;

test.describe("Dashboard half-width blocks", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
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

  /** Count the 7-column weekday-header rows inside the heatmap card — one per month. */
  async function monthGridCount(page: Page) {
    const card = page.locator('[data-card-id="heatmap"]');
    await expect(card).toBeVisible({ timeout: 45_000 });
    // Each month renders a weekday header: a 7-column grid whose first cell is a
    // single-letter weekday label. The header uses mb-1 (gap was mb-1.5 before
    // the compact-cell refactor).
    return card.locator("div.grid.grid-cols-7.mb-1").count();
  }

  test("row pairing, height caps, calendar months, net-worth breakdown (>=lg), and below-lg stacking", async ({
    page,
  }) => {
    // 39rem at the default 16px root font size — the max card height.
    const CAP = 624;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    // --- Two half cards pair on one row; a full card spans the row ---
    const ids = ["budget", "recent", "heatmap", "income_by_source", "income_expenses"];
    const boxes: Record<string, { x: number; y: number; width: number; height: number }> = {};
    for (const id of ids) boxes[id] = await boxOf(page, id);

    expect(Math.abs(boxes.budget.y - boxes.recent.y)).toBeLessThan(4);
    expect(Math.abs(boxes.budget.width - boxes.recent.width)).toBeLessThan(8);
    expect(boxes.budget.x).toBeLessThan(boxes.recent.x);
    expect(boxes.income_expenses.width).toBeGreaterThan(boxes.budget.width * 1.8);

    // --- No block grows past the cap — taller content scrolls inside instead ---
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

    // --- Spending Calendar shows two months at half-row width (>=lg) ---
    await expect.poll(() => monthGridCount(page), { timeout: 45_000 }).toBe(2);

    // --- Expanding the KPI grid reveals the Net Worth monthly-change rows ---
    // "Cash Balance" is text unique to the pinned KPI header (the chart filter
    // chips read Bank Balance / Investment Value / Net Worth / Debt Payments,
    // never "Cash Balance"). Waiting on it guarantees the header finished
    // loading before we interact — otherwise the still-skeleton header would
    // let a locator resolve to a same-named chart tab further down the page.
    const cashBalanceLabel = page.getByText("Cash Balance", { exact: true });
    await expect(cashBalanceLabel).toBeVisible({ timeout: 45_000 });

    // Scope to the Net Worth KPI card via its label's card ancestor.
    const netWorthCard = page
      .getByText("Net Worth", { exact: true })
      .first()
      .locator("xpath=ancestor::*[contains(@class,'rounded-xl')][1]");

    // Collapsed: no per-month breakdown rows yet.
    await expect(netWorthCard).not.toContainText(MONTH_ROW);

    // The whole KPI grid is one click target that toggles the breakdowns.
    const kpiGrid = cashBalanceLabel.locator(
      "xpath=ancestor::*[contains(@class,'cursor-pointer')][1]",
    );
    await kpiGrid.click();

    // Expanded: the Net Worth card lists up to three month rows, each with a
    // signed currency delta and a percentage in parentheses.
    await expect(netWorthCard).toContainText(MONTH_ROW);
    await expect(netWorthCard).toContainText(/[+-].*%\)/);

    // Collapsing hides the breakdown again.
    await kpiGrid.click();
    await expect(netWorthCard).not.toContainText(MONTH_ROW);

    // --- Below lg the cards stack full-width (single column) ---
    await page.setViewportSize({ width: 800, height: 1000 });

    const budgetNarrow = await boxOf(page, "budget");
    const recentNarrow = await boxOf(page, "recent");

    expect(recentNarrow.y).toBeGreaterThan(budgetNarrow.y + budgetNarrow.height - 4);
    expect(Math.abs(budgetNarrow.width - recentNarrow.width)).toBeLessThan(8);

    // --- Spending Calendar collapses to a single month in the mobile layout ---
    await expect.poll(() => monthGridCount(page), { timeout: 45_000 }).toBe(1);
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
});
