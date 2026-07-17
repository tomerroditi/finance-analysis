import { test, expect, type Page, type Locator } from "@playwright/test";
import { enableDemoMode, disableDemoMode, navigateTo } from "./helpers";

/**
 * The redesigned "Income & Expenses" dashboard card. It replaces the old
 * horizontal Plotly bars with:
 *   - Totals tab      → a statement-style ledger (one row per month, newest
 *                       on top, income/expense bars + a Net figure).
 *   - Income/Expenses → 100%-composition rows (`data-testid="composition-row"`)
 *                       with a % / ₪ label toggle.
 *
 * This spec guards that each tab renders, that the ledger is ordered
 * newest-first, and that the label toggle + tab switches never crash the card.
 * Demo Mode supplies the sample data.
 *
 * All checks are client-side interactions on one rendered card, so they run
 * as a single test on a single dashboard load — the cold dashboard boot is
 * by far the most expensive step, and it used to be paid once per assertion
 * group (5×).
 */
test.describe("Income & Expenses dashboard card", () => {
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
    await expect(card.getByRole("heading", { name: "Income & Expenses" })).toBeVisible({
      timeout: 45_000,
    });
    return card;
  }

  test("tabs, ledger, KPIs, pager, and label toggles all behave on one load", async ({ page }) => {
    const card = await openCard(page);

    // --- Totals tab: ledger renders newest-first with a Net column ---
    await expect(card.getByText("Month", { exact: true }).first()).toBeVisible();
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

    // --- Income Breakdown: composition rows and the % / ₪ toggle ---
    await card.getByRole("button", { name: "Income Breakdown" }).click();

    const compositionRows = card.getByTestId("composition-row");
    await expect(compositionRows.first()).toBeVisible({ timeout: 45_000 });
    const before = await compositionRows.count();
    expect(before).toBeGreaterThan(0);

    // The label toggle appears only on breakdown tabs. Default is share (%).
    const amountBtn = card.getByRole("button", { name: "Show amount (₪)" });
    const shareBtn = card.getByRole("button", { name: "Show share (%)" });
    await expect(amountBtn).toBeVisible();
    await expect(shareBtn).toHaveAttribute("aria-pressed", "true");

    // Flip to amounts, then back — the rows must survive both.
    await amountBtn.click();
    await expect(amountBtn).toHaveAttribute("aria-pressed", "true");
    await expect(card.getByTestId("composition-row")).toHaveCount(before);

    await shareBtn.click();
    await expect(shareBtn).toHaveAttribute("aria-pressed", "true");
    await expect(card.getByTestId("composition-row")).toHaveCount(before);

    // --- Expenses Breakdown renders composition rows too ---
    await card.getByRole("button", { name: "Expenses Breakdown" }).click();

    await expect(compositionRows.first()).toBeVisible({ timeout: 45_000 });
    expect(await compositionRows.count()).toBeGreaterThan(0);

    // Toggle is present here too and defaults to share.
    await expect(card.getByRole("button", { name: "Show amount (₪)" })).toBeVisible();
  });
});
