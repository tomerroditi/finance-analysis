import { describe, it, expect } from "vitest";
import { matchQuery, type Query, type QueryKey } from "@tanstack/react-query";
import { makeQueryKeys } from "../../services/queryKeys";
import { investmentPlan, PAGE_FIRST } from "./investmentPlans";

const qk = makeQueryKeys(false);

/** Whether the sweep after a write following this plan refreshes `key`. */
function refreshes(plan: ReturnType<typeof investmentPlan>["refresh"], key: QueryKey) {
  const query = { queryKey: key } as unknown as Query;
  const under = (keys: readonly QueryKey[] | undefined) =>
    (keys ?? []).some((queryKey) => matchQuery({ queryKey }, query));
  return under(plan.first) || !under(plan.skip);
}

describe("investmentPlan", () => {
  it("refreshes what an investment feeds: its own reads, analytics and the retirement plan", () => {
    const { refresh } = investmentPlan(PAGE_FIRST);
    expect(refresh.first).toEqual(PAGE_FIRST);
    for (const key of [
      qk.investments.list(true),
      qk.investments.balanceHistory(true),
      qk.analytics.netWorthOverTime(),
      qk.analytics.overview(),
      qk.fire.planProjection(),
    ]) {
      expect(refreshes(refresh, key), JSON.stringify(key)).toBe(true);
    }
  });

  it("leaves the ledger, the budget, cash, goals and static reads alone", () => {
    const { refresh } = investmentPlan(PAGE_FIRST);
    for (const key of [
      qk.transactions.list(undefined, false),
      qk.pendingRefunds.all(),
      qk.budget.analysis(2026, 10, false),
      qk.balances.cash(),
      qk.savingsGoals.all(),
      qk.insurance.accounts(),
      ["onboardingStatus"],
      qk.tagging.categories(),
    ]) {
      expect(refreshes(refresh, key), JSON.stringify(key)).toBe(false);
    }
  });

  it("keeps the insurance accounts for an edit and onboarding for a create or delete", () => {
    expect(refreshes(investmentPlan(PAGE_FIRST, { insurance: true }).refresh, qk.insurance.accounts())).toBe(true);
    expect(refreshes(investmentPlan(PAGE_FIRST, { onboarding: true }).refresh, ["onboardingStatus"])).toBe(true);
  });
});
