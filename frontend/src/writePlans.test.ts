import { describe, it, expect } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import {
  UNCHANGED_BY_ROW_WRITE,
  cancelPendingRefund,
  closePendingRefund,
  markPendingRefund,
  patchRefundLink,
  splitInTransactionLists,
  patchTransactionLists,
  removeFromTransactionLists,
  rowsOfService,
} from "./writePlans";
import type { Transaction } from "./types/transaction";
import type { PendingRefund } from "./services/api";
import type { MonthlyAnalysis } from "./components/budget/budgetOptimistic";

const ALL = ["transactions", "list", "all", false, false];
const WITH_PARENTS = ["transactions", "list", "all", true, false];

const row = (source: string, uniqueId: number | string, extra: Partial<Transaction> = {}) =>
  ({ source, unique_id: uniqueId, amount: -10, date: "2026-10-01", ...extra }) as Transaction;

function seeded() {
  const client = new QueryClient();
  client.setQueryData(ALL, [
    row("bank_transactions", 5, { category: "Food", tag: "Groceries" }),
    row("credit_card_transactions", 5, { category: "Food", tag: "Groceries" }),
    row("bank_transactions", "split_1", { split_id: 1, category: "Food", tag: "Out" }),
  ]);
  client.setQueryData(WITH_PARENTS, [row("bank_transactions", 5, { category: "Food" })]);
  return client;
}

describe("transaction list patches", () => {
  it("retags the named row in every cached list, and only that row", () => {
    const client = seeded();

    patchTransactionLists(client, [
      { source: "bank_transactions", unique_id: "5", category: "Fun", tag: "" },
    ]);

    const all = client.getQueryData<Transaction[]>(ALL)!;
    expect(all[0]).toMatchObject({ category: "Fun", tag: undefined });
    // Same id in another table is a different transaction.
    expect(all[1]).toMatchObject({ category: "Food", tag: "Groceries" });
    // A split part keeps its own tag.
    expect(all[2]).toMatchObject({ category: "Food", tag: "Out" });
    expect(client.getQueryData<Transaction[]>(WITH_PARENTS)![0].category).toBe("Fun");
  });

  it("keeps a field the write leaves out", () => {
    const client = seeded();
    patchTransactionLists(client, [{ source: "bank_transactions", unique_id: 5, tag: "Cinema" }]);
    expect(client.getQueryData<Transaction[]>(ALL)![0]).toMatchObject({
      category: "Food",
      tag: "Cinema",
    });
  });

  it("puts every list back for a failed write", () => {
    const client = seeded();
    const before = client.getQueryData(ALL);
    const restore = patchTransactionLists(client, [
      { source: "bank_transactions", unique_id: 5, category: "" },
    ]);
    restore();
    expect(client.getQueryData(ALL)).toEqual(before);
  });

  it("takes deleted rows off every list and can put them back", () => {
    const client = seeded();
    const restore = removeFromTransactionLists(client, [
      { source: "credit_card_transactions", unique_id: "5" },
    ]);
    expect(client.getQueryData<Transaction[]>(ALL)!.map((r) => r.source)).toEqual([
      "bank_transactions",
      "bank_transactions",
    ]);
    restore();
    expect(client.getQueryData<Transaction[]>(ALL)).toHaveLength(3);
  });
});

describe("service filters over the merged list", () => {
  const rows = [
    row("bank_transactions", 1),
    row("credit_card_transactions", 1),
    row("cash_transactions", 1),
    row("manual_investment_transactions", 1),
    row("credit_card_transactions", "split_3", { split_id: 3, type: "split_child" }),
  ];

  it("keeps the rows of the chosen service's table, split parts included", () => {
    expect(rowsOfService(rows, "credit_cards").map((r) => r.unique_id)).toEqual([1, "split_3"]);
    expect(rowsOfService(rows, "banks")).toHaveLength(1);
    expect(rowsOfService(rows, "cash")).toHaveLength(1);
    expect(rowsOfService(rows, "manual_investments")).toHaveLength(1);
  });

  it("returns the whole list for all", () => {
    expect(rowsOfService(rows, "all")).toBe(rows);
  });
});

describe("row-write plans", () => {
  it("refresh the month overrides and the onboarding status a row's existence reaches", () => {
    expect(UNCHANGED_BY_ROW_WRITE).not.toContainEqual(["budget", "month-overrides"]);
    expect(UNCHANGED_BY_ROW_WRITE).not.toContainEqual(["onboardingStatus"]);
    expect(UNCHANGED_BY_ROW_WRITE).toContainEqual(["categories"]);
  });
});

describe("split list patches", () => {
  it("puts the parts in the parent's place, or after it where parents are kept", () => {
    const client = seeded();

    splitInTransactionLists(client, { source: "bank_transactions", unique_id: 5 }, [
      { amount: -6, category: "Food", tag: "Groceries" },
      { amount: -4, category: "Home", tag: "" },
    ]);

    const all = client.getQueryData<Transaction[]>(ALL)!;
    expect(all.map((r) => [r.source, r.split_id ?? null, r.amount])).toEqual([
      ["bank_transactions", -1, -6],
      ["bank_transactions", -2, -4],
      ["credit_card_transactions", null, -10],
      ["bank_transactions", 1, -10],
    ]);
    expect(all[1]).toMatchObject({ type: "split_child", parent_unique_id: 5, tag: undefined });
    const kept = client.getQueryData<Transaction[]>(WITH_PARENTS)!;
    expect(kept.map((r) => r.type)).toEqual(["split_parent", "split_child", "split_child"]);
  });
});

