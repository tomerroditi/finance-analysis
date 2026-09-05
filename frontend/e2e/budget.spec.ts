import { test, expect } from "@playwright/test";
import { enableDemoMode, navigateTo, expectPageTitle, resetDemoData } from "./helpers";

test.describe("Budget", () => {
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

  // Every check here is a read-only interaction (tab switches, month
  // navigation, collapse/expand toggles), so they run as one journey on a
  // single navigation — the /budget cold load is the expensive step and it
  // used to be paid once per assertion group (8×).
  test("tabs, month navigation, trend figure, card toggles, and projects jump on one load", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");
    await expectPageTitle(page, /Budget/);

    // --- Both tabs visible ---
    await expect(page.getByText(/Monthly Budget/i)).toBeVisible();
    await expect(page.getByText(/Project Budgets/i)).toBeVisible();

    // --- Tab switching: Projects hides the month header, Monthly restores it ---
    await page.getByText(/Project Budgets/i).click();
    await expect(
      page.getByRole("button", { name: "Previous" }).first(),
    ).toBeHidden();

    await page.getByText(/Monthly Budget/i).click();
    const prevMonth = page.getByRole("button", { name: "Previous" }).first();
    const nextMonth = page.getByRole("button", { name: "Next" }).first();
    await expect(prevMonth).toBeVisible();

    // --- Month navigation ---
    const monthLabel = page
      .locator("h2")
      .filter({ hasText: /\w+ \d{4}/ })
      .first();
    const initialMonth = await monthLabel.textContent();

    await prevMonth.click();
    await expect(monthLabel).not.toHaveText(initialMonth ?? "");

    await nextMonth.click();
    await expect(monthLabel).toHaveText(initialMonth ?? "");

    // --- Budget-vs-actual lives in the summary band, not a card of its own ---
    // The dedicated rail chart was removed: it restated the band's trend
    // figure, so the band is now the only place this appears.
    const band = page.getByTestId("budget-status-band");
    await expect(band).toBeVisible();
    await expect(band.getByText(/Budget vs Actual/i)).toBeVisible();
    await expect(page.locator(".recharts-wrapper")).toHaveCount(0);

    // The figure carries the trailing months and the Total Budget cap in its
    // accessible label — if the old per-category-rule sum had crept back, the
    // budget it names would be smaller than the gauge's cap.
    const bandTrend = band.getByTestId("rule-sparkline");
    await expect(bandTrend).toBeVisible();
    await expect(bandTrend.locator("svg")).toHaveAttribute(
      "aria-label",
      /Budget\s/,
    );

    // --- Total Budget card collapses the rule list and shows month transactions ---
    const totalBudget = page.getByRole("button", {
      name: /^\s*Total Budget\s*$/,
    });
    if (
      await totalBudget
        .first()
        .isVisible()
        .catch(() => false)
    ) {
      // Collapsing hides the per-rule rows; expanding shows them again.
      await totalBudget.first().click();
      await page.waitForTimeout(400);
      await totalBudget.first().click();
      await page.waitForTimeout(400);

      // "View month transactions" reveals a transactions table under the card.
      const viewMonth = page.getByRole("button", {
        name: /View month transactions/i,
      });
      if (
        await viewMonth
          .first()
          .isVisible()
          .catch(() => false)
      ) {
        await viewMonth.first().click();
        await page.waitForTimeout(500);
        await expect(
          page.getByRole("button", { name: /Hide Transactions/i }).first(),
        ).toBeVisible();
      }
    }

    // --- Pending Refunds section collapses from its header ---
    const refundsHeader = page.getByRole("button", {
      name: /Pending Refunds/i,
    });
    if (
      await refundsHeader
        .first()
        .isVisible()
        .catch(() => false)
    ) {
      await refundsHeader.first().click();
      await page.waitForTimeout(300);
      await refundsHeader.first().click();
      await page.waitForTimeout(300);
      await expect(refundsHeader.first()).toBeVisible();
    }

    // --- Per-rule trend column ---
    // Every budgeted envelope carries its own sparkline on top of the band's
    // figure, and the summary in its aria-label names each month plus the
    // reference figure, so the status is never conveyed by colour alone.
    const sparklines = page.getByTestId("rule-sparkline");
    await expect(sparklines.first()).toBeVisible();
    expect(await sparklines.count()).toBeGreaterThan(1);
    const monthlyLabel = await sparklines.first().locator("svg").getAttribute("aria-label");
    expect(monthlyLabel).toBeTruthy();
    expect(monthlyLabel).toMatch(/Budget/i);

    // Monthly rules plot discrete bars against a dashed budget line; the
    // yearly tab plots a cumulative burn line instead (different question,
    // different mark), so the two must not render the same element type.
    // Counted, not `toBeVisible`: a month with no spend draws a zero-height
    // bar, and the leading month of a 12-month series is often exactly that.
    expect(await sparklines.first().locator("rect").count()).toBeGreaterThan(0);
    await expect(sparklines.first().locator("polyline")).toHaveCount(0);

    await page.getByRole("button", { name: /^Yearly$/i }).click();
    const yearlySpark = page.getByTestId("rule-sparkline").first();
    if (await yearlySpark.isVisible().catch(() => false)) {
      await expect(yearlySpark.locator("polyline")).toHaveCount(1);
      await expect(yearlySpark.locator("rect")).toHaveCount(0);
    }
    await page.getByText(/Monthly Budget/i).click();
    await expect(prevMonth).toBeVisible();

    // --- 'View all projects' jumps to the Projects tab ---
    const viewAll = page.getByRole("button", { name: /View all projects/i });
    if (await viewAll.isVisible().catch(() => false)) {
      await viewAll.click();
      await page.waitForTimeout(400);
      // Projects tab content: the project selector label appears.
      await expect(page.getByText(/Select Project/i).first()).toBeVisible();
    }
  });

  // Its own test because the assertion is about layout at a mobile width.
  // The tab bar previously used `flex-1` + `whitespace-nowrap`, so the three
  // tabs could not shrink below their text and pushed the document 53px past
  // the viewport — the whole page scrolled sideways on a phone.
  test("does not scroll horizontally at mobile width", async ({ page }) => {
    await navigateTo(page, "/budget");
    await expect(page.getByRole("navigation").first()).toBeVisible();

    await page.setViewportSize({ width: 375, height: 812 });
    // Anchor on the tab bar so the measurement can't race an unlaid-out page.
    await expect(
      page.getByRole("button", { name: /Project Budgets/i }).first(),
    ).toBeVisible();

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
  });

  test("over-budget rules are flagged inline; the alerts toggle gates the bell", async ({
    page,
  }) => {
    await navigateTo(page, "/budget");

    // The budget page no longer carries an alerts banner: every rule row
    // already shows a rose dot, an over-by figure and a >100% percentage, so
    // a strip restating "N budgets need attention" only pushed those rows down.
    await expect(page.getByTestId("budget-status-band")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText(/budgets need attention/i)).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Dismiss all/i })).toHaveCount(0);

    // The bell in the app shell is the surviving alerts surface, and the
    // Settings toggle still gates it.
    const bell = page.getByRole("button", { name: /Budget Alerts/i }).first();
    await expect(bell).toBeVisible();

    // The settings control is a <label>; the mobile drawer tile uses a
    // <span>, so scope to the label.
    await page.getByRole("button", { name: "Settings" }).first().click();
    const toggleRow = page
      .locator("label", { hasText: "Budget Alerts" })
      .first();
    await expect(toggleRow).toBeVisible();
    await toggleRow.click();
    await page.keyboard.press("Escape");

    await expect(page.getByRole("button", { name: /Budget Alerts/i })).toHaveCount(0);
  });
});
