import { describe, it, expect } from "vitest";
import { matchQuery, type Query, type QueryKey } from "@tanstack/react-query";
import { makeQueryKeys } from "../../services/queryKeys";
import type { RefreshPlan } from "../../queryInvalidation";
import { monthlyRulePlan, projectPlan, savingsGoalPlan, yearlyRulePlan } from "./budgetPlans";

const qk = makeQueryKeys(false);

/** Whether the sweep after a write following `plan` refreshes `key`. */
function refreshes(plan: RefreshPlan, key: QueryKey): boolean {
  const query = { queryKey: key, queryHash: JSON.stringify(key) } as unknown as Query;
  const under = (keys: readonly QueryKey[] | undefined) =>
    (keys ?? []).some((queryKey) => matchQuery({ queryKey }, query));
  if (under(plan.first)) return true;
  if (plan.only !== undefined) return under(plan.only);
  return !under(plan.skip);
}

describe("monthlyRulePlan", () => {
  const plan = monthlyRulePlan(2026, 10);

  it("refetches the edited month first", () => {
    expect(plan.first).toEqual([["budget", "analysis", 2026, 10]]);
  });

  it("refreshes what a rule feeds: the budget, insights, the forecast and onboarding", () => {
    for (const key of [
      qk.budget.analysis(2026, 9, false),
      qk.budget.trend(2026, 10, 12, false),
      qk.budget.overview(2026, 10, false),
      qk.budget.categoryConflicts(),
      qk.budget.availableProjects(),
      qk.analytics.insights(),
      qk.analytics.cashFlowForecast(),
      ["onboardingStatus"],
      qk.fire.plan(),
    ]) {
      expect(refreshes(plan, key), JSON.stringify(key)).toBe(true);
    }
  });

  it("leaves alone what no budget rule can change", () => {
    for (const key of [
      qk.transactions.list(undefined, false),
      qk.pendingRefunds.all(),
      qk.investments.portfolio(),
      qk.liabilities.list(false),
      qk.balances.cash(),
      qk.savingsGoals.all(),
      qk.analytics.overview(),
      qk.analytics.recurring(),
      qk.tagging.categories(),
      qk.tagging.rules(),
      qk.credentials.accounts(),
    ]) {
      expect(refreshes(plan, key), JSON.stringify(key)).toBe(false);
    }
  });
});

describe("yearlyRulePlan", () => {
  it("refetches the year and the Overview first, and keeps the conflict notice live", () => {
    const plan = yearlyRulePlan(2026);
    expect(plan.first).toEqual([
      ["budget", "yearly", 2026],
      ["budget", "overview"],
    ]);
    expect(refreshes(plan, qk.budget.categoryConflicts())).toBe(true);
    expect(refreshes(plan, qk.budget.analysis(2026, 3, false))).toBe(true);
    expect(refreshes(plan, qk.transactions.list(undefined, false))).toBe(false);
  });
});

describe("projectPlan", () => {
  it("lets creating or deleting a project reach analytics and the retirement plan", () => {
    const plan = projectPlan("Wedding", "structure");
    expect(plan.first).toEqual([
      ["budget", "projects-status"],
      ["budget", "project-details", "Wedding"],
    ]);
    for (const key of [
      qk.analytics.expensesByCategoryOverTime("pending", true, false),
      qk.analytics.recurring(),
      qk.fire.planProjection(),
      qk.budget.projects(),
      qk.budget.availableProjects(),
    ]) {
      expect(refreshes(plan, key), JSON.stringify(key)).toBe(true);
    }
    expect(refreshes(plan, qk.transactions.list(undefined, false))).toBe(false);
  });

  it("keeps an edit off the analytics a project's total cannot move", () => {
    const plan = projectPlan("Wedding", "edit");
    expect(refreshes(plan, qk.analytics.expensesByCategoryOverTime("pending", true, false))).toBe(false);
    expect(refreshes(plan, qk.analytics.insights())).toBe(true);
    expect(refreshes(plan, qk.budget.overview(2026, 10, false))).toBe(true);
  });
});

describe("savingsGoalPlan", () => {
  const plan = savingsGoalPlan();

  it("refreshes the goals and the budget month that shows them", () => {
    expect(refreshes(plan, qk.savingsGoals.all())).toBe(true);
    expect(refreshes(plan, qk.savingsGoals.yearly())).toBe(true);
    expect(refreshes(plan, qk.budget.analysis(2026, 10, false))).toBe(true);
  });

  it("leaves the rest of the app alone", () => {
    for (const key of [
      qk.budget.trend(2026, 10, 12, false),
      qk.budget.overview(2026, 10, false),
      qk.transactions.list(undefined, false),
      qk.analytics.insights(),
      qk.fire.plan(),
      qk.balances.cash(),
    ]) {
      expect(refreshes(plan, key), JSON.stringify(key)).toBe(false);
    }
  });
});
