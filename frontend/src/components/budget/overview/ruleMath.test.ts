import { describe, it, expect } from "vitest";
import type { BudgetLongRule } from "../../../services/api";
import { ruleColor, percentOf, rankRules } from "./ruleMath";

function rule(
  overrides: Partial<BudgetLongRule> = {},
): BudgetLongRule {
  return {
    name: "Home Renovation",
    kind: "project",
    category: "Home Renovation",
    month_contribution: 0,
    spent: 0,
    budget: 1000,
    ...overrides,
  };
}

describe("percentOf", () => {
  it("reports the share of the rule consumed", () => {
    expect(percentOf(rule({ spent: 250, budget: 1000 }))).toBe(25);
  });

  it("goes past 100 rather than capping, so an overspend is visible", () => {
    expect(percentOf(rule({ spent: 1050, budget: 1000 }))).toBe(105);
  });

  it("floors a net refund at zero instead of running the bar backwards", () => {
    expect(percentOf(rule({ spent: -400, budget: 1000 }))).toBe(0);
  });

  it("treats spend against a zero budget as entirely unbudgeted", () => {
    expect(percentOf(rule({ spent: 900, budget: 0 }))).toBe(100);
  });

  it("leaves an untouched zero-budget rule at zero", () => {
    expect(percentOf(rule({ spent: 0, budget: 0 }))).toBe(0);
  });

  it("ignores the month's contribution entirely", () => {
    // The contribution is scoped to the viewed month; the percentage describes
    // the rule as a whole. Mixing them is the bug this card exists to avoid.
    const a = percentOf(rule({ spent: 500, budget: 1000, month_contribution: 0 }));
    const b = percentOf(
      rule({ spent: 500, budget: 1000, month_contribution: 9999 }),
    );
    expect(a).toBe(b);
  });
});

describe("rankRules", () => {
  it("puts the fullest rule first", () => {
    const ranked = rankRules([
      rule({ name: "Wedding", spent: 780, budget: 1000 }),
      rule({ name: "Renovation", spent: 1050, budget: 1000 }),
      rule({ name: "Gifts", spent: 960, budget: 1000 }),
    ]);
    expect(ranked.map((item) => item.name)).toEqual([
      "Renovation",
      "Gifts",
      "Wedding",
    ]);
  });

  it("does not mutate the array it was given", () => {
    const input = [
      rule({ name: "Wedding", spent: 100 }),
      rule({ name: "Renovation", spent: 900 }),
    ];
    rankRules(input);
    expect(input.map((item) => item.name)).toEqual(["Wedding", "Renovation"]);
  });
});

describe("ruleColor", () => {
  it("turns rose only past the budget", () => {
    expect(ruleColor(101)).toBe("bg-rose-500");
    expect(ruleColor(100)).not.toBe("bg-rose-500");
  });

  it("warns in amber above ninety percent", () => {
    expect(ruleColor(95)).toBe("bg-amber-500");
  });

  it("stays green below the warning threshold", () => {
    expect(ruleColor(90)).toBe("bg-emerald-500");
  });
});
