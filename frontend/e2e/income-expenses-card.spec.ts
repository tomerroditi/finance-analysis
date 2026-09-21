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
 * A Monthly/Yearly scope toggle in the title row re-folds every view: the
 * ledger and both breakdowns collapse to one row per calendar year, and the
 * KPI cards swap their rolling averages for per-year totals.
 *
 * This spec guards that each tab renders, that the ledger is ordered
 * newest-first, that the scope toggle folds months into years, that the
 * filter row carries only the pending-refund and
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

    // --- Scope toggle: the ledger folds into one row per year ---
    // Purely client-side (the card re-folds the monthly series it already
    // holds), so the year rows must add up to the months they replace.
    const monthlyNets = await rows.allTextContents();
    const monthKeys = await rows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-month")),
    );

    await card.getByRole("button", { name: "Yearly" }).click();
    await expect(card.getByText("Year", { exact: true }).first()).toBeVisible();

    // Fewer rows than months, and every key is a bare year.
    await expect.poll(() => rows.count()).toBeLessThan(monthKeys.length);
    const yearKeys = await rows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-month")),
    );
    expect(yearKeys.length).toBeGreaterThan(0);
    for (const key of yearKeys) expect(key).toMatch(/^\d{4}$/);
    // Newest-first, like the monthly ledger.
    expect(yearKeys[0]! > yearKeys[yearKeys.length - 1]!).toBe(true);

    // A year row carries real money, and the KPI card leads with a year
    // caption instead of the 3-month average.
    await expect(rows.first()).toContainText(/\d,\d{3}/);
    await expect(income.getByText("3-mo avg")).toHaveCount(0);
    await expect(income.getByText(/^\d{4}( to date)?$/).first()).toBeVisible();

    // The breakdown tabs fold too — one composition row per year.
    await card.getByRole("button", { name: "Expenses Breakdown" }).click();
    const yearlyComposition = card.getByTestId("composition-row");
    await expect(yearlyComposition.first()).toBeVisible({ timeout: 45_000 });
    const compositionKeys = await yearlyComposition.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-month")),
    );
    expect(compositionKeys.length).toBeGreaterThan(0);
    for (const key of compositionKeys) expect(key).toMatch(/^\d{4}$/);

    // Back to Monthly: the ledger returns exactly as it was.
    await card.getByRole("button", { name: "Totals" }).click();
    await card.getByRole("button", { name: "Monthly" }).click();
    await expect(card.getByText("Month", { exact: true }).first()).toBeVisible();
    await expect.poll(() => rows.allTextContents()).toEqual(monthlyNets);
    await expect(income.getByText("3-mo avg")).toBeVisible();

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

  // Its own test on purpose: the defect needs a bar to go capped -> uncapped
  // on a card that has not been interacted with yet, and the journey test has
  // paged the ledger by the time it gets here, which is enough to hide it.
  test("a bar that loses its over-scale cap restores its own border", async ({
    page,
  }) => {
    const card = await openCard(page);
    const rows = card.getByTestId("ledger-row");
    await expect(rows.first()).toBeVisible({ timeout: 45_000 });

    // The tip's colour and style are supplied on every render rather than
    // spread in only while capped. React removes a property a re-render stops
    // giving, and a removed `borderRightColor` falls back to `currentColor`
    // -- the inherited near-white text colour -- not to the `border`
    // shorthand, so a bar that lost its cap kept a pale 1px sliver at its tip.
    const barBorders = () =>
      card.evaluate(() => {
        const out: string[] = [];
        document.querySelectorAll('[data-testid="ledger-row"]').forEach((row) => {
          row.querySelectorAll('div[style*="width"]').forEach((bar) => {
            const cs = getComputedStyle(bar as HTMLElement);
            if (cs.borderLeftWidth === "0px" && cs.borderRightWidth === "0px") return;
            out.push(
              `${row.getAttribute("data-month")} ${cs.borderLeftStyle}|${cs.borderLeftColor}` +
                `|${cs.borderRightStyle}|${cs.borderRightColor}`,
            );
          });
        });
        return out;
      });

    // The expense KPI has its own query and can still read the zero
    // placeholder here; it is what tells us a toggle's refetch has landed.
    const expenseKpi = card.getByTestId("kpi-expense");
    await expect(expenseKpi).toContainText(/\d,\d{3}/, { timeout: 45_000 });
    const kpiBefore = await expenseKpi.textContent();
    const bordersBefore = await barBorders();
    expect(bordersBefore.length).toBeGreaterThan(0);

    const projectsChip = card.getByRole("button", { name: /^Projects (Ex|In)cluded$/ });
    await projectsChip.click();
    await expect.poll(() => expenseKpi.textContent(), { timeout: 20_000 }).not.toBe(kpiBefore);
    // Some bar has to take a cap here, or the round trip proves nothing.
    expect(await barBorders()).not.toEqual(bordersBefore);

    await projectsChip.click();
    await expect.poll(() => expenseKpi.textContent(), { timeout: 20_000 }).toBe(kpiBefore);
    // Read the settled state once: polling until the borders matched would
    // pass on the first frame that happened to agree, which is the transient
    // this defect hides behind.
    expect(await barBorders()).toEqual(bordersBefore);
  });
});
