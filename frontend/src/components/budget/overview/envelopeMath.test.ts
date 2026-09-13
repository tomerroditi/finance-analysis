import { describe, it, expect } from "vitest";
import type { BudgetLongEnvelope } from "../../../services/api";
import { envelopeColor, percentOf, rankEnvelopes } from "./envelopeMath";

function envelope(
  overrides: Partial<BudgetLongEnvelope> = {},
): BudgetLongEnvelope {
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
  it("reports the share of the envelope consumed", () => {
    expect(percentOf(envelope({ spent: 250, budget: 1000 }))).toBe(25);
  });

  it("goes past 100 rather than capping, so an overspend is visible", () => {
    expect(percentOf(envelope({ spent: 1050, budget: 1000 }))).toBe(105);
  });

  it("floors a net refund at zero instead of running the bar backwards", () => {
    expect(percentOf(envelope({ spent: -400, budget: 1000 }))).toBe(0);
  });

  it("treats spend against a zero budget as entirely unbudgeted", () => {
    expect(percentOf(envelope({ spent: 900, budget: 0 }))).toBe(100);
  });

  it("leaves an untouched zero-budget envelope at zero", () => {
    expect(percentOf(envelope({ spent: 0, budget: 0 }))).toBe(0);
  });

  it("ignores the month's contribution entirely", () => {
    // The contribution is scoped to the viewed month; the percentage describes
    // the envelope as a whole. Mixing them is the bug this card exists to avoid.
    const a = percentOf(envelope({ spent: 500, budget: 1000, month_contribution: 0 }));
    const b = percentOf(
      envelope({ spent: 500, budget: 1000, month_contribution: 9999 }),
    );
    expect(a).toBe(b);
  });
});

describe("rankEnvelopes", () => {
  it("puts the fullest envelope first", () => {
    const ranked = rankEnvelopes([
      envelope({ name: "Wedding", spent: 780, budget: 1000 }),
      envelope({ name: "Renovation", spent: 1050, budget: 1000 }),
      envelope({ name: "Gifts", spent: 960, budget: 1000 }),
    ]);
    expect(ranked.map((item) => item.name)).toEqual([
      "Renovation",
      "Gifts",
      "Wedding",
    ]);
  });

  it("does not mutate the array it was given", () => {
    const input = [
      envelope({ name: "Wedding", spent: 100 }),
      envelope({ name: "Renovation", spent: 900 }),
    ];
    rankEnvelopes(input);
    expect(input.map((item) => item.name)).toEqual(["Wedding", "Renovation"]);
  });
});

describe("envelopeColor", () => {
  it("turns rose only past the budget", () => {
    expect(envelopeColor(101)).toBe("bg-rose-500");
    expect(envelopeColor(100)).not.toBe("bg-rose-500");
  });

  it("warns in amber above ninety percent", () => {
    expect(envelopeColor(95)).toBe("bg-amber-500");
  });

  it("stays green below the warning threshold", () => {
    expect(envelopeColor(90)).toBe("bg-emerald-500");
  });
});
