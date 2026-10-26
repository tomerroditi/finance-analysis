import { test, expect, request, type Page, type Route } from "@playwright/test";
import { API_BASE, enableDemoMode, navigateTo, resetDemoData, scrollFeedUntil } from "./helpers";

/**
 * Retagging a transaction from a monthly-budget rule's list moves it to its
 * new rule on click, before the server has answered — and a reload straight
 * after the write must still show it there.
 *
 * The reload is the regression: the query cache is restored from IndexedDB,
 * whose snapshot is written through a throttle and so can predate the write.
 * Restored entries kept their original fetch time, anything younger than
 * `staleTime` was trusted as fresh, and the pre-write budget stuck on screen
 * across reloads.
 */

interface LedgerTx {
  unique_id: number;
  source: string;
  category: string | null;
  amount: number;
}

interface AnalysisRule {
  rule: { name: string };
  current_amount: number;
  data: LedgerTx[];
}

const TARGET_RULE = "Entertainment Budget";
const TARGET_CATEGORY = "Entertainment";

/** An untagged expense the current month's "Other Expenses" list holds. */
async function pickUntaggedExpense(): Promise<LedgerTx> {
  const now = new Date();
  const ctx = await request.newContext({ extraHTTPHeaders: { "X-FAD-Demo": "1" } });
  try {
    const res = await ctx.get(
      `${API_BASE}/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`,
    );
    expect(res.ok()).toBeTruthy();
    const { rules } = (await res.json()) as { rules: AnalysisRule[] };
    const other = rules.find((r) => r.rule.name === "Other Expenses");
    const tx = other?.data.find(
      (row) => !row.category && row.amount < 0 && row.source !== "cash_transactions",
    );
    if (!tx) throw new Error("demo data has no untagged expense this month");
    return tx;
  } finally {
    await ctx.dispose();
  }
}

/** The figures cell of one monthly rule row, e.g. "0 ₪ / 800 ₪". */
const ruleFigures = (page: Page, name: string) =>
  page
    .locator("div.rounded-xl", { has: page.getByText(name, { exact: true }) })
    .getByTestId("ledger-figures")
    .filter({ visible: true })
    .first();

const rowKey = (tx: LedgerTx) => `${tx.source}_${tx.unique_id}`;

/**
 * Find the row in the expanded pool's list and stage a retag into the target
 * rule in its inline editor, up to the Done click. The pool lists through the
 * transaction feed, which mounts rows in batches as it scrolls.
 */
async function stageRetag(page: Page, tx: LedgerTx) {
  const list = page.getByTestId("budget-tx-list").filter({ visible: true }).first();
  const row = page.locator(`[data-tx-key="${rowKey(tx)}"]`).filter({ visible: true });
  expect(await scrollFeedUntil(list.locator("[data-scroll-root]"), row)).toBe(true);
  await row.getByRole("button", { name: "Edit category / tag" }).first().click();
  const editor = row.getByTestId("recent-tx-editor");
  await editor.getByRole("button").nth(0).click();
  await page.getByRole("listbox").getByRole("option", { name: TARGET_CATEGORY, exact: true }).click();
  await editor.getByRole("button").nth(1).click();
  await page.getByRole("listbox").getByRole("option").first().click();
}

const applyButton = (page: Page) =>
  page.getByTestId("recent-tx-editor").getByRole("button", { name: "Done" });

async function openMonthly(page: Page) {
  await page.getByRole("button", { name: /^Monthly Budget$/i }).click();
  await expect(page.getByTestId("budget-status-band")).toBeVisible({ timeout: 30_000 });
}

test.describe("Monthly budget retag", () => {
  test.beforeAll(async () => {
    await resetDemoData();
  });

  test.beforeEach(async ({ page }) => {
    await enableDemoMode(page);
  });

  test("a retagged row moves rules and survives an immediate reload", async ({ page }) => {
    const tx = await pickUntaggedExpense();

    await navigateTo(page, "/budget");
    await openMonthly(page);
    const before = (await ruleFigures(page, TARGET_RULE).textContent()) ?? "";

    await page.getByText("Other Expenses", { exact: true }).first().click();
    await stageRetag(page, tx);

    // Give the persister time to write the pre-write snapshot, as it would
    // for anyone who looked at the page for a moment before tagging.
    await page.waitForTimeout(1500);

    const written = page.waitForResponse(
      (r) => r.url().includes(`/transactions/${tx.unique_id}/tag`) && r.ok(),
    );
    await applyButton(page).click();
    await written;

    await page.reload();
    await openMonthly(page);
    await expect(ruleFigures(page, TARGET_RULE)).not.toHaveText(before, { timeout: 15_000 });

    await page.getByText("Other Expenses", { exact: true }).first().click();
    await expect(page.getByTestId("budget-tx-list").getByTestId("recent-tx-row").first()).toBeVisible();
    await expect(page.locator(`[data-tx-key="${rowKey(tx)}"]`)).toHaveCount(0);
  });

  test("the row moves on click, before the server has answered", async ({ page }) => {
    const tx = await pickUntaggedExpense();

    // Hold every month's analysis once the write is sent, so nothing the
    // server says can be what moves the row.
    let holding = false;
    const held: Route[] = [];
    await page.route("**/api/budget/analysis/**", (route) =>
      holding ? held.push(route) : route.continue(),
    );

    await navigateTo(page, "/budget");
    await openMonthly(page);
    const before = (await ruleFigures(page, TARGET_RULE).textContent()) ?? "";
    await page.getByText("Other Expenses", { exact: true }).first().click();
    await stageRetag(page, tx);

    const requested: string[] = [];
    page.on("request", (req) => {
      if (holding || held.length > 0) requested.push(new URL(req.url()).pathname);
    });
    holding = true;
    await applyButton(page).click();

    await expect(ruleFigures(page, TARGET_RULE)).not.toHaveText(before);
    await expect(page.locator(`[data-tx-key="${rowKey(tx)}"]`)).toHaveCount(0);
    const patched = (await ruleFigures(page, TARGET_RULE).textContent()) ?? "";

    // The server's answer lands and agrees with what the click showed.
    holding = false;
    await Promise.all(held.map((route) => route.continue()));
    await page.waitForLoadState("networkidle");
    await expect(ruleFigures(page, TARGET_RULE)).toHaveText(patched);

    // Only what the retag could change is fetched again: its own month, not
    // the neighbours already cached, and none of the reads a tag cannot move.
    const now = new Date();
    const analyses = requested.filter((path) => path.includes("/budget/analysis/"));
    expect(analyses.length).toBeGreaterThan(0);
    expect(new Set(analyses)).toEqual(
      new Set([`/api/budget/analysis/${now.getFullYear()}/${now.getMonth() + 1}`]),
    );
    for (const unchanged of ["/budget/projects/status", "/budget/category-conflicts", "/onboarding/status"]) {
      expect(requested.filter((path) => path.endsWith(unchanged))).toEqual([]);
    }
  });
});
