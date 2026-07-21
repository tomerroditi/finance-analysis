import { test, expect } from "@playwright/test";
import {
  API_BASE,
  enableDemoMode,
  disableDemoMode,
  navigateTo,
} from "./helpers";

/**
 * Redesigned Refunds experience (Transactions → Refunds tab).
 *
 * Covers the multi-link refund model end to end through the UI:
 * - summary cards (outstanding / received / unallocated refund money)
 * - search + per-card progress with the ALLOCATED amount (not the full
 *   transaction amount — regression guard for the enrichment overwrite bug)
 * - linking the SAME incoming transaction to a second pending refund via
 *   the link modal (the old model rejected any reuse of a transaction)
 * - the "By Refund Source" view showing per-transaction allocation and the
 *   money still available for further matching
 *
 * Mutating spec: seeds its own pending refunds via the API in beforeAll and
 * relies on the demo-DB re-copy on the next demo-mode enable for cleanup.
 */

interface ApiTxn {
  unique_id: number;
  source: string;
  amount: number;
  description?: string;
  desc?: string;
}

const descOf = (t: ApiTxn) => t.description ?? t.desc ?? "";

test.describe("Refunds redesign", () => {
  let expense1: ApiTxn;
  let expense2: ApiTxn;
  let income: ApiTxn;
  let p2Id: number;

  test.beforeAll(async ({ request }) => {
    await enableDemoMode();

    const txns: ApiTxn[] = await (
      await request.get(`${API_BASE}/transactions/`)
    ).json();
    const pendings: { source_table: string; source_id: number }[] = await (
      await request.get(`${API_BASE}/pending-refunds/`)
    ).json();
    const marked = new Set(
      pendings.map((p) => `${p.source_table}_${p.source_id}`),
    );

    const expenses = txns.filter(
      (t) =>
        t.amount < -20 &&
        descOf(t).length > 2 &&
        !marked.has(`${t.source}_${t.unique_id}`),
    );
    expense1 = expenses[0];
    expense2 = expenses.find((t) => descOf(t) !== descOf(expense1))!;
    expect(expense1, "demo data must contain expense transactions").toBeTruthy();
    expect(expense2, "demo data must contain a second expense").toBeTruthy();

    // A distinct incoming transaction big enough to fund both refunds (7 + 5)
    // with a leftover to show up as "available". Demo data already allocates
    // some incoming transactions to refunds — account for that.
    const sources: {
      refund_source: string;
      refund_transaction_id: number;
      total_allocated: number;
    }[] = await (
      await request.get(`${API_BASE}/pending-refunds/refund-sources`)
    ).json();
    const allocated = new Map(
      sources.map((s) => [
        `${s.refund_source}_${s.refund_transaction_id}`,
        s.total_allocated,
      ]),
    );
    income = txns
      .filter(
        (t) =>
          t.amount >= 20 &&
          descOf(t).length > 2 &&
          t.amount - (allocated.get(`${t.source}_${t.unique_id}`) ?? 0) >= 20,
      )
      .sort((a, b) => a.amount - b.amount)[0];
    expect(income, "demo data must contain an incoming transaction").toBeTruthy();

    const r1 = await request.post(`${API_BASE}/pending-refunds/`, {
      data: {
        source_type: "transaction",
        source_id: expense1.unique_id,
        source_table: expense1.source,
        expected_amount: 7,
      },
    });
    expect(r1.ok()).toBeTruthy();
    const p1Id = (await r1.json()).id;

    const r2 = await request.post(`${API_BASE}/pending-refunds/`, {
      data: {
        source_type: "transaction",
        source_id: expense2.unique_id,
        source_table: expense2.source,
        expected_amount: 5,
      },
    });
    expect(r2.ok()).toBeTruthy();
    p2Id = (await r2.json()).id;

    // Fully settle refund #1 from the shared income transaction.
    const l1 = await request.post(`${API_BASE}/pending-refunds/${p1Id}/link`, {
      data: {
        refund_transaction_id: income.unique_id,
        refund_source: income.source,
        amount: 7,
      },
    });
    expect(l1.ok()).toBeTruthy();
  });

  test.afterAll(async () => {
    await disableDemoMode();
  });

  test("summary, allocation display, reuse of one transaction across refunds, source view", async ({
    page,
  }) => {
    await navigateTo(page, "/transactions");
    await page.getByRole("button", { name: /Refunds/ }).click();

    // --- summary cards ---
    await expect(page.getByText("Expected Back")).toBeVisible();
    await expect(page.getByText("Received Back")).toBeVisible();
    await expect(page.getByText("Unallocated Refund Money")).toBeVisible();

    // --- refund #1: resolved, link row shows the ALLOCATED 7, not the full txn amount ---
    const search = page.getByPlaceholder("Search refunds, notes, accounts...");
    await search.fill(descOf(expense1));
    const card1 = page.getByTestId("refund-card").first();
    await expect(card1).toBeVisible();
    await expect(card1.getByText("Resolved").first()).toBeVisible();
    await expect(card1.getByText(/refunded/).first()).toBeVisible();
    await expect(card1.getByText(/\+/).first()).toBeVisible();
    // The "of <transaction amount>" hint proves we show allocation vs txn total
    await expect(card1.getByText(/^of /).first()).toBeVisible();

    // --- refund #2: link the SAME income transaction through the modal ---
    await search.fill(descOf(expense2));
    const card2 = page.getByTestId("refund-card").first();
    await expect(card2).toBeVisible();
    await card2.getByRole("button", { name: "Link Refund" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog
      .getByPlaceholder("Search refund transactions...")
      .fill(descOf(income));
    // Our shared transaction is the one flagged with an availability hint
    // (it's already partially allocated to refund #1).
    const txnBtn = dialog
      .locator("button")
      .filter({ hasText: descOf(income) })
      .filter({ hasText: /available/ })
      .first();
    await expect(txnBtn).toBeVisible();
    await txnBtn.click();

    // Amount defaults to the pending refund's remaining expectation (5).
    await expect(dialog.locator('input[type="number"]')).toHaveValue("5");

    const [linkResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/pending-refunds/${p2Id}/link`) &&
          r.request().method() === "POST",
      ),
      dialog.getByRole("button", { name: "Link Refund", exact: true }).click(),
    ]);
    expect(linkResp.ok()).toBeTruthy();

    // Refund #2 resolves, and the link row flags the shared source.
    await expect(card2.getByText("Resolved").first()).toBeVisible();
    await expect(card2.getByText("+1 more")).toBeVisible();

    // --- "By Refund Source" view: one card for the shared transaction ---
    await search.fill("");
    await page.getByRole("button", { name: "By Refund Source" }).click();
    const srcCard = page
      .getByTestId("refund-source-card")
      .filter({ hasText: descOf(income) })
      .first();
    await expect(srcCard).toBeVisible();
    // 12 of <total> allocated across two refunds, remainder still available.
    await expect(srcCard.getByText(/allocated/).first()).toBeVisible();
    await expect(srcCard.getByText(/available/).first()).toBeVisible();
    await expect(srcCard.getByRole("button", { name: "Unlink" })).toHaveCount(2);
  });
});
