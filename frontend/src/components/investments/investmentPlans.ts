import type { QueryKey } from "@tanstack/react-query";
import type { RefreshPlan } from "../../queryInvalidation";
import { qkPrefix } from "../../services/queryKeys";
import { staticExcept } from "../budget/budgetPlans";

/** What the Investments page waits on after a write: the list and the portfolio. */
export const PAGE_FIRST: readonly QueryKey[] = [
  ["investments", "list"],
  ["investments", "portfolio"],
];

/**
 * How an investment write refreshes the cache.
 *
 * An investment record (and its snapshots) feeds the investments reads, net
 * worth and the other analytics, and the retirement plan — never a
 * transaction, the budget, a cash balance or a savings goal, and none of the
 * app's static families except two: an edit can rename a synced fund
 * (`custom_name`, shown on the Insurances page), and creating or deleting
 * one flips the onboarding check's `has_investments`.
 *
 * @param first - What the screen waits on.
 * @param also - The static families this write does reach.
 */
export function investmentPlan(
  first: readonly QueryKey[],
  also: { insurance?: boolean; onboarding?: boolean } = {},
): { refresh: RefreshPlan } {
  const keep: QueryKey[] = [];
  if (also.insurance) keep.push(qkPrefix.insuranceAccounts);
  if (also.onboarding) keep.push(["onboardingStatus"]);
  return {
    refresh: {
      first,
      skip: [
        qkPrefix.transactions,
        qkPrefix.pendingRefunds,
        qkPrefix.budget,
        qkPrefix.cashBalances,
        qkPrefix.savingsGoals,
        ...staticExcept(...keep),
      ],
    },
  };
}
