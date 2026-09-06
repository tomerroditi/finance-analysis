import type { BudgetRule } from "./types";

export interface AnalysisEntry {
  rule: { id: number; name: string; category: string; amount: number };
  current_amount: number;
}

export interface NormalizedAnalysis {
  rules: BudgetRule[];
  totalBudget: number;
  totalSpent: number;
}

const TOTAL_BUDGET_RULE = "Total Budget";

/**
 * Fold a monthly or project analysis payload into what the card renders.
 *
 * Both carry a synthetic "Total Budget" row that supplies the totals and must
 * not appear as a tile. Yearly analysis has no such row and does not use this —
 * its totals come from the server's roll-up instead.
 */
export function normalizeAnalysis(
  entries: AnalysisEntry[],
  spentFallback?: number,
): NormalizedAnalysis {
  const rules: BudgetRule[] = entries.map((item) => ({
    id: item.rule.id,
    name: item.rule.name,
    category: item.rule.category,
    budget_amount: item.rule.amount,
    spent_amount: item.current_amount,
  }));
  const totalRule = rules.find((r) => r.name === TOTAL_BUDGET_RULE);
  return {
    rules: rules
      .filter((r) => r.name !== TOTAL_BUDGET_RULE)
      .sort((a, b) => b.spent_amount - a.spent_amount),
    totalBudget:
      totalRule?.budget_amount ?? rules.reduce((sum, r) => sum + r.budget_amount, 0),
    totalSpent:
      totalRule?.spent_amount ??
      spentFallback ??
      rules.reduce((sum, r) => sum + r.spent_amount, 0),
  };
}
