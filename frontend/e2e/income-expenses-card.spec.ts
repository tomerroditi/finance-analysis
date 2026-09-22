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
 * A Monthly/Yearly/All-time scope toggle in the title row re-folds every view:
 * the ledger and both breakdowns collapse to one row per calendar year (or to
 * a single row over the whole window), and the KPI cards swap their rolling
 * averages for per-year — or all-time — totals. In the all scope a breakdown
 * is drawn as a donut with a collapsible legend instead of a composition bar,
 * because a single period has no movement for a bar to show.
 *
 * Either breakdown can also be filtered to one series — click a slice, a donut
 * slice or a legend row — which replaces the mix with that series over time.
 *
 * This spec guards that each tab renders, that the ledger is ordered
 * newest-first, that the scope toggle folds months into years, that the
 * filter row carries the pending-refund, project and loans chips and
 * that the pending-refund one actually moves the breakdown, that the KPI, the
 * ledger and the breakdown legend report the *same* money (they are one
 * number summed three ways), that tab switches never crash the card, and that hovering a
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
    // Exact, not a substring: the heading carries the column's unit, and a
    // bare "Net" would mean the ₪ had quietly moved back onto every row.
    await expect(
      card.getByText("Net (₪)", { exact: true }).first(),
    ).toBeVisible();

    const rows = card.getByTestId("ledger-row");
    await expect(rows.first()).toBeVisible({ timeout: 45_000 });
    const count = await rows.count();
    expect(count).toBeGreaterThan(1);

    // Newest-first: the first row's month must be later than the last row's.
    const firstMonth = await rows.first().getAttribute("data-month");
    const lastMonth = await rows.last().getAttribute("data-month");
    expect(firstMonth && lastMonth).toBeTruthy();
    expect(firstMonth! > lastMonth!).toBe(true); // "YYYY-MM" strings sort lexically

    // --- Headings sit on the columns they name, and those columns are snug ---
    // Assert the geometry rather than the CSS: the headings and the rows are
    // separate elements subgridded onto one track list, and what actually
    // matters is that a heading's box lines up with its column's, however the
    // tracks come to be declared.
    const columns = await page.evaluate(() => {
      const rows = Array.from(
        document.querySelectorAll('[data-testid="ledger-row"]'),
      );
      const head = rows[0].parentElement!.querySelector(
        ":scope > div.grid-cols-subgrid",
      )!;
      const edges = (el: Element) =>
        Array.from(el.children).map((c) => {
          const r = c.getBoundingClientRect();
          return [Math.round(r.left), Math.round(r.right)].join(":");
        });
      // Widest rendered text in a column vs the column box that holds it —
      // a fixed width sized for content nobody has shows up as slack here.
      const slack = (index: number) => {
        const widest = Math.max(
          ...rows.map((r) => {
            const range = document.createRange();
            range.selectNodeContents(r.children[index]);
            return range.getBoundingClientRect().width;
          }),
        );
        const box = rows[0].children[index].getBoundingClientRect().width;
        return box - widest;
      };
      return {
        head: edges(head),
        row: edges(rows[0]),
        periodSlack: slack(0),
        netSlack: slack(3),
      };
    });
    expect(columns.row).toEqual(columns.head);
    // Shrink-wrapped: the widest label fills its column. Sub-pixel text
    // metrics and the row's own padding leave a little, never a column's worth.
    expect(columns.periodSlack).toBeLessThan(6);
    expect(columns.netSlack).toBeLessThan(6);

    // --- The Net column names its unit once, in the heading ---
    // ₪ and its NBSP are real glyphs, so a per-row symbol is width every row
    // pays to repeat what the column already says.
    const currency = await page.evaluate(() => {
      const rows = Array.from(
        document.querySelectorAll('[data-testid="ledger-row"]'),
      );
      const head = rows[0].parentElement!.querySelector(
        ":scope > div.grid-cols-subgrid",
      )!;
      return {
        heading: head.children[3].textContent || "",
        rowsWithShekel: rows.filter((r) =>
          (r.children[3].textContent || "").includes("₪"),
        ).length,
        // Every net still carries its own sign, with nothing between the
        // sign and the digits that bidi could reorder.
        allSigned: rows.every((r) =>
          /^[+-]\d/.test((r.children[3].textContent || "").replace(/[\u2066\u2069]/g, "")),
        ),
      };
    });
    expect(currency.heading).toContain("₪");
    expect(currency.rowsWithShekel).toBe(0);
    expect(currency.allSigned).toBe(true);

    // --- Each column scales off its own series, proportionally ---
    // Pooling income and expenses under one cap let the lumpy series (income
    // carries the bonuses and windfalls) set the scale the steady one had to
    // live on, pinning every expense bar to the bottom of its column.
    const scales = await page.evaluate(() => {
      const impliedCaps = (kind: string) =>
        Array.from(
          document.querySelectorAll(
            `[data-testid="ledger-bar"][data-kind="${kind}"]`,
          ),
        )
          .filter((bar) => (bar as HTMLElement).dataset.capped === "false")
          .map((bar) => {
            // The label is the bar's own ₪ figure; width is its share of the cap.
            const value = Number((bar.textContent || "").replace(/\D/g, ""));
            const pct = parseFloat((bar as HTMLElement).style.width);
            return { value, pct };
          })
          // Skip the 2% floor and the full-width end, where width no longer
          // tracks value.
          .filter((b) => b.value > 0 && b.pct > 2 && b.pct < 100)
          .map((b) => (b.value / b.pct) * 100);
      return { income: impliedCaps("income"), expense: impliedCaps("expense") };
    });

    // Every uncapped bar in a column implies the same cap — i.e. length stays
    // strictly proportional to ₪ within the column.
    for (const caps of [scales.income, scales.expense]) {
      expect(caps.length).toBeGreaterThan(1);
      for (const cap of caps) expect(cap).toBeCloseTo(caps[0], -2);
    }
    // ...and the two columns arrive at different caps, which they cannot do
    // from a shared pool. (Demo income is a flat salary while expenses vary,
    // so their medians are far apart — if demo data ever makes the two series
    // coincide, this is the assertion to revisit, not the split.)
    expect(Math.abs(scales.income[0] - scales.expense[0])).toBeGreaterThan(
      scales.income[0] * 0.05,
    );

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

    // --- Filter chips: pending-refunds, projects, loans ---
    // "Refunds Included/Excluded" is gone: a refund is a positive amount in an
    // expense category, so it already nets off the month it lands in, and the
    // opt-out only ever reached the ledger and the income KPI — never the
    // expense KPI beside them or either breakdown tab.
    await expect(
      card.getByRole("button", { name: /^Pending Refunds (Ex|In)cluded$/ }),
    ).toBeVisible();
    await expect(
      card.getByRole("button", { name: /^Loans (Ex|In)cluded$/ }),
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
    // Project spend is the lumpy kind — a wedding lands in two months — so
    // the chip has to be on for a month to run past the median-anchored cap
    // at all. It is off by default now that it reaches this tab: the
    // breakdown, the ledger and the KPI answer to the same chips, so a
    // category one of them excludes is excluded from all of them.
    await card.getByRole("button", { name: "Projects Excluded" }).click();
    await expect(card.getByRole("button", { name: "Projects Included" })).toBeVisible();

    // The meter is 3px tall with a 2px rounded cap. A diagonal hatch is all
    // but vertical over three pixels and the cap sheared both ends into
    // ragged points, so the bar read as torn rather than hatched — and which
    // rows showed it changed with every filter toggle. The stripes must stay
    // horizontal (90deg), which is the one direction the height cannot spoil.
    const overScaleFill = card
      .locator('[data-testid="composition-row"] div[title]:not([title=""]) > div')
      .first();
    await expect(overScaleFill).toBeVisible({ timeout: 20_000 });
    expect(
      await overScaleFill.evaluate((el) => getComputedStyle(el).backgroundImage),
    ).toContain("90deg");

    await card.getByRole("button", { name: "Projects Included" }).click();
    await expect(card.getByRole("button", { name: "Projects Excluded" })).toBeVisible();

    // Slices carry their readout here as well, and still print nothing.
    const expenseSegments = compositionRows.first().getByTestId("composition-segment");
    await expect(expenseSegments.first()).toBeVisible();
    for (const text of await expenseSegments.allTextContents()) {
      expect(text.trim()).toBe("");
    }

    await expenseSegments.first().hover();
    const expenseTooltip = page.getByTestId("composition-tooltip");
    await expect(expenseTooltip).toBeVisible({ timeout: 1_000 });
    // Nothing about a coloured band says it can be clicked, so the readout
    // that names the slice has to say it.
    await expect(expenseTooltip).toContainText("Click to filter");

    // --- Clicking a slice filters the tab down to that one series ---
    // The composition rows answer "what did this month consist of"; following
    // one colour down a stack of differently-ordered bars is the comparison
    // the eye is worst at, so the slice is also the control that pulls its
    // own series out over time.
    const clicked = await expenseSegments.first().getAttribute("aria-label");
    const clickedName = clicked!.split(":")[0];
    await expenseSegments.first().click();

    const focusRows = card.getByTestId("series-focus-row");
    await expect(focusRows.first()).toBeVisible({ timeout: 45_000 });
    await expect(card.getByTestId("series-focus-chip")).toContainText(clickedName);
    // One row per period, newest first, each with the series' share of that
    // period — the reading a composition bar cannot give.
    expect(await focusRows.count()).toBeGreaterThan(1);
    const focusMonths = await focusRows.evaluateAll((els) =>
      els.map((el) => el.getAttribute("data-month")),
    );
    expect(focusMonths[0]! > focusMonths[focusMonths.length - 1]!).toBe(true);
    await expect(focusRows.first()).toContainText("%");
    // The composition rows are gone while the filter is on.
    await expect(compositionRows).toHaveCount(0);

    // Escape is the dismissal people try without looking, and the focused
    // view is not a dialog, so nothing else would handle it.
    await page.keyboard.press("Escape");
    await expect(focusRows).toHaveCount(0);
    await expect(compositionRows.first()).toBeVisible();

    // A tab switch drops the filter too: the two tabs share no series names,
    // so a name carried across is a filter that matches nothing.
    await expenseSegments.first().click();
    await expect(card.getByTestId("series-focus-chip")).toBeVisible();
    await card.getByRole("button", { name: "Income Breakdown" }).click();
    await expect(card.getByTestId("series-focus-chip")).toHaveCount(0);
    await expect(compositionRows.first()).toBeVisible();
  });

  test("the all-time scope draws a donut with a legend, and both filter a series", async ({
    page,
  }) => {
    const card = await openCard(page);

    const scope = card.getByTestId("scope-toggle");
    await scope.getByRole("button", { name: "All time" }).click();

    // --- Totals: the whole history folds to a single labelled row ---
    // Income against expenses is not a part-whole relation, so this tab keeps
    // its bars and its Net — a donut here would be a lie about the figures.
    const rows = card.getByTestId("ledger-row");
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toHaveAttribute("data-month", "all");
    await expect(rows.first()).toContainText("All time");

    // The KPI drops its trend chip: there is no earlier "all time" to compare
    // against, and a 0% chip would read as "flat" rather than "not asked".
    const income = card.getByTestId("kpi-income");
    await expect(income.getByText("Per month")).toBeVisible();
    await expect(income.locator("span[title]")).toHaveCount(0);

    // --- Income Breakdown: a donut, with the legend closed by default ---
    await card.getByRole("button", { name: "Income Breakdown" }).click();
    await expect(card.getByTestId("donut-chart")).toBeVisible({ timeout: 45_000 });
    await expect(card.getByTestId("composition-row")).toHaveCount(0);
    await expect(card.getByTestId("breakdown-legend-row")).toHaveCount(0);

    await card.getByRole("button", { name: "Breakdown", exact: true }).click();
    const legendRows = card.getByTestId("breakdown-legend-row");
    await expect(legendRows.first()).toBeVisible();
    expect(await legendRows.count()).toBeGreaterThan(0);
    // The legend states the shares the donut only draws, and they add up.
    await expect(card.getByTestId("breakdown-legend-scroll")).toContainText("100.0%");

    // --- The window chips narrow what the donut folds ---
    const ranges = card.getByTestId("range-chips");
    const legendBefore = await legendRows.allTextContents();
    await ranges.getByRole("button", { name: "This year" }).click();
    await expect
      .poll(() => legendRows.allTextContents(), { timeout: 20_000 })
      .not.toEqual(legendBefore);
    await ranges.getByRole("button", { name: "All time" }).click();

    // --- A legend row filters, and drops back to months to have periods ---
    // A slice under a few percent is hard to hit, so the legend is the
    // reachable way to the same filter; and the focused view needs periods,
    // which the all scope by definition does not have.
    const firstLegend = await legendRows.first().textContent();
    await legendRows.first().click();

    const focusRows = card.getByTestId("series-focus-row");
    await expect(focusRows.first()).toBeVisible({ timeout: 45_000 });
    expect(await focusRows.count()).toBeGreaterThan(1);
    await expect(card.getByTestId("series-focus-chip")).toContainText(
      firstLegend!.trim().split(/\s{2,}/)[0],
    );
    await expect(scope.getByRole("button", { name: "Monthly" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    // The chip's ✕ is the visible dismissal; clicking it restores the mix.
    await card.getByTestId("series-focus-chip").click();
    await expect(focusRows).toHaveCount(0);
    await expect(card.getByTestId("composition-row").first()).toBeVisible();
  });

  test("the KPI, the ledger and the legend report one number, and the chips move all three", async ({
    page,
  }) => {
    const card = await openCard(page);
    await card.getByTestId("scope-toggle").getByRole("button", { name: "All time" }).click();

    /**
     * What the card says its expenses are, read in each of the three places.
     *
     * A chip toggles two queries at once, and they land independently, so a
     * reading taken the instant a chip is clicked can catch one series
     * refreshed and the other not. `settle` waits for the figure to stop
     * being the one from before the click.
     */
    const readings = async () => {
      await card.getByRole("button", { name: "Totals" }).click();
      const ledger = await card
        .locator('[data-testid="ledger-bar"][data-kind="expense"]')
        .first()
        .textContent();
      const kpi = await card.getByTestId("kpi-expense").getByTestId("kpi-primary").textContent();

      await card.getByRole("button", { name: "Expenses Breakdown" }).click();
      await expect(card.getByTestId("donut-chart")).toBeVisible({ timeout: 45_000 });
      const legendToggle = card.getByRole("button", { name: "Breakdown", exact: true });
      if ((await legendToggle.getAttribute("aria-expanded")) === "false") {
        await legendToggle.click();
      }
      await expect(card.getByTestId("breakdown-legend-scroll")).toBeVisible();
      const legend = await card
        .getByTestId("breakdown-legend-scroll")
        .locator("tfoot td")
        .nth(1)
        .textContent();
      return { ledger: ledger?.trim(), kpi: kpi?.trim(), legend: legend?.trim() };
    };

    /** Read again until the card has stopped showing `previous`, then report. */
    const settled = async (previous?: string) => {
      let current = await readings();
      if (previous !== undefined) {
        await expect
          .poll(
            async () => {
              current = await readings();
              return current.ledger;
            },
            { timeout: 30_000 },
          )
          .not.toBe(previous);
      }
      // One more pass once the figures have moved: the three readings are
      // taken from three tabs in sequence, and only the last of them is
      // guaranteed to have been read after the refetch finished.
      current = await readings();
      return current;
    };

    // The three used to be three endpoints with three definitions of
    // "expenses" — a budget-filtered KPI, a bank-bill ledger and a raw
    // itemized breakdown — which put three different all-time totals on one
    // screen. They are now one series summed three ways, so they must agree
    // to the shekel.
    const all = await settled();
    expect(all.kpi).toBe(all.ledger);
    expect(all.legend).toBe(all.ledger);
    expect(all.ledger).toMatch(/\d/);

    // --- And the chips move all three together ---
    // The projects chip used to reach only the ledger, and could not even
    // reach the project spend paid by credit card there: a bill row carries
    // the category "Credit Cards", so no category filter can see inside it.
    await card.getByRole("button", { name: "Projects Excluded" }).click();
    await expect(card.getByRole("button", { name: "Projects Included" })).toBeVisible();
    const withProjects = await settled(all.ledger);
    expect(withProjects.kpi).toBe(withProjects.ledger);
    expect(withProjects.legend).toBe(withProjects.ledger);
    expect(withProjects.ledger).not.toBe(all.ledger);

    // An opened legend survives a chip toggle. Each chip is part of the query
    // key, so a toggle is a different query with no data of its own — without
    // `keepPreviousData` the card empties out, the "no data" line flashes and
    // the remount closes the legend under the reader.
    await expect(
      card.getByRole("button", { name: "Breakdown", exact: true }),
    ).toHaveAttribute("aria-expanded", "true");
    await expect(card.getByTestId("breakdown-legend-row").first()).toBeVisible();

    // Debt payments are money out by default; excluding them takes the
    // envelope view, and must move every reading at once.
    await card.getByRole("button", { name: "Loans Included" }).click();
    await expect(card.getByRole("button", { name: "Loans Excluded" })).toBeVisible();
    const withoutDebt = await settled(withProjects.ledger);
    expect(withoutDebt.kpi).toBe(withoutDebt.ledger);
    expect(withoutDebt.legend).toBe(withoutDebt.ledger);
    expect(withoutDebt.ledger).not.toBe(withProjects.ledger);
    // Demo data's mortgage and car loan are a big share of the outflow, so
    // dropping them can only make the figure smaller.
    const digits = (value: string | undefined) => Number((value ?? "").replace(/\D/g, ""));
    expect(digits(withoutDebt.ledger)).toBeLessThan(digits(withProjects.ledger));
  });

  // Its own test on purpose: it needs Hebrew seeded before the app boots, so
  // it cannot share the journey test's page.
  test("an over-scale bar marks its growing tip under RTL", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("language", "he"));
    await navigateTo(page, "/");
    const card = cardContainer(page);
    await expect(card).toBeVisible({ timeout: 45_000 });
    await card.scrollIntoViewIfNeeded();

    const bars = card.locator('[data-testid="ledger-bar"][data-capped="true"]');
    await expect(bars.first()).toBeVisible({ timeout: 45_000 });

    // Flexbox anchors each bar on the inline axis, so in Hebrew an income bar
    // grows to the right and an expense bar to the left — the mirror of LTR.
    // The hatch and the dashed edge mark the *growing* tip, so both have to
    // follow. They were physical (`left` / `borderLeftColor`), which pinned
    // them to the anchored end that never moves.
    const marks = await bars.evaluateAll((els) =>
      els.map((el) => {
        const cs = getComputedStyle(el);
        const bar = el.getBoundingClientRect();
        const hatch = el
          .querySelector('[data-testid="ledger-bar-hatch"]')!
          .getBoundingClientRect();
        return {
          kind: el.getAttribute("data-kind"),
          dashedLeft: cs.borderLeftStyle === "dashed",
          dashedRight: cs.borderRightStyle === "dashed",
          // Which half of the bar the hatched strip sits in.
          hatchOnRight: hatch.left + hatch.width / 2 > bar.left + bar.width / 2,
        };
      }),
    );
    // Demo data reliably caps at least one bar (an income month well above the
    // median); both kinds are marked from the same logical mapping, so
    // whichever ones are capped here prove the direction handling.
    expect(marks.length).toBeGreaterThan(0);

    for (const mark of marks) {
      if (mark.kind === "income") {
        expect(mark.dashedRight).toBe(true);
        expect(mark.dashedLeft).toBe(false);
        expect(mark.hatchOnRight).toBe(true);
      } else {
        expect(mark.dashedLeft).toBe(true);
        expect(mark.dashedRight).toBe(false);
        expect(mark.hatchOnRight).toBe(false);
      }
    }
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

    // A chip refetches income and expenses as two independent queries, and
    // the bars sampled below are scaled per column — the income bars by the
    // income series, the expense bars by the expense one. Waiting on a single
    // KPI therefore reads the bars while half the card is still on the
    // previous answer, which is exactly the transient this test is otherwise
    // about. Both KPIs have to be back before the borders mean anything.
    const expenseKpi = card.getByTestId("kpi-expense");
    const incomeKpi = card.getByTestId("kpi-income");
    await expect(expenseKpi).toContainText(/\d,\d{3}/, { timeout: 45_000 });
    await expect(incomeKpi).toContainText(/\d,\d{3}/, { timeout: 45_000 });
    const kpis = async () =>
      `${await incomeKpi.textContent()}|${await expenseKpi.textContent()}`;
    const kpiBefore = await kpis();
    const bordersBefore = await barBorders();
    expect(bordersBefore.length).toBeGreaterThan(0);

    // The projects chip is the one that moves a cap *among the rows on
    // screen*. The scale is anchored to the median of the whole history, but
    // the ledger shows the last 12 periods, so a toggle only shows here if it
    // flips a bar inside that window: project spend lands in recent months
    // and takes four expense bars over the cap, while the loans chip's
    // capped months are all older than the window.
    const projectsChip = card.getByRole("button", { name: /^Projects (Ex|In)cluded$/ });
    await projectsChip.click();
    await expect.poll(kpis, { timeout: 20_000 }).not.toBe(kpiBefore);
    // Some bar has to take a cap here, or the round trip proves nothing.
    expect(await barBorders()).not.toEqual(bordersBefore);

    await projectsChip.click();
    await expect.poll(kpis, { timeout: 20_000 }).toBe(kpiBefore);
    // Read the settled state once: polling until the borders matched would
    // pass on the first frame that happened to agree, which is the transient
    // this defect hides behind.
    expect(await barBorders()).toEqual(bordersBefore);
  });
});
