import type { SavingsGoalTimeline } from "../../services/api";

/** The series key of free cash in a history row. */
export const FREE_CASH_KEY = "free_cash";

/** One chart row: the month, then a column per series (`g<id>`, free cash). */
export type HistoryRow = Record<string, number | string>;

/** Which reading of the history the chart shows. */
export type HistoryMode = "monthly" | "cumulative";

/**
 * One row per month with a column per goal and free cash as it stood at
 * month end.
 *
 * Monthly reads how much each goal moved that month (added, plus income, less
 * spending); cumulative reads what each goal held at the end of it, so a
 * goal's last bar is the balance on its card. Free cash is a standing balance
 * in both readings.
 */
export function historyRows(
  months: SavingsGoalTimeline["months"],
  mode: HistoryMode,
): HistoryRow[] {
  return months.map((month) => {
    const row: HistoryRow = { month: month.month, [FREE_CASH_KEY]: month.free_cash };
    for (const goal of month.goals) {
      row[`g${goal.goal_id}`] = mode === "cumulative" ? goal.balance : goal.change;
    }
    return row;
  });
}
