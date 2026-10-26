import { describe, it, expect, vi, afterEach } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { isTotalBudget, monthTransactions, uncategorizedSummary } from "./monthTransactions";
import { neighbourMonths, prefetchNeighbourMonths } from "./prefetchNeighbourMonths";
import { monthlyAlerts } from "./overview/ruleMath";

const row = (id: number, category: string | null, amount = -10) => ({
  unique_id: id,
  category,
  amount,
});
const entry = (name: string, category: string, data: ReturnType<typeof row>[], amount = 100, spent = 0) => ({
  rule: { id: name, name, category, amount },
  current_amount: spent,
  data,
});

describe("monthTransactions", () => {
  it("lists the other rules' rows when the Total sends none", () => {
    const rules = [
      entry("Total Budget", "Total Budget", []),
      entry("Food", "Food", [row(1, "Food")]),
      entry("Other Expenses", "Other Expenses", [row(2, null)]),
    ];
    expect(monthTransactions(rules).map((r) => r.unique_id)).toEqual([1, 2]);
  });

  it("uses the Total's own rows in a total-only month or an old response", () => {
    const rules = [
      entry("Total Budget", "Total Budget", [row(1, "Food"), row(2, null)]),
      entry("Food", "Food", [row(1, "Food")]),
    ];
    expect(monthTransactions(rules).map((r) => r.unique_id)).toEqual([1, 2]);
  });

  it("recognises the Total by its category even when renamed", () => {
    expect(isTotalBudget({ name: "Household cap", category: "Total Budget" })).toBe(true);
    expect(isTotalBudget({ name: "Food", category: "Food" })).toBe(false);
  });
});

describe("uncategorizedSummary", () => {
  it("reads the served fields", () => {
    expect(uncategorizedSummary({ uncategorized_count: 3, uncategorized_amount: 42 })).toEqual({
      count: 3,
      amount: 42,
    });
  });

  it("falls back to the Total's rows for a response cached before the fields", () => {
    const rules = [entry("Total Budget", "Total Budget", [row(1, null, -30), row(2, "Food"), row(3, null, 5)])];
    expect(uncategorizedSummary({ rules })).toEqual({ count: 2, amount: 35 });
  });
});

describe("neighbourMonths", () => {
  it("orders the neighbours nearest first", () => {
    expect(neighbourMonths(2026, 1, new Date(2027, 0, 1))).toEqual([
      { year: 2025, month: 12 },
      { year: 2026, month: 2 },
      { year: 2025, month: 11 },
      { year: 2026, month: 3 },
    ]);
  });

  it("never reaches past the current month — reading one would auto-fill it", () => {
    expect(neighbourMonths(2026, 10, new Date(2026, 9, 26))).toEqual([
      { year: 2026, month: 9 },
      { year: 2026, month: 8 },
    ]);
  });
});

describe("prefetchNeighbourMonths", () => {
  afterEach(() => vi.useRealTimers());

  it("fetches one month at a time and stops when cancelled", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2027, 0, 15));
    const client = new QueryClient();
    const resolvers: (() => void)[] = [];
    const fetched: string[] = [];
    const stop = prefetchNeighbourMonths(client, 2026, 6, (y, m) => ({
      queryKey: ["m", y, m],
      queryFn: () =>
        new Promise((resolve) => {
          fetched.push(`${y}-${m}`);
          resolvers.push(() => resolve(null));
        }),
    }));

    await vi.waitFor(() => expect(fetched).toEqual(["2026-5"]));
    resolvers[0]();
    await vi.waitFor(() => expect(fetched).toEqual(["2026-5", "2026-7"]));
    stop();
    resolvers[1]();
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(fetched).toEqual(["2026-5", "2026-7"]);
  });
});

describe("monthlyAlerts", () => {
  it("lists monthly rules at or past the threshold, fullest first, as /budget/alerts does", () => {
    const alerts = monthlyAlerts(
      [
        entry("Total Budget", "Total Budget", [], 1000, 990),
        entry("Other Expenses", "Other Expenses", [], 10, 50),
        entry("Food", "Food", [], 100, 95),
        entry("Fun", "Fun", [], 100, 150),
        entry("Car", "Car", [], 100, 50),
        entry("Free", "Gifts", [], 0, 20),
      ],
      0.9,
    );
    expect(alerts.map((a) => [a.name, a.percentage])).toEqual([
      ["Fun", 1.5],
      ["Food", 0.95],
    ]);
  });
});
