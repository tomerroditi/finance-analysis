import { describe, expect, it } from "vitest";
import type { SavingsGoalTimeline } from "../../services/api";
import { historyRows } from "./goalHistoryRows";

/** A timeline month with the given per-goal `[balance, change]` and free cash. */
function month(
  key: string,
  goals: Record<number, [number, number]>,
  freeCash = 0,
): SavingsGoalTimeline["months"][number] {
  return {
    month: key,
    free_cash: freeCash,
    goals: Object.entries(goals).map(([id, [balance, change]]) => ({
      goal_id: Number(id),
      balance,
      change,
    })),
  };
}

const MONTHS = [
  month("2026-01", { 1: [1000, 1000] }, 5000),
  month("2026-02", { 1: [1500, 500], 2: [2000, 2000] }, 4000),
  month("2026-03", { 1: [1200, -300], 2: [2000, 0] }, -600),
];

describe("goal history rows", () => {
  it("reads each month's movement in the monthly view", () => {
    const rows = historyRows(MONTHS, "monthly");

    expect(rows[1]).toEqual({ month: "2026-02", free_cash: 4000, g1: 500, g2: 2000 });
    expect(rows.map((row) => row.g1)).toEqual([1000, 500, -300]);
  });

  it("reads each goal's month-end balance in the cumulative view", () => {
    const rows = historyRows(MONTHS, "cumulative");

    expect(rows.map((row) => row.g1)).toEqual([1000, 1500, 1200]);
    expect(rows.map((row) => row.g2)).toEqual([undefined, 2000, 2000]);
  });

  it("keeps free cash as the balance it already is, below zero included", () => {
    for (const mode of ["monthly", "cumulative"] as const) {
      expect(historyRows(MONTHS, mode).map((row) => row.free_cash)).toEqual([
        5000, 4000, -600,
      ]);
    }
  });
});