describe("refund patches", () => {
  const LIST = ["pending-refunds", false];
  const MONTH = ["budget", "analysis", 2026, 10, false, false];
  const purchase = row("credit_card_transactions", 7, {
    amount: -200,
    category: "Shopping",
    tag: "Online",
  });
  const open: PendingRefund = {
    id: 3,
    source_type: "transaction",
    source_id: 7,
    source_table: "credit_card_transactions",
    expected_amount: 200,
    status: "partial",
    total_refunded: 50,
    remaining: 150,
    links: [
      { id: 9, pending_refund_id: 3, refund_transaction_id: 41, refund_source: "bank_transactions", amount: 50 },
    ],
  };
  const analysis = (net: number | null, items: PendingRefund[], expected: number): MonthlyAnalysis => ({
    rules: [
      {
        rule: { id: 1, name: "Total Budget", amount: 1000, category: "Total Budget", tags: ["all_tags"] },
        current_amount: -(net ?? -200),
        data: [],
        allow_edit: true,
        allow_delete: false,
      },
      {
        rule: { id: 2, name: "Shopping", amount: 500, category: "Shopping", tags: ["all_tags"] },
        current_amount: -(net ?? -200),
        data: [{ ...purchase, net_amount: net, split_id: null }],
        allow_edit: true,
        allow_delete: true,
      },
    ],
    project_spending: { projects: [] },
    pending_refunds: { items, total_expected: expected },
  });
  const shopping = (client: QueryClient) =>
    client.getQueryData<MonthlyAnalysis>(MONTH)!.rules!.find((i) => i.rule.name === "Shopping")!;

  it("marks a purchase at once: its badge, the awaiting section, and its cost", () => {
    const client = new QueryClient();
    client.setQueryData(LIST, []);
    client.setQueryData(MONTH, analysis(null, [], 0));

    const restore = markPendingRefund(client, LIST, purchase, 200);

    const list = client.getQueryData<PendingRefund[]>(LIST)!;
    expect(list).toEqual([
      expect.objectContaining({ source_id: 7, source_table: "credit_card_transactions", status: "pending" }),
    ]);
    expect(list[0].id).toBeLessThan(0);
    expect(shopping(client).current_amount).toBe(0);
    expect(shopping(client).data[0].net_amount).toBe(0);
    const section = client.getQueryData<MonthlyAnalysis>(MONTH)!.pending_refunds!;
    expect(section.total_expected).toBe(200);
    expect(section.items).toHaveLength(1);

    restore();
    expect(client.getQueryData(LIST)).toEqual([]);
    expect(shopping(client).current_amount).toBe(200);
  });

  it("cancels a refund at once: the badge goes and the purchase counts in full", () => {
    const client = new QueryClient();
    client.setQueryData(LIST, [open]);
    client.setQueryData(MONTH, analysis(0, [], 150));

    cancelPendingRefund(client, LIST, 3);

    expect(client.getQueryData(LIST)).toEqual([]);
    expect(shopping(client).current_amount).toBe(200);
    expect(shopping(client).data[0].net_amount).toBeNull();
    expect(client.getQueryData<MonthlyAnalysis>(MONTH)!.pending_refunds!.total_expected).toBe(0);
  });

  it("closes a refund at once: only what came back is taken off the purchase", () => {
    const client = new QueryClient();
    client.setQueryData(LIST, [open]);
    client.setQueryData(MONTH, analysis(0, [], 150));

    closePendingRefund(client, LIST, open);

    expect(client.getQueryData<PendingRefund[]>(LIST)![0].status).toBe("closed");
    expect(shopping(client).current_amount).toBe(150);
    expect(client.getQueryData<MonthlyAnalysis>(MONTH)!.pending_refunds!.total_expected).toBe(0);
  });

  it("unlinks and links at once, recomputing totals and status as the backend does", () => {
    const client = new QueryClient();
    client.setQueryData(LIST, [open]);
    client.setQueryData(MONTH, analysis(0, [], 150));

    const restore = patchRefundLink(client, LIST, { unlink: 9 });
    expect(client.getQueryData<PendingRefund[]>(LIST)![0]).toMatchObject({
      status: "pending",
      total_refunded: 0,
      remaining: 200,
      links: [],
    });
    const section = client.getQueryData<MonthlyAnalysis>(MONTH)!.pending_refunds!;
    expect(section.items!.map((r) => r.id)).toEqual([3]);
    expect(section.total_expected).toBe(200);
    restore();

    patchRefundLink(client, LIST, {
      pendingId: 3,
      link: { refund_transaction_id: 42, refund_source: "bank_transactions", amount: 150 },
    });
    expect(client.getQueryData<PendingRefund[]>(LIST)![0]).toMatchObject({
      status: "resolved",
      total_refunded: 200,
      remaining: 0,
    });
    expect(client.getQueryData<MonthlyAnalysis>(MONTH)!.pending_refunds!.total_expected).toBe(0);
  });
});
