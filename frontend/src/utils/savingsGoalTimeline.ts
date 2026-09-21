import type { SavingsGoalTimelineMonth } from "../services/api";

/**
 * What the waterfall left of a month's surplus.
 *
 * `allocated` counts only the money that went into goals and `clawed_back`
 * only the money that came back out — the backend reports them apart so that
 * neither hides the other — so netting both against the surplus is what the
 * pool kept. Negative when the month spent more than it earned and the pool
 * covered the difference.
 *
 * This is a flow, and stacks with the per-goal bars because they are all cuts
 * of the same month's surplus. The pool *balance* is a different quantity and
 * is not stackable with any of them.
 *
 * Parameters
 * ----------
 * month
 *   One row of `GET /savings-goals/timeline`.
 */
export function unclaimedSurplus(month: SavingsGoalTimelineMonth): number {
  // Two 2dp figures do not subtract to a 2dp float.
  return (
    Math.round((month.surplus - month.allocated + month.clawed_back) * 100) / 100
  );
}
