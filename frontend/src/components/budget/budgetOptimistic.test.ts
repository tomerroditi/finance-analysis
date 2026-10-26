import { describe, it, expect } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import {
  applyRetag,
  patchBudgetForRetag,
  widenForCascade,
  UNCHANGED_BY_RETAG,
  type ClaimContext,
  type MonthlyAnalysis,
} from "./budgetOptimistic";

/**
 * A retag moves a row in the Monthly tab on click, by running the backend's
 * claim order (`backend/services/budget/ledger.py`) for that one row against
 * the cached month. The refetch that follows replaces it — these pin that the
 * stand-in agrees with what the server will answer.
 */

const NONE: ClaimContext = { projectCategories: new Set(), yearlyRules: new Map() };

const row = (uniqueId: number, amount: number, category: string | null, tag: string | null) => ({
  id: uniqueId,
  unique_id: String(uniqueId),
  source: "credit_card_transactions",
  date: "2026-10-10",
  description: `tx ${uniqueId}`,
  amount,
  category: category ?? undefined,
  tag: tag ?? undefined,
  split_id: null,
  net_amount: null,
  budget_year: 2026,
  budget_month: 10,
});

const item = (
  id: number | string,
  name: string,
  amount: number,
  category: string,
  tags: string[] | string,
  data: ReturnType<typeof row>[],
) => ({
  rule: { id, name, amount, category, tags },
  current_amount: data.reduce((sum, r) => sum - (r.net_amount ?? r.amount), 0),
  data,
  allow_edit: true,
  allow_delete: true,
});

/** A month: Total, Food (all tags), Groceries (Food/Groceries), Fun (all tags), Other. */
function month(): MonthlyAnalysis {
  const grocery = row(1, -100, "Food", "Groceries");
  const dinner = row(2, -60, "Food", "Restaurants");
  const untagged = row(3, -40, null, null);
  return {
    rules: [
      // The Total lists no rows of its own; the month's list is the others' union.
      { ...item(1, "Total Budget", 1000, "Total Budget", ["all_tags"], []), current_amount: 200 },
      item(2, "Food Budget", 300, "Food", ["all_tags"], [dinner]),
      item(3, "Groceries", 200, "Food", ["Groceries"], [grocery]),
      item(4, "Fun", 100, "Entertainment", ["all_tags"], []),
      item("202610_Other_Expenses", "Other Expenses", 400, "Other Expenses", "Other Expenses", [untagged]),
    ],
    project_spending: { projects: [] },
  };
}

const byName = (analysis: MonthlyAnalysis, name: string) =>
  analysis.rules!.find((i) => i.rule.name === name);
const ids = (analysis: MonthlyAnalysis, name: string) =>
  byName(analysis, name)?.data.map((r) => Number(r.unique_id));

/** Every row the month lists — the union the Total's transaction list shows. */
const listed = (analysis: MonthlyAnalysis) =>
  analysis
    .rules!.filter((i) => i.rule.name !== "Total Budget")
    .flatMap((i) => i.data.map((r) => Number(r.unique_id)))
    .sort();

const edit = (uniqueId: number, category?: string, tag?: string) => ({
  source: "credit_card_transactions",
  unique_id: String(uniqueId),
  category,
  tag,
});

