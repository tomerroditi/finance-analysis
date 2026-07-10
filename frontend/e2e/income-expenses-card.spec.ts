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

  test("Totals tab renders the ledger newest-first with a Net column", async ({ page }) => {
    const card = await openCard(page);

    // Header labels for the ledger.
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
  });

  test("Income Breakdown shows composition rows and the % / ₪ toggle works", async ({ page }) => {
    const card = await openCard(page);

    await card.getByRole("button", { name: "Income Breakdown" }).click();

    const rows = card.getByTestId("composition-row");
    await expect(rows.first()).toBeVisible({ timeout: 45_000 });
    const before = await rows.count();
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
  });

  test("Expenses Breakdown renders composition rows", async ({ page }) => {
    const card = await openCard(page);

    await card.getByRole("button", { name: "Expenses Breakdown" }).click();

    const rows = card.getByTestId("composition-row");
    await expect(rows.first()).toBeVisible({ timeout: 45_000 });
    expect(await rows.count()).toBeGreaterThan(0);

    // Toggle is present here too and defaults to share.
    await expect(card.getByRole("button", { name: "Show amount (₪)" })).toBeVisible();
  });

  test("KPI cards summarise income and expenses with period labels", async ({ page }) => {
    const card = await openCard(page);

    const income = card.getByTestId("kpi-income");
    const expenses = card.getByTestId("kpi-expense");
    await expect(income).toBeVisible();
    await expect(expenses).toBeVisible();

    // Each card leads with a 12-month average and keeps the 3M/6M windows.
    await expect(income.getByText("12-mo avg")).toBeVisible();
    await expect(income.getByText("3M", { exact: true })).toBeVisible();
    await expect(income.getByText("6M", { exact: true })).toBeVisible();

    // Income averages come straight from the loaded series — a real thousands
    // figure (e.g. "30,321"), not a zero placeholder. (Currency uses an NBSP
    // before ₪, so match just the grouped number.)
    await expect(income).toContainText(/\d,\d{3}/);
  });
});
