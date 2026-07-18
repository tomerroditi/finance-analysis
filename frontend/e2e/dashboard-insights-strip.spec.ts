import { test, expect, type Page } from "@playwright/test";
import { enableDemoMode } from "./helpers";

/**
 * The dashboard grid sizes cards to their content on >=lg, capped at
 * `--dash-card-h` (39rem): a card alone on a row is exactly as tall as it needs
 * to be, and taller content scrolls inside the cap instead of growing the row.
 *
 * `forecast` (the "This Month" hero) and `insights` are short full-width cards
 * — a heading plus a couple of rows of tiles — so they collapse well under the
 * cap with no tall empty gap below them. A content-heavy card (e.g. `budget`
 * paired with the transaction-rich `recent` feed) instead sits at the cap.
 *
 * forecast/insights ship beta/hidden by default, so each test seeds a layout
 * that puts them first, ahead of the half-width `budget` card.
 */
test.describe("Dashboard strip cards", () => {
  // Self-heal demo mode: a no-op when already enabled (the `demo-setup`
  // project turns it on once), so this is safe under parallel workers and
  // makes the spec order-independent when sharded alongside mutating specs.
  test.beforeAll(async () => {
    await enableDemoMode();
  });

  const CAP = 624; // --dash-card-h: 39rem at the default 16px root font size.
  const STRIP_CARDS = ["forecast", "insights"] as const;

  const LAYOUT = {
    order: ["forecast", "insights", "budget", "recent", "heatmap", "income_by_source", "income_expenses", "net_worth"],
    hidden: ["recurring", "goals", "cash_flow", "category"],
    v: 3,
  };
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((layout) => {
      window.localStorage.setItem("fa.dashboard.layout", JSON.stringify(layout));
    }, LAYOUT);
  });

  async function boxOf(page: Page, id: string) {
    const el = page.locator(`[data-card-id="${id}"]`);
    await expect(el).toBeVisible({ timeout: 45_000 });
    const box = await el.boundingBox();
    if (!box) throw new Error(`no box for ${id}`);
    return box;
  }

  // All three scenarios are pure geometry assertions against one rendered
  // dashboard — the responsive layout is CSS-driven, so the below-lg case is
  // covered by resizing the viewport mid-test instead of paying a second
  // (expensive) dashboard load per scenario.
  test("strips collapse to content, leave no tall gap (>=lg), and stack full-width below lg", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/");

    // --- >=lg: strip cards collapse to content well under the cap ---
    // The content-heavy `budget` card stays within the cap (taller content
    // scrolls inside instead of growing the row).
    const budget = await boxOf(page, "budget");
    expect(budget.height, "budget should not exceed the cap").toBeLessThanOrEqual(CAP + 2);

    // Each strip is much shorter than the cap — it sized to its content instead
    // of being stretched to a fixed row height.
    for (const id of STRIP_CARDS) {
      const strip = await boxOf(page, id);
      expect(strip.height, `${id} should collapse to content`).toBeLessThan(CAP * 0.8);
    }

    // --- >=lg: the card after a strip follows immediately, no tall empty gap ---
    // forecast -> insights and insights -> budget are both strip->next pairs.
    const pairs: [string, string][] = [
      ["forecast", "insights"],
      ["insights", "budget"],
    ];
    for (const [stripId, nextId] of pairs) {
      const strip = await boxOf(page, stripId);
      const next = await boxOf(page, nextId);
      const gap = next.y - (strip.y + strip.height);
      // Only the grid gap (md:gap-8 = 32px) — never the ~350px the fixed
      // height used to leave below a short strip. Allow generous slack.
      expect(gap, `gap below ${stripId}`).toBeGreaterThanOrEqual(0);
      expect(gap, `gap below ${stripId}`).toBeLessThan(64);
    }

    // --- below lg: the strips stack full-width above the next card ---
    await page.setViewportSize({ width: 800, height: 1000 });

    const forecast = await boxOf(page, "forecast");
    const insights = await boxOf(page, "insights");
    const budgetNarrow = await boxOf(page, "budget");

    expect(insights.y).toBeGreaterThan(forecast.y + forecast.height - 4);
    expect(budgetNarrow.y).toBeGreaterThan(insights.y + insights.height - 4);
    expect(Math.abs(insights.width - budgetNarrow.width)).toBeLessThan(8);
  });
});
