import { describe, it, expect } from "vitest";
import { normalizeAnalysis, type AnalysisEntry } from "./normalizeAnalysis";

function entry(
  id: number,
  name: string,
  amount: number,
  spent: number,
): AnalysisEntry {
  return {
    rule: { id, name, category: `cat-${id}`, amount },
    current_amount: spent,
  };
}

describe("normalizeAnalysis", () => {
  it("takes the totals from the Total Budget row and keeps it out of the tiles", () => {
    const result = normalizeAnalysis([
      entry(1, "Total Budget", 12000, 66),
      entry(2, "Groceries", 2000, 500),
    ]);
    expect(result.totalBudget).toBe(12000);
    expect(result.totalSpent).toBe(66);
    expect(result.rules.map((r) => r.name)).toEqual(["Groceries"]);
  });

  it("orders the remaining rules by spend, descending", () => {
    const result = normalizeAnalysis([
      entry(1, "Total Budget", 100, 0),
      entry(2, "Small", 50, 10),
      entry(3, "Big", 50, 40),
      entry(4, "Middle", 50, 25),
    ]);
    expect(result.rules.map((r) => r.name)).toEqual(["Big", "Middle", "Small"]);
  });

  it("maps a rule onto the grid's shape", () => {
    const { rules } = normalizeAnalysis([entry(7, "Groceries", 2000, 500)]);
    expect(rules[0]).toEqual({
      id: 7,
      name: "Groceries",
      category: "cat-7",
      budget_amount: 2000,
      spent_amount: 500,
    });
  });

  it("sums the rules when there is no Total Budget row", () => {
    const result = normalizeAnalysis([
      entry(1, "Groceries", 2000, 500),
      entry(2, "Bills", 3000, 1200),
    ]);
    expect(result.totalBudget).toBe(5000);
    expect(result.totalSpent).toBe(1700);
  });

  it("prefers an explicit spent fallback over the sum", () => {
    const result = normalizeAnalysis(
      [entry(1, "Groceries", 2000, 500)],
      9999,
    );
    expect(result.totalSpent).toBe(9999);
  });

  it("still prefers the Total Budget row over an explicit fallback", () => {
    const result = normalizeAnalysis(
      [entry(1, "Total Budget", 2000, 42), entry(2, "Groceries", 2000, 500)],
      9999,
    );
    expect(result.totalSpent).toBe(42);
  });

  it("returns zeroed totals and no rules for an empty payload", () => {
    expect(normalizeAnalysis([])).toEqual({
      rules: [],
      totalBudget: 0,
      totalSpent: 0,
    });
  });
});
