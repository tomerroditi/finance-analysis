import type { SavingsGoalTimeline } from "../../services/api";

/** The series key of the free-cash pool in a history row. */
export const FREE_CASH_KEY = "free_cash";

/** One chart row: the month, then a column per series (`g<id>`, free cash). */
export type HistoryRow = Record<string, number | string>;

/** Which reading of the history the chart shows. */
export type HistoryMode = "monthly" | "cumulative";

/** A goal's opening balance and the month it is earmarked in. */
export interface GoalOpening {
  id: number;
  opening_balance: number;
  start_month: string | null;
}

/**
 * One row per month with a column per goal — what each goal received that
 * month — and the free-cash pool as it stood at month end.
 */
export function monthlyRows(months: SavingsGoalTimeline["months"]): HistoryRow[] {
  return months.map((month) => {
    const row: HistoryRow = { month: month.month, [FREE_CASH_KEY]: month.free_cash };
    for (const goal of month.goals) {
      row[`g${goal.goal_id}`] = goal.total;
    }
    return row;
  });
}

/**
 * The same months read as running totals: what each goal has received so far,
 * opening balance included, so a goal's last bar is the amount on its card.
 *
 * Free cash is a standing balance already, not a monthly flow, so it is the
 * same in both readings. A goal appears from the first month it holds
 * anything. The totals only add up from the start of the history, so this
 * needs every month — trim to a window afterwards with {@link lastMonths}.
 */
export function cumulativeRows(
  months: SavingsGoalTimeline["months"],
  openings: GoalOpening[],
): HistoryRow[] {
  const running = new Map<number, number>();
  const pending = openings.filter((goal) => goal.opening_balance);
  return months.map((month) => {
    for (const goal of pending) {
      // An opening balance is earmarked in the goal's start month — or the
      // first month on record, for a goal that started before it.
      const start = goal.start_month?.slice(0, 7) ?? month.month;
      if (start <= month.month && !running.has(goal.id)) {
        running.set(goal.id, goal.opening_balance);
      }
    }
    for (const goal of month.goals) {
      running.set(goal.goal_id, (running.get(goal.goal_id) ?? 0) + goal.total);
    }
    const row: HistoryRow = { month: month.month, [FREE_CASH_KEY]: month.free_cash };
    for (const [id, total] of running) {
      // Adding zero turns a -0 a goal that gave everything back rounds to into 0.
      row[`g${id}`] = Math.round(total * 100) / 100 + 0;
    }
    return row;
  });
}

/** The trailing `count` rows; `0` keeps them all. */
export function lastMonths(rows: HistoryRow[], count: number): HistoryRow[] {
  return count > 0 ? rows.slice(-count) : rows;
}
