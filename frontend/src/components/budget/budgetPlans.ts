import { hashKey, type QueryKey } from "@tanstack/react-query";
import type { RefreshPlan } from "../../queryInvalidation";
import { qkPrefix } from "../../services/queryKeys";
import { UNCHANGED_BY_RETAG } from "./budgetOptimistic";

/**
 * Refresh plans for the budget's own writes — rules, projects and the
 * savings goals the budget month shows.
 *
 * Each names what its screen waits on (`first`) and the families the write
 * cannot reach (`skip`). When unsure whether a write can reach a family, the
 * family is left out of `skip`: a needless refetch costs a request, a missed
 * one shows stale money.
 */

/** `UNCHANGED_BY_RETAG` without the given keys. */
export function staticExcept(...keep: QueryKey[]): QueryKey[] {
  const kept = new Set(keep.map((key) => hashKey(key)));
  return UNCHANGED_BY_RETAG.filter((key) => !kept.has(hashKey(key)));
}

const ONBOARDING: QueryKey = ["onboardingStatus"];
const CATEGORY_CONFLICTS: QueryKey = ["budget", "category-conflicts"];
const AVAILABLE_PROJECTS: QueryKey = ["budget", "available-projects"];
const PROJECTS: QueryKey = ["budget", "projects"];
const PROJECTS_STATUS: QueryKey = ["budget", "projects-status"];

/**
 * Analytics reads no budget rule feeds. Insights (`services/insights/context.py`
 * reads the rules to tell planned spend from surprises) and the cash-flow
 * forecast (`services/analysis/forecast.py`) do, so they are not listed.
 */
export const ANALYTICS_NOT_FED_BY_BUDGET: readonly QueryKey[] = [
  ["analytics", "overview"],
  ["analytics", "net-worth-over-time"],
  ["analytics", "debt-payments-over-time"],
  ["analytics", "expenses-by-category-over-time"],
  ["analytics", "income-by-source-over-time"],
  qkPrefix.recurring,
];

/** Families a budget rule write never touches: it moves no money and no account. */
const LEDGER_FAMILIES: readonly QueryKey[] = [
  qkPrefix.transactions,
  qkPrefix.pendingRefunds,
  qkPrefix.investments,
  qkPrefix.liabilities,
  qkPrefix.cashBalances,
  qkPrefix.savingsGoals,
];

/**
 * A monthly rule created, edited or deleted. The month's analysis first;
 * the rest of the budget, insights, the forecast and the onboarding check
 * (`has_budgets`) after. A monthly rule claims a category, so the project
 * picker and the conflict notice can change too.
 */
export function monthlyRulePlan(year: number, month: number): RefreshPlan {
  return {
    first: [[...qkPrefix.budgetAnalysis, year, month]],
    skip: [
      ...staticExcept(ONBOARDING, CATEGORY_CONFLICTS, AVAILABLE_PROJECTS),
      ...LEDGER_FAMILIES,
      ...ANALYTICS_NOT_FED_BY_BUDGET,
    ],
  };
}

/** A yearly rule created, edited, closed or deleted: that year's tab and the Overview first. */
export function yearlyRulePlan(year: number): RefreshPlan {
  return {
    first: [
      ["budget", "yearly", year],
      ["budget", "overview"],
    ],
    skip: [
      ...staticExcept(ONBOARDING, CATEGORY_CONFLICTS, AVAILABLE_PROJECTS),
      ...LEDGER_FAMILIES,
      ...ANALYTICS_NOT_FED_BY_BUDGET,
    ],
  };
}

/**
 * A project write: its status and details first.
 *
 * `structure` — a project created or deleted — claims or frees a whole
 * category, which moves its spend in or out of every analytics read that
 * excludes projects (`transaction_views.py`) and the recurring detection
 * (`recurring_service.py`), and so the retirement plan's spending; nothing
 * analytics is skipped. Any other write (the total, a tag rule, closing)
 * changes no analytics read but insights and the forecast.
 */
export function projectPlan(
  name: string | undefined,
  kind: "structure" | "edit",
): RefreshPlan {
  return {
    first: [PROJECTS_STATUS, name ? ["budget", "project-details", name] : ["budget", "project-details"]],
    skip: [
      ...staticExcept(ONBOARDING, CATEGORY_CONFLICTS, AVAILABLE_PROJECTS, PROJECTS, PROJECTS_STATUS),
      ...LEDGER_FAMILIES,
      ...(kind === "edit" ? ANALYTICS_NOT_FED_BY_BUDGET : []),
    ],
  };
}

/**
 * A savings-goal write that moves no transaction: money in or out, a goal's
 * settings, links, order. Goals feed the budget month (`savings_goals` on
 * `/budget/analysis`, `services/budget/monthly.py`), nothing else in the
 * budget, and no ledger read.
 *
 * @param first - What the screen waits on; the goals card's free cash and
 *   month by default.
 */
export function savingsGoalPlan(first?: readonly QueryKey[]): RefreshPlan {
  return {
    first: first ?? [
      ["savings-goals", "free-cash"],
      ["savings-goals", "month"],
    ],
    skip: [
      ...UNCHANGED_BY_RETAG,
      qkPrefix.transactions,
      qkPrefix.pendingRefunds,
      qkPrefix.analytics,
      qkPrefix.investments,
      qkPrefix.liabilities,
      qkPrefix.cashBalances,
      qkPrefix.fire,
      ["budget", "trend"],
      ["budget", "overview"],
      ["budget", "alerts"],
      ["budget", "yearly"],
      ["budget", "project-details"],
    ],
  };
}
