import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * Default-layout dashboard geometry + behavior, on as few (expensive) cold
 * dashboard loads as possible:
 *
 * - Half-width cards: on wide (>=lg) viewports the customizable region is a
 *   2-column grid. `budget` and `recent` are both half-width and adjacent in
 *   the default order, so they pair on one row, as do `recurring` and
 *   `heatmap` on the next; `income_expenses` is full-width and spans the row.
 *   Fill order is start->end and flips under RTL (Hebrew).
 * - Blocks are capped at `--dash-card-h` (39rem) and scroll overflow inside.
 * - Card gutters are compact (gap-1.5 = 6px).
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
  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll. enableDemoMode's demo/prepare call is idempotent, so this
  // is still cheap and order-independent when sharded alongside mutating
  // specs.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
    await page.addInitScript(() =>
      window.localStorage.removeItem("fa.dashboard.layout"),
    );
  });

  /** The default layout's cards, in fill order. */
  const CARD_IDS = [
    "budget",
    "recent",
    "recurring",
    "goals",
    "heatmap",
    "income_expenses",
  ];

  async function boxOf(page: Page, id: string) {
    const el = page.locator(`[data-card-id="${id}"]`);
    await expect(el).toBeVisible({ timeout: 45_000 });
    const box = await el.boundingBox();
    if (!box) throw new Error(`no box for ${id}`);
    return box;
  }

  /**
   * Block until no card's geometry is still moving.
   *
   * Every assertion here is a comparison *between* cards, but `boxOf` only
   * waits for the card it is asked about to be visible. The cards lazy-load
   * and grow as their content arrives, so a card measured early can still be
   * short while one measured later has already been pushed down — and the
   * difference lands in whichever gap is computed from the two. CI saw
   * exactly that: a 6px row gutter read as 144px, then 290px on the retry, on
   * a runner loaded enough for the page to still be settling through both
   * attempts.
   *
   * Two consecutive agreeing samples of every card at once was the first
   * attempt at pinning this down, and it is not enough on its own: the cards
   * arrive in waves, and the lull between two waves is longer than the sample
   * gap. Measured on a warm dev server, the whole grid held still from 1.0 s
   * to 1.5 s and then jumped again at 2.0 s — so a run that started sampling
   * in that lull declared the layout settled while two more reflows were
   * still to come. The same 144px row gutter came back on CI.
   *
   * What actually ends the movement is the last query landing, so wait for
   * the network to go quiet first and let the sampling guard the reflow that
   * follows it. Measured on the same page: the last card stops moving ~3 s
   * in, `networkidle` lands ~5.8 s in — after every reflow, never before.
   * This is the case the "avoid redundant networkidle" rule carves out, since
   * what follows is a non-waiting geometry read. Nothing here polls on a
   * timer (no `refetchInterval` in the app), so the network genuinely idles.
   *
   * It weakens no assertion — the geometry checked is the same, just no
   * longer read mid-reflow.
   */
  async function waitForSettledCards(page: Page, ids: string[] = CARD_IDS) {
    await page.waitForLoadState("networkidle");
    const sample = () =>
      page.evaluate(
        (cardIds) =>
          cardIds
            .map((id) => {
              const el = document.querySelector(`[data-card-id="${id}"]`);
              if (!el) return `${id}:absent`;
              const r = el.getBoundingClientRect();
              return `${id}:${Math.round(r.x)},${Math.round(r.y)},${Math.round(r.width)},${Math.round(r.height)}`;
            })
            .join("|"),
        ids,
      );

    await expect
      .poll(
        async () => {
          const before = await sample();
          if (before.includes(":absent")) return "moving";
          await page.waitForTimeout(250);
          return before === (await sample()) ? "settled" : "moving";
        },
        { timeout: 45_000, intervals: [100] },
      )
      .toBe("settled");
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
    const ids = CARD_IDS;
    const boxes: Record<
      string,
      { x: number; y: number; width: number; height: number }
    > = {};
    await waitForSettledCards(page, ids);
    for (const id of ids) boxes[id] = await boxOf(page, id);

    expect(Math.abs(boxes.budget.y - boxes.recent.y)).toBeLessThan(4);
    expect(Math.abs(boxes.budget.width - boxes.recent.width)).toBeLessThan(8);
    expect(boxes.budget.x).toBeLessThan(boxes.recent.x);
    expect(boxes.income_expenses.width).toBeGreaterThan(
      boxes.budget.width * 1.8,
    );

    // --- Gutters between cards are compact (gap-1.5 = 6px) ---
    // The customizable region used to sit at gap-8 (32px), which read as an
    // over-airy dashboard. Assert both bounds so neither a regression back to
    // the wide gutter nor a collapse to zero slips through.
    const GUTTER = 6;
    const columnGutter = boxes.recent.x - (boxes.budget.x + boxes.budget.width);
    const rowGutter = boxes.recurring.y - (boxes.budget.y + boxes.budget.height);
    expect(
      columnGutter,
      "column gutter between paired half cards",
    ).toBeGreaterThan(GUTTER - 2);
    expect(
      columnGutter,
      "column gutter between paired half cards",
    ).toBeLessThan(GUTTER + 2);
    expect(rowGutter, "row gutter between card rows").toBeGreaterThan(
      GUTTER - 2,
    );
    expect(rowGutter, "row gutter between card rows").toBeLessThan(GUTTER + 2);

    // --- No block grows past the cap — taller content scrolls inside instead ---
    for (const id of ids) {
      expect(
        boxes[id].height,
        `${id} should not exceed the cap`,
      ).toBeLessThanOrEqual(CAP + 2);
    }

    // Two half cards sharing a row are the same height (the taller of the two).
    expect(Math.abs(boxes.budget.height - boxes.recent.height)).toBeLessThan(2);
    // Second row: `recurring` + `goals`. Both graduated out of beta into the
    // default layout between `recent` and `heatmap`, each shifting this pair
    // along — it was `heatmap` + `income_by_source`, then `recurring` +
    // `heatmap`, and `heatmap` now pairs on the row below.
    expect(Math.abs(boxes.recurring.y - boxes.goals.y)).toBeLessThan(4);
    expect(boxes.recurring.x).toBeLessThan(boxes.goals.x);
    expect(Math.abs(boxes.recurring.height - boxes.goals.height)).toBeLessThan(
      2,
    );
    // `heatmap` is the last half card before a full one now that the
    // income-by-source card is gone (its all-time donut lives inside
    // `income_expenses`), so it sits alone on its row and the full card
    // starts below it.
    expect(boxes.income_expenses.y).toBeGreaterThan(boxes.heatmap.y);

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
      .evaluateAll((els) => els.map((el) => getComputedStyle(el).maxHeight));
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
    expect(
      tallest,
      "a card should reach the height cap",
    ).toBeGreaterThanOrEqual(CAP - 2);

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
    // A resize reflows every card, so the layout has to settle again.
    await waitForSettledCards(page);

    const budgetNarrow = await boxOf(page, "budget");
    const recentNarrow = await boxOf(page, "recent");

    expect(recentNarrow.y).toBeGreaterThan(
      budgetNarrow.y + budgetNarrow.height - 4,
    );
    expect(Math.abs(budgetNarrow.width - recentNarrow.width)).toBeLessThan(8);

    // --- Spending Calendar collapses to a single month in the mobile layout ---
    await expect.poll(() => monthGridCount(page), { timeout: 45_000 }).toBe(1);
  });

  test("fill order flips under RTL (Hebrew)", async ({ page }) => {
    await page.addInitScript(() =>
      window.localStorage.setItem("language", "he"),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await waitForSettledCards(page);

    const budget = await boxOf(page, "budget");
    const recent = await boxOf(page, "recent");

    expect(Math.abs(budget.y - recent.y)).toBeLessThan(4);
    expect(budget.x).toBeGreaterThan(recent.x);
  });
});