describe("applyRetag", () => {
  it("moves a row and its cost out of Other Expenses into the rule that now claims it", () => {
    const next = applyRetag(month(), [edit(3, "Entertainment", "Cinema")], NONE);

    expect(ids(next, "Fun")).toEqual([3]);
    expect(byName(next, "Fun")!.current_amount).toBe(40);
    // Emptied, so it goes — the backend only lists Other Expenses while it holds something.
    expect(byName(next, "Other Expenses")).toBeUndefined();
    // Still in the monthly pool: the Total keeps its figure and shows the new tag.
    expect(byName(next, "Total Budget")!.current_amount).toBe(200);
    expect(byName(next, "Total Budget")!.data).toEqual([]);
    expect(listed(next)).toEqual([1, 2, 3]);
  });

  it("gives the row to the most specific rule, not the all-tags one", () => {
    const next = applyRetag(month(), [edit(2, "Food", "Groceries")], NONE);

    expect(ids(next, "Groceries")).toEqual([1, 2]);
    expect(byName(next, "Groceries")!.current_amount).toBe(160);
    expect(ids(next, "Food Budget")).toEqual([]);
    expect(byName(next, "Food Budget")!.current_amount).toBe(0);
  });

  it("keeps the current value of a field the write leaves out", () => {
    const next = applyRetag(month(), [edit(2, undefined, "Groceries")], NONE);

    expect(ids(next, "Groceries")).toEqual([1, 2]);
  });

  it("creates Other Expenses when a cleared row has nowhere else to go", () => {
    const start = month();
    start.rules = start.rules!.filter((i) => i.rule.name !== "Other Expenses");

    const next = applyRetag(start, [edit(1, "", "")], NONE);

    const other = byName(next, "Other Expenses")!;
    expect(other.data.map((r) => Number(r.unique_id))).toEqual([1]);
    expect(other.current_amount).toBe(100);
    // What the backend gives it: the Total's headroom over every other rule.
    expect(other.rule.amount).toBe(1000 - (300 + 200 + 100));
  });

  it("takes a row into a project out of the monthly pool and into the month's projects", () => {
    const ctx: ClaimContext = { ...NONE, projectCategories: new Set(["Renovation"]) };
    const next = applyRetag(month(), [edit(1, "Renovation", "Paint")], ctx);

    expect(ids(next, "Groceries")).toEqual([]);
    expect(byName(next, "Total Budget")!.current_amount).toBe(100);
    expect(listed(next)).toEqual([2, 3]);
    expect(next.project_spending!.projects).toEqual([
      expect.objectContaining({ category: "Renovation", spent: 100 }),
    ]);
    expect(next.project_spending!.total_spent).toBe(100);
  });

  it("brings a row back from a project into the monthly pool", () => {
    const start = month();
    start.project_spending = {
      projects: [{ category: "Renovation", spent: 50, transactions: [row(9, -50, "Renovation", "Paint")] }],
      total_spent: 50,
    };
    const ctx: ClaimContext = { ...NONE, projectCategories: new Set(["Renovation"]) };

    const next = applyRetag(start, [edit(9, "Food", "Restaurants")], ctx);

    expect(next.project_spending!.projects).toEqual([]);
    expect(ids(next, "Food Budget")).toEqual([2, 9]);
    expect(byName(next, "Total Budget")!.current_amount).toBe(250);
  });

  it("drops a row a yearly envelope claims from the monthly pool", () => {
    const ctx: ClaimContext = {
      ...NONE,
      yearlyRules: new Map([[2026, [{ category: "Insurance", tags: ["Car"] }]]]),
    };
    const next = applyRetag(month(), [edit(3, "Insurance", "Car")], ctx);

    expect(byName(next, "Other Expenses")).toBeUndefined();
    expect(listed(next)).toEqual([1, 2]);
    expect(byName(next, "Total Budget")!.current_amount).toBe(160);
  });

  it("drops a row moved to a category the budget never counts", () => {
    const next = applyRetag(month(), [edit(2, "Ignore", "Transfer")], NONE);

    expect(ids(next, "Food Budget")).toEqual([]);
    expect(listed(next)).toEqual([1, 3]);
    expect(byName(next, "Total Budget")!.current_amount).toBe(140);
  });

  it("moves what a row counts for, net of its refund, not its gross amount", () => {
    const start = month();
    const refunded = { ...row(5, -300, null, null), net_amount: -120 };
    start.rules![4].data.push(refunded);

    const next = applyRetag(start, [edit(5, "Entertainment", "Cinema")], NONE);

    expect(byName(next, "Fun")!.current_amount).toBe(120);
  });

  it("leaves split parts and unrelated months untouched", () => {
    const start = month();
    start.rules![4].data[0] = { ...start.rules![4].data[0], split_id: 7 };

    expect(applyRetag(start, [edit(3, "Entertainment", "Cinema")], NONE)).toBe(start);
    expect(applyRetag(start, [edit(999, "Entertainment", "Cinema")], NONE)).toBe(start);
  });
});

