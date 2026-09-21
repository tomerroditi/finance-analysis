import type { BudgetLongRule } from "../../../services/api";

/**
 * Pure helpers for yearly and project rules.
 *
 * Kept out of the component file so they can be imported without dragging a
 * component along, and so the arithmetic can be tested directly.
 */

/** Bar colour by how full the rule is. Matches BudgetLedgerRow's thresholds. */
export function ruleColor(percent: number): string {
  if (percent > 100) return "bg-rose-500";
  if (percent > 90) return "bg-amber-500";
  return "bg-emerald-500";
}

/** Text colour for the same thresholds. */
export function ruleTextColor(percent: number): string {
  if (percent > 100) return "text-rose-400";
  if (percent > 90) return "text-amber-400";
  return "text-[var(--text-default)]";
}

/**
 * Share of a rule consumed.
 *
 * Spend is clamped at zero first: refunds can push a rule's net negative,
 * and a negative fill would read as a bar running backwards. A rule with no
 * budget at all is either untouched (0%) or entirely unbudgeted spend (100%) —
 * the same treatment the monthly ledger applies to a zero-budget rule.
 */
export function percentOf(rule: BudgetLongRule): number {
  if (rule.budget <= 0) return rule.spent > 0 ? 100 : 0;
  return Math.round((Math.max(rule.spent, 0) / rule.budget) * 100);
}

/** Rules ranked by how full they are, so the ones in trouble come first. */
export function rankRules(
  rules: BudgetLongRule[],
): BudgetLongRule[] {
  return [...rules].sort((a, b) => percentOf(b) - percentOf(a));
}
