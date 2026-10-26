import { describe, it, expect } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import {
  UNCHANGED_BY_ROW_WRITE,
  patchTransactionLists,
  removeFromTransactionLists,
  rowsOfService,
} from "./writePlans";
import type { Transaction } from "./types/transaction";

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
