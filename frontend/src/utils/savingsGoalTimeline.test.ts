import { describe, it, expect } from "vitest";
import { unclaimedSurplus } from "./savingsGoalTimeline";
import type { SavingsGoalTimelineMonth } from "../services/api";

/** A timeline row, with the figures under test filled in per case. */
function month(
  fields: Partial<SavingsGoalTimelineMonth>,
): SavingsGoalTimelineMonth {
  return {
    month: "2026-08",
    goals: [],
    allocated: 0,
    clawed_back: 0,
    surplus: 0,
    free_cash: 0,
    is_provisional: false,
    ...fields,
  };
}

describe("unclaimedSurplus", () => {
  it("is what the waterfall left of the month's surplus", () => {
    expect(unclaimedSurplus(month({ surplus: 1500, allocated: 900 }))).toBe(600);
  });

  it("counts a clawback back into what the pool kept", () => {
    // A month 5,000 in the red with an empty pool: 3,000 came back out of the
    // goals, so the pool itself gave up the other 2,000. The goal segments and
    // this one sum to the surplus, which is what makes them one stack.
    expect(
      unclaimedSurplus(month({ surplus: -5000, clawed_back: 3000 })),
    ).toBe(-2000);
  });

  it("reads a month that claimed the whole surplus as nothing left", () => {
    expect(unclaimedSurplus(month({ surplus: 2400, allocated: 2400 }))).toBe(0);
  });

  it("gives back a deficit the pool covered on its own", () => {
    // No goal moved, so the whole shortfall came out of the pool.
    expect(unclaimedSurplus(month({ surplus: -2432.14 }))).toBe(-2432.14);
  });

  it("keeps the figure at two decimals", () => {
    // Shekel figures that subtract to a float the axis would otherwise print.
    expect(
      unclaimedSurplus(month({ surplus: 1000.3, allocated: 1000.2 })),
    ).toBe(0.1);
  });
});
