import { test, expect, request, type Page, type Route } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData, scrollFeedUntil } from "./helpers";

/**
 * The row actions of a monthly-budget list answer on click, as a retag does
 * (`budget-retag-refresh.spec.ts`): marking a pending refund, moving a row to
 * the previous month and splitting it all change the list and the rule's
 * figures while the write itself is still held — so nothing the server says
 * can be what changed them — and the server's answer agrees once it lands.
 */

interface LedgerTx {
  unique_id: number | string;
  source: string;
  category: string | null;
  amount: number;
  date: string;
  split_id?: number | null;
}

interface AnalysisRule {
  rule: { name: string };
  data: LedgerTx[];
}

const rowKey = (tx: { source: string; unique_id: number | string }) => `${tx.source}_${tx.unique_id}`;

/**
 * An expense of the current month that a named monthly rule holds, dated in
 * the month itself (so it can move back one), not split, not cash, and with
 * no refund on it.
 */
async function pickRuleExpense(): Promise<{ tx: LedgerTx; rule: string }> {
  const now = new Date();
  const ctx = await request.newContext({ extraHTTPHeaders: { "X-FAD-Demo": "1" } });
  try {
    const [analysis, refunds] = await Promise.all([
      ctx.get(`${API_BASE}/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`),
      ctx.get(`${API_BASE}/pending-refunds/`),
    ]);
    expect(analysis.ok()).toBeTruthy();
    const { rules } = (await analysis.json()) as { rules: AnalysisRule[] };
    const marked = new Set(
      ((await refunds.json()) as { source_table: string; source_id: number }[]).map(
        (r) => `${r.source_table}_${r.source_id}`,
      ),
    );
    const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    for (const { rule, data } of rules) {
      if (rule.name === "Total Budget" || rule.name === "Other Expenses") continue;
      const tx = data.find(
        (row) =>
          row.amount < -10 &&
          row.category &&
          row.split_id == null &&
          row.source !== "cash_transactions" &&
          row.date.startsWith(month) &&
          !marked.has(rowKey(row)),
      );
      if (tx) return { tx, rule: rule.name };
    }
    throw new Error("demo data has no plain rule expense this month");
  } finally {
    await ctx.dispose();
  }
}

/** The figures cell of one monthly rule row, e.g. "120 ₪ / 800 ₪". */
const ruleFigures = (page: Page, name: string) =>
  page
    .locator("div.rounded-xl", { has: page.getByText(name, { exact: true }) })
    .getByTestId("ledger-figures")
    .filter({ visible: true })
    .first();

const visibleRow = (page: Page, key: string) =>
  page.locator(`[data-tx-key="${key}"]`).filter({ visible: true });

/** Hold every request a predicate matches until `release` is called. */
async function hold(page: Page, url: string, method: string) {
  const held: Route[] = [];
  let holding = true;
  await page.route(url, (route) =>
    holding && route.request().method() === method ? held.push(route) : route.continue(),
  );
  return {
    sent: () => held.length > 0,
    release: async () => {
      holding = false;
      await Promise.all(held.map((route) => route.continue()));
    },
  };
}

/** Open the Monthly tab, expand `rule`'s list and bring `tx`'s row on screen. */
async function openRow(page: Page, rule: string, tx: LedgerTx) {
  await navigateTo(page, "/budget");
  await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
  await expect(page.getByTestId("budget-status-band")).toBeVisible({ timeout: 30_000 });
  await page.getByText(rule, { exact: true }).first().click();
  const list = page.getByTestId("budget-tx-list").filter({ visible: true }).first();
  const row = visibleRow(page, rowKey(tx));
  expect(await scrollFeedUntil(list.locator("[data-scroll-root]"), row)).toBe(true);
  return row;
}

/** Wait for the current month's analysis to be fetched again and answered. */
const monthRefetched = (page: Page) => {
  const now = new Date();
  return page.waitForResponse(
    (r) =>
      r.url().includes(`/api/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`) && r.ok(),
  );
};

