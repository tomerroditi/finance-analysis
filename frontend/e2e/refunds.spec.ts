import { test, expect } from "@playwright/test";
import {
  API_BASE,
  enableDemoMode,
  disableDemoMode,
  navigateTo,
} from "./helpers";

/**
 * Redesigned Refunds experience — dense two-pane layout.
 *
 * Covers, in one journey:
 * - toolbar KPIs (owed back / received / unallocated)
 * - request rows with expandable link lines showing the ALLOCATED amount
 *   plus the "of <transaction amount>" hint (enrichment regression guard)
 * - inline note editing on a request (PATCH) and on a refund source (PUT)
 * - the link dialog's SUGGESTED section (exact amount match pinned on top)
 *   and linking through it — reusing the multi-link model
 * - the sources rail: allocation chips, free-amount chip
 *
 * Mutating spec: seeds its own pending refunds via the API in beforeAll and
 * relies on the demo-DB re-copy on the next demo-mode enable for cleanup.
 */

interface ApiTxn {
  unique_id: number;
  source: string;
  amount: number;
  date?: string;
  description?: string;
  desc?: string;
}

const descOf = (t: ApiTxn) => t.description ?? t.desc ?? "";

test.describe("Refunds redesign", () => {
  let expense1: ApiTxn;
  let expense2: ApiTxn;
  let income1: ApiTxn; // shared source funding p1, with leftover
  let income2: ApiTxn; // untouched txn whose amount exactly matches p2
  let p1Id: number;
  let p2Id: number;

  test.beforeAll(async ({ request }) => {
    await enableDemoMode();

    const txns: ApiTxn[] = await (
      await request.get(`${API_BASE}/transactions/`)
    ).json();
    const pendings: { source_table: string; source_id: number }[] = await (
      await request.get(`${API_BASE}/pending-refunds/`)
    ).json();
    const sources: {
      refund_source: string;
      refund_transaction_id: number;
      total_allocated: number;
    }[] = await (
      await request.get(`${API_BASE}/pending-refunds/refund-sources`)
    ).json();

    const marked = new Set(
      pendings.map((p) => `${p.source_table}_${p.source_id}`),
    );
    const allocated = new Map(
      sources.map((s) => [
        `${s.refund_source}_${s.refund_transaction_id}`,
        s.total_allocated,
      ]),
    );
    const availOf = (t: ApiTxn) =>
      t.amount - (allocated.get(`${t.source}_${t.unique_id}`) ?? 0);

    const incomes = txns.filter(
      (t) => t.amount >= 20 && descOf(t).length > 2 && t.date,
    );
    // income1: has ≥20 available (funds p1's 7 with leftover to spare)
    income1 = incomes
      .filter((t) => availOf(t) >= 20)
      .sort((a, b) => a.amount - b.amount)[0];
    // income2: completely unallocated, distinct from income1 — its exact
    // amount becomes p2's expectation so it must surface as SUGGESTED.
    income2 = incomes
      .filter(
        (t) =>
          availOf(t) === t.amount &&
          t.unique_id !== income1.unique_id &&
          Math.abs(t.amount - 7) > 1,
      )
      .sort((a, b) => a.amount - b.amount)[0];
    expect(income1, "demo data must contain an available income txn").toBeTruthy();
    expect(income2, "demo data must contain an unallocated income txn").toBeTruthy();

    const expenses = txns.filter(
      (t) =>
        t.amount < -20 &&
        descOf(t).length > 2 &&
        !marked.has(`${t.source}_${t.unique_id}`) &&
        // The suggestion date rule only proposes refunds dated on/after the
        // expense — keep both seeds compatible with our chosen incomes.
        (!t.date || !income2.date || t.date <= income2.date),
    );
    expense1 = expenses[0];
    expense2 = expenses.find((t) => descOf(t) !== descOf(expense1))!;
    expect(expense1, "demo data must contain expense transactions").toBeTruthy();
    expect(expense2, "demo data must contain a second expense").toBeTruthy();

    const r1 = await request.post(`${API_BASE}/pending-refunds/`, {
      data: {
        source_type: "transaction",
        source_id: expense1.unique_id,
        source_table: expense1.source,
        expected_amount: 7,
      },
    });
    expect(r1.ok()).toBeTruthy();
    p1Id = (await r1.json()).id;

    const r2 = await request.post(`${API_BASE}/pending-refunds/`, {
      data: {
        source_type: "transaction",
        source_id: expense2.unique_id,
        source_table: expense2.source,
        expected_amount: income2.amount,
      },
    });
    expect(r2.ok()).toBeTruthy();
    p2Id = (await r2.json()).id;

    const l1 = await request.post(`${API_BASE}/pending-refunds/${p1Id}/link`, {
      data: {
        refund_transaction_id: income1.unique_id,
        refund_source: income1.source,
        amount: 7,
      },
    });
    expect(l1.ok()).toBeTruthy();
  });

  test.afterAll(async () => {
    await disableDemoMode();
  });

  test("KPIs, dense rows, inline notes, suggested source linking, sources rail", async ({
    page,
  }) => {
    await navigateTo(page, "/transactions");
    await page.getByRole("button", { name: /Refunds/ }).click();

    // --- toolbar KPIs ---
    await expect(page.getByText("Expected Back", { exact: false })).toBeVisible();
    await expect(page.getByText("Received Back")).toBeVisible();
    await expect(page.getByText("Unallocated Refund Money")).toBeVisible();

    // --- request row for p1: expand, allocated amount + "of <txn>" hint ---
    const search = page.getByPlaceholder(/Search refunds/);
    await search.fill(descOf(expense1));
    const row1 = page.getByTestId("refund-row").first();
    await expect(row1).toBeVisible();
    await row1.getByRole("button").first().click(); // expand
    await expect(row1.getByText(/^of\s/).first()).toBeVisible();

    // --- inline note on the request (PATCH) ---
    await row1.hover();
    await row1.getByTestId("inline-note").first().click();
    const noteInput = row1.getByPlaceholder(/Add a short note/);
    await noteInput.fill("e2e recall note");
    const [patchResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/pending-refunds/${p1Id}`) &&
          r.request().method() === "PATCH",
      ),
      noteInput.press("Enter"),
    ]);
    expect(patchResp.ok()).toBeTruthy();
    await expect(row1.getByText('"e2e recall note"')).toBeVisible();

    // --- link p2 through the SUGGESTED candidate ---
    await search.fill(descOf(expense2));
    const row2 = page.getByTestId("refund-row").first();
    await expect(row2).toBeVisible();
    // Remaining is shown out of the expected total ("100 / 221 left")
    await expect(row2.getByTestId("remaining-cell")).toContainText("/");
    await row2.getByRole("button", { name: "Link", exact: true }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/^★?\s*Suggested/).first()).toBeVisible();
    const suggested = dialog
      .getByTestId("suggested-candidate")
      .filter({ hasText: descOf(income2) })
      .first();
    await expect(suggested).toBeVisible();
    await expect(suggested.getByText("Suggested · amount match")).toBeVisible();
    await suggested.click();

    const expectedDefault = String(Math.round(income2.amount * 100) / 100);
    await expect(dialog.locator('input[type="number"]')).toHaveValue(expectedDefault);

    const [linkResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/pending-refunds/${p2Id}/link`) &&
          r.request().method() === "POST",
      ),
      dialog.getByRole("button", { name: "Link Refund", exact: true }).click(),
    ]);
    expect(linkResp.ok()).toBeTruthy();
    await expect(row2.getByText("settled")).toBeVisible();

    // --- sources rail: income1 shows free chip; add a source note (PUT) ---
    await search.fill("");
    const srcItem = page
      .getByTestId("refund-source-item")
      .filter({ hasText: descOf(income1) })
      .first();
    await expect(srcItem).toBeVisible();
    await expect(srcItem.getByText(/free → link it/).first()).toBeVisible();

    await srcItem.hover();
    await srcItem.getByTestId("inline-note").first().click();
    const srcNoteInput = srcItem.getByPlaceholder(/Add a short note/);
    await srcNoteInput.fill("shared source note");
    const [putResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes("/pending-refunds/refund-sources/note") &&
          r.request().method() === "PUT",
      ),
      srcNoteInput.press("Enter"),
    ]);
    expect(putResp.ok()).toBeTruthy();
    await expect(srcItem.getByText('"shared source note"')).toBeVisible();
  });
});
