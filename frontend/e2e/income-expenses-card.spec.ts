import { test, expect, type Page, type Locator } from "@playwright/test";
import { enableDemoMode, navigateTo, resetDemoData } from "./helpers";

/**
 * The redesigned "Income & Expenses" dashboard card. It replaces the old
 * horizontal Plotly bars with:
 *   - Totals tab      → a statement-style ledger (one row per month, newest
 *                       on top, income/expense bars + a Net figure).
 *   - Income/Expenses → 100%-composition rows (`data-testid="composition-row"`)
 *                       whose slices carry no text at all.
 *
 * This spec guards that each tab renders, that the ledger is ordered
 * newest-first, that the filter row carries only the pending-refund and
 * project chips and that the pending-refund one actually moves the
 * breakdown, that tab switches never crash the card, and that hovering a
 * composition slice pops the cursor-following tooltip — the only readout the
 * bars have now that both the in-bar labels and the colour legend are gone, so
 * it must name the slice with its amount *and* its share. Demo Mode supplies
 * the sample data.
 *
 * All checks are client-side interactions on one rendered card, so they run
 * as a single test on a single dashboard load — the cold dashboard boot is
 * by far the most expensive step, and it used to be paid once per assertion
 * group (5×).
 */
test.describe("Income & Expenses dashboard card", () => {
  // Restore pristine demo data before this file runs. The `mutating`
  // project is serial and each file is expected to own its DB state; the
  // demo database is process-global, so without this a predecessor's
  // writes leak in and this spec asserts against data it did not set up.
  test.beforeAll(async () => {
    await resetDemoData();
  });

  // Demo Mode lives in the browser context's localStorage, so it must be
  // seeded per-test (a fresh context per test) rather than once in
  // beforeAll via a throwaway page — that page is a different browser
  // context from the one each test actually navigates in, so anything it
  // set there never reached the real test.
  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  /** The Income & Expenses dashboard card (its lazy placeholder reserves height). */
  function cardContainer(page: Page): Locator {
    return page.locator('[data-card-id="income_expenses"]');
  }

  /**
   * Bring the (lazy-mounted) card into view and wait for its content to render.
   * Below-the-fold cards defer mounting until scrolled near the viewport, so we
   * scroll the placeholder in first, then wait for the title to appear.
   */
  async function openCard(page: Page): Promise<Locator> {
    await navigateTo(page, "/");
    const card = cardContainer(page);
    await expect(card).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();
    await expect(
      card.getByRole("heading", { name: "Income & Expenses" }),
    ).toBeVisible({
      timeout: 45_000,
    });
    return card;
  }

  test("tabs, ledger, KPIs, pager, and slice tooltips all behave on one load", async ({
    page,
  }) => {
    const card = await openCard(page);

    // --- Totals tab: ledger renders newest-first with a Net column ---
    await expect(
      card.getByText("Month", { exact: true }).first(),
    ).toBeVisible();
    await expect(card.getByText("Net", { exact: true }).first()).toBeVisible();

    const rows = card.getByTestId("ledger-row");
    await expect(rows.first()).toBeVisible({ timeout: 45_000 });
    const count = await rows.count();
    expect(count).toBeGreaterThan(1);

    // Newest-first: the first row's month must be later than the last row's.
    const firstMonth = await rows.first().getAttribute("data-month");
    const lastMonth = await rows.last().getAttribute("data-month");
    expect(firstMonth && lastMonth).toBeTruthy();
    expect(firstMonth! > lastMonth!).toBe(true); // "YYYY-MM" strings sort lexically

    // --- KPI cards summarise income and expenses with period labels ---
    const income = card.getByTestId("kpi-income");
    const expenses = card.getByTestId("kpi-expense");
    await expect(income).toBeVisible();
    await expect(expenses).toBeVisible();

    // Each card leads with the 3-month average and keeps the 6M/12M windows.
    await expect(income.getByText("3-mo avg")).toBeVisible();
    await expect(income.getByText("6M", { exact: true })).toBeVisible();
    await expect(income.getByText("12M", { exact: true })).toBeVisible();

    // Income averages come straight from the loaded series — a real thousands
    // figure (e.g. "30,321"), not a zero placeholder. (Currency uses an NBSP
    // before ₪, so match just the grouped number.)
    await expect(income).toContainText(/\d,\d{3}/);

    // --- Ledger caps to 12 months; pager reveals more and collapses back ---
    const initial = await rows.count();
    expect(initial).toBeLessThanOrEqual(12);

    // The demo history spans well over a year, so the pager must be present.
    const showMore = card.getByRole("button", { name: /Show earlier months/ });
    await expect(showMore).toBeVisible();

    await showMore.click();
    await expect.poll(() => rows.count()).toBeGreaterThan(initial);

    // Collapsing returns to the 12-month window.
    await card.getByRole("button", { name: "Show less" }).click();
    await expect.poll(() => rows.count()).toBeLessThanOrEqual(12);

    // --- Filter chips: pending-refunds and projects only ---
    // "Refunds Included/Excluded" is gone: a refund is a positive amount in an
    // expense category, so it already nets off the month it lands in, and the
    // opt-out only ever reached the ledger and the income KPI — never the
    // expense KPI beside them or either breakdown tab.
    await expect(
      card.getByRole("button", { name: /^Pending Refunds (Ex|In)cluded$/ }),
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: /^Refunds (Ex|In)cluded$/ }),
    ).toHaveCount(0);

    // --- Income Breakdown: composition rows with textless slices ---
    await card.getByRole("button", { name: "Income Breakdown" }).click();

    const compositionRows = card.getByTestId("composition-row");
    await expect(compositionRows.first()).toBeVisible({ timeout: 45_000 });
    expect(await compositionRows.count()).toBeGreaterThan(0);

    // The % / ₪ label toggle is gone — the tooltip carries both figures now.
    await expect(card.getByRole("button", { name: "Show amount (₪)" })).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Show share (%)" })).toHaveCount(0);

    // No slice prints anything: the bars are pure colour. The rows are already
    // visible above, so an empty result here is a real one, not an unrendered
    // page.
    const segments = compositionRows.first().getByTestId("composition-segment");
    await expect(segments.first()).toBeVisible();
    for (const text of await segments.allTextContents()) {
      expect(text.trim()).toBe("");
    }

    // --- Hovering a slice names it instantly (the only readout left) ---
    // The tooltip is portalled to <body>, so it is looked up on the page, not
    // inside the card. A short timeout is the point of the assertion: this
    // replaced a native `title`, which browsers delay by ~1s and never expose
    // in the DOM at all.
    const tooltip = page.getByTestId("composition-tooltip");
    await expect(tooltip).toHaveCount(0);

    await segments.first().hover();
    await expect(tooltip).toBeVisible({ timeout: 1_000 });
    // "<Category>: <amount> ₪ (<share>%)" — both figures, as the bars show none.
    await expect(tooltip).toHaveText(/.+: .*\d.*\(\d+%\)/);

    // Leaving the chart dismisses it.
    await card.getByRole("heading", { name: "Income & Expenses" }).hover();
    await expect(tooltip).toHaveCount(0);

    // --- Expenses Breakdown renders composition rows too ---
    await card.getByRole("button", { name: "Expenses Breakdown" }).click();

    await expect(compositionRows.first()).toBeVisible({ timeout: 45_000 });
    expect(await compositionRows.count()).toBeGreaterThan(0);

    // --- The pending-refunds chip now reaches the breakdown too ---
    // It used to move only the expense KPI; the breakdown and ledger ignored
    // it. Demo data carries open credit-card refund expectations in the
    // recent months, so flipping the chip must change what a month cost.
    const totalsBefore = await compositionRows.allTextContents();
    await card.getByRole("button", { name: "Pending Refunds Excluded" }).click();
    await expect(
      card.getByRole("button", { name: "Pending Refunds Included" }),
    ).toBeVisible();
    await expect
      .poll(() => compositionRows.allTextContents(), { timeout: 20_000 })
      .not.toEqual(totalsBefore);

    // Put it back so the rest of the journey sees the default view.
    await card.getByRole("button", { name: "Pending Refunds Included" }).click();
    await expect(
      card.getByRole("button", { name: "Pending Refunds Excluded" }),
    ).toBeVisible();

    // --- An over-scale month's meter is dashed, and legibly so ---
    // The meter is 3px tall with a 2px rounded cap. A diagonal hatch is all
    // but vertical over three pixels and the cap sheared both ends into
    // ragged points, so the bar read as torn rather than hatched — and which
    // rows showed it changed with every filter toggle. The stripes must stay
    // horizontal (90deg), which is the one direction the height cannot spoil.
    const overScaleFill = card
      .locator('[data-testid="composition-row"] div[title]:not([title=""]) > div')
      .first();
    await expect(overScaleFill).toBeVisible();
    expect(
      await overScaleFill.evaluate((el) => getComputedStyle(el).backgroundImage),
    ).toContain("90deg");

    // Slices carry their readout here as well, and still print nothing.
    const expenseSegments = compositionRows.first().getByTestId("composition-segment");
    await expect(expenseSegments.first()).toBeVisible();
    for (const text of await expenseSegments.allTextContents()) {
      expect(text.trim()).toBe("");
    }

    await expenseSegments.first().hover();
    await expect(page.getByTestId("composition-tooltip")).toBeVisible({
      timeout: 1_000,
    });
  });
});