describe("patchBudgetForRetag", () => {
  it("patches every cached month and restores them all on a failed write", () => {
    const client = new QueryClient();
    const key = ["budget", "analysis", 2026, 10, false, false];
    const original = month();
    client.setQueryData(key, original);

    const { restore } = patchBudgetForRetag(client, [edit(3, "Entertainment", "Cinema")]);
    expect(ids(client.getQueryData<MonthlyAnalysis>(key)!, "Fun")).toEqual([3]);

    restore();
    expect(client.getQueryData(key)).toEqual(original);
  });

  it("knows a project from the cached project list", () => {
    const client = new QueryClient();
    const key = ["budget", "analysis", 2026, 10, false, false];
    client.setQueryData(key, month());
    client.setQueryData(["budget", "projects-status", false], [{ name: "Renovation", closed: false }]);

    patchBudgetForRetag(client, [edit(1, "Renovation", "Paint")]);

    const next = client.getQueryData<MonthlyAnalysis>(key)!;
    expect(next.project_spending!.projects!.map((p) => p.category)).toEqual(["Renovation"]);
  });

  it("plans to refetch the touched month first and to leave the other months alone", () => {
    const client = new QueryClient();
    const october = ["budget", "analysis", 2026, 10, false, false];
    const september = ["budget", "analysis", 2026, 9, false, false];
    client.setQueryData(october, month());
    client.setQueryData(september, { rules: [], project_spending: { projects: [] } });

    const { refresh } = patchBudgetForRetag(client, [edit(3, "Entertainment", "Cinema")]);

    expect(refresh.first).toEqual([["budget", "analysis", 2026, 10]]);
    expect(refresh.skip).toEqual([
      ...UNCHANGED_BY_RETAG,
      ["budget", "analysis", 2026, 9],
      ["cash-balances"],
    ]);
  });

  it("refreshes the cash balances only when a cash row is retagged", () => {
    const client = new QueryClient();
    client.setQueryData(["budget", "analysis", 2026, 10, false, false], month());

    const cash = patchBudgetForRetag(client, [
      { source: "cash_transactions", unique_id: "9", category: "Food" },
    ]);

    expect(cash.refresh.skip).not.toContainEqual(["cash-balances"]);
  });

  it("refetches every month when a row was in none of the cached ones", () => {
    const client = new QueryClient();
    client.setQueryData(["budget", "analysis", 2026, 10, false, false], month());

    // Tagged from the Transactions page: the row could be in any month.
    const { refresh } = patchBudgetForRetag(client, [edit(42, "Entertainment", "Cinema")]);

    expect(refresh.first).toEqual([["budget", "analysis"]]);
    expect(refresh.skip).toEqual([...UNCHANGED_BY_RETAG, ["cash-balances"]]);
  });

  it("widens to every month once the reply says linked refunds moved too", () => {
    const client = new QueryClient();
    client.setQueryData(["budget", "analysis", 2026, 10, false, false], month());
    client.setQueryData(["budget", "analysis", 2026, 9, false, false], { rules: [] });
    const { refresh } = patchBudgetForRetag(client, [edit(3, "Entertainment", "Cinema")]);

    widenForCascade(refresh, 0);
    expect(refresh.skip).toContainEqual(["budget", "analysis", 2026, 9]);

    widenForCascade(refresh, 2);
    expect(refresh.skip).toEqual(UNCHANGED_BY_RETAG);
  });
});
