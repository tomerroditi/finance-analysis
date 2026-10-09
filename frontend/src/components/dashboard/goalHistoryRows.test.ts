import { describe, expect, it } from "vitest";
import type { SavingsGoalTimeline } from "../../services/api";
import { cumulativeRows, lastMonths, monthlyRows } from "./goalHistoryRows";

/** A timeline month with the given per-goal totals and free cash. */
function month(
  key: string,
  goals: Record<number, number>,
  freeCash = 0,
): SavingsGoalTimeline["months"][number] {
  return {
    month: key,
    goals: Object.entries(goals).map(([id, total]) => ({
      goal_id: Number(id),
      name: `Goal ${id}`,
      allocated: total,
      contributed: 0,
      bridged: 0,
      total,
    })),
    allocated: 0,
    clawed_back: 0,
    surplus: 0,
    free_cash: freeCash,
    is_provisional: false,
  };
}

const MONTHS = [
  month("2026-01", { 1: 1000 }, 5000),
  month("2026-02", { 1: 500, 2: 2000 }, 4000),
  month("2026-03", { 1: -300 }, 6000),
  month("2026-04", {}, 6500),
];

describe("goal history rows", () => {
  it("reads each month's own funding in the monthly view", () => {
    const rows = monthlyRows(MONTHS);

    expect(rows[1]).toEqual({ month: "2026-02", free_cash: 4000, g1: 500, g2: 2000 });
    expect(rows[3]).toEqual({ month: "2026-04", free_cash: 6500 });
  });

  it("adds them up in the cumulative view, clawbacks included", () => {
    const rows = cumulativeRows(MONTHS, []);

    expect(rows.map((row) => row.g1)).toEqual([1000, 1500, 1200, 1200]);
    expect(rows.map((row) => row.g2)).toEqual([undefined, 2000, 2000, 2000]);
  });

  it("keeps free cash as the balance it already is", () => {
    const rows = cumulativeRows(MONTHS, []);

    expect(rows.map((row) => row.free_cash)).toEqual([5000, 4000, 6000, 6500]);
  });

  it("starts a goal from its opening balance, so the last bar matches its card", () => {
    const rows = cumulativeRows(MONTHS, [
      { id: 2, opening_balance: 3000, start_month: "2026-02" },
      { id: 1, opening_balance: 0, start_month: "2026-01" },
    ]);

    expect(rows[0].g2).toBeUndefined();
    expect(rows.map((row) => row.g2).slice(1)).toEqual([5000, 5000, 5000]);
  });

  it("books an opening balance from before the history in its first month", () => {
    const rows = cumulativeRows(MONTHS, [
      { id: 3, opening_balance: 800, start_month: "2025-06" },
    ]);

    expect(rows[0].g3).toBe(800);
  });

  it("trims to the window after adding up the whole history", () => {
    const rows = lastMonths(cumulativeRows(MONTHS, []), 2);

    expect(rows.map((row) => row.month)).toEqual(["2026-03", "2026-04"]);
    expect(rows[0].g1).toBe(1200);
    expect(lastMonths(rows, 0)).toHaveLength(2);
  });
});