test.describe("Monthly budget row actions answer on click", () => {
  test.beforeEach(async ({ page }) => {
    await resetDemoData();
    await enableDemoMode(page);
  });

  test("marking a pending refund badges the row and takes its cost off the rule", async ({ page }) => {
    const { tx, rule } = await pickRuleExpense();
    const row = await openRow(page, rule, tx);
    const before = (await ruleFigures(page, rule).textContent()) ?? "";

    const write = await hold(page, "**/api/pending-refunds/", "POST");
    await row.getByTitle("Mark as pending refund").click();

    await expect(row.getByTitle("Pending refund")).toBeVisible();
    await expect(ruleFigures(page, rule)).not.toHaveText(before);
    const patched = (await ruleFigures(page, rule).textContent()) ?? "";
    expect(write.sent()).toBe(true);

    const refetched = monthRefetched(page);
    await write.release();
    await refetched;
    await expect(ruleFigures(page, rule)).toHaveText(patched);
    await expect(row.getByTitle("Pending refund")).toBeVisible();
  });

  test("a refused refund mark undoes itself and says so", async ({ page }) => {
    const { tx, rule } = await pickRuleExpense();
    const row = await openRow(page, rule, tx);
    const before = (await ruleFigures(page, rule).textContent()) ?? "";

    let refuse: () => Promise<void> = async () => {};
    const sent = new Promise<void>((resolve) => {
      void page.route("**/api/pending-refunds/", (route) => {
        if (route.request().method() !== "POST") return route.continue();
        refuse = () => route.fulfill({ status: 500, json: { detail: "Internal server error" } });
        resolve();
      });
    });
    await row.getByTitle("Mark as pending refund").click();
    await sent;
    await expect(row.getByTitle("Pending refund")).toBeVisible();
    await expect(ruleFigures(page, rule)).not.toHaveText(before);

    await refuse();

    await expect(page.getByText("Couldn't save that change, so it was undone.")).toBeVisible();
    await expect(row.getByTitle("Mark as pending refund")).toBeVisible();
    await expect(ruleFigures(page, rule)).toHaveText(before);
  });

  test("moving a row to the previous month takes it and its cost out of this month", async ({ page }) => {
    const { tx, rule } = await pickRuleExpense();
    const row = await openRow(page, rule, tx);
    const before = (await ruleFigures(page, rule).textContent()) ?? "";

    const write = await hold(page, "**/api/budget-month-overrides/", "POST");
    await row.getByRole("button", { name: "More actions" }).click();
    await page.getByTitle("Count in previous month's budget").filter({ visible: true }).click();

    await expect(visibleRow(page, rowKey(tx))).toHaveCount(0);
    await expect(ruleFigures(page, rule)).not.toHaveText(before);
    const patched = (await ruleFigures(page, rule).textContent()) ?? "";
    expect(write.sent()).toBe(true);

    const refetched = monthRefetched(page);
    await write.release();
    await refetched;
    await expect(ruleFigures(page, rule)).toHaveText(patched);
    await expect(visibleRow(page, rowKey(tx))).toHaveCount(0);
  });

  test("splitting a row closes the dialog and lists its parts at once", async ({ page }) => {
    const { tx, rule } = await pickRuleExpense();
    const row = await openRow(page, rule, tx);
    const before = (await ruleFigures(page, rule).textContent()) ?? "";

    await row.getByTitle("Split transaction").click();
    const dialog = page.getByRole("dialog", { name: /split transaction/i });
    await dialog.getByRole("button", { name: /select category/i }).click();
    await page.getByRole("listbox").getByRole("option", { name: tx.category!, exact: true }).click();

    const write = await hold(page, `**/api/transactions/${tx.unique_id}/split`, "POST");
    await dialog.getByRole("button", { name: /^split transaction$/i }).click();

    await expect(dialog).toBeHidden();
    await expect(visibleRow(page, rowKey(tx))).toHaveCount(0);
    await expect(
      page.locator(`[data-tx-key^="${tx.source}_split_pending_${tx.unique_id}_"]`).filter({ visible: true }),
    ).toHaveCount(2);
    // Both halves stay in the same category, so the rule spends the same.
    await expect(ruleFigures(page, rule)).toHaveText(before);
    expect(write.sent()).toBe(true);

    const refetched = monthRefetched(page);
    await write.release();
    await refetched;
    await expect(page.locator(`[data-tx-key^="${tx.source}_split_"]`).filter({ visible: true })).toHaveCount(
      2,
    );
    await expect(page.locator(`[data-tx-key*="split_pending"]`)).toHaveCount(0);
    await expect(ruleFigures(page, rule)).toHaveText(before);
  });
});
