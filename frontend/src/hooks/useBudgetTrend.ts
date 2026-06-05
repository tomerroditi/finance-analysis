import { useQueries } from "@tanstack/react-query";
import { budgetApi } from "../services/api";

export interface BudgetTrendPoint {
  /** ISO-ish month key, e.g. "2026-05". */
  key: string;
  year: number;
  month: number;
  budget: number;
  actual: number;
}

interface TrendRuleItem {
  rule: { name: string; amount: number };
  current_amount: number;
}

/**
 * Build a budget-vs-actual series for the trailing `months` calendar months
 * ending at (and including) the given year/month.
 *
 * Reuses the per-month `["budgetAnalysis", y, m, includeSplitParents]` queries
 * — the monthly view already prefetches ±2 months, so most of these are warm
 * cache hits. `budget` and `actual` come from the month's "Total Budget" row —
 * the same single source of truth the monthly gauge uses — so the trend bars
 * match the gauge exactly. (A month with no budget rules at all has no row and
 * plots zeros.)
 */
export function useBudgetTrend(
  year: number,
  month: number,
  months = 6,
  includeSplitParents = false,
) {
  const periods = Array.from({ length: months }, (_, i) => {
    const offset = months - 1 - i;
    const date = new Date(year, month - 1 - offset);
    return { year: date.getFullYear(), month: date.getMonth() + 1 };
  });

  const results = useQueries({
    queries: periods.map((p) => ({
      queryKey: ["budgetAnalysis", p.year, p.month, includeSplitParents],
      queryFn: () =>
        budgetApi
          .getAnalysis(p.year, p.month, includeSplitParents)
          .then((res) => res.data),
      staleTime: 60 * 1000,
    })),
  });

  const isLoading = results.some((r) => r.isLoading);

  const data: BudgetTrendPoint[] = periods.map((p, i) => {
    const rules: TrendRuleItem[] = results[i].data?.rules ?? [];

    // The "Total Budget" row is the source of truth: its amount is the
    // configured monthly cap and its current_amount is the month's total
    // spend. Summing the per-category rules instead would undercount the
    // budget (it ignores headroom not allocated to a rule) and the actual
    // (it drops the "Other Expenses" catch-all).
    const totalRule = rules.find((item) => item.rule.name === "Total Budget");
    const budget = totalRule?.rule.amount || 0;
    const actual = Math.abs(totalRule?.current_amount || 0);

    return {
      key: `${p.year}-${String(p.month).padStart(2, "0")}`,
      year: p.year,
      month: p.month,
      budget,
      actual,
    };
  });

  const hasData = data.some((d) => d.budget > 0 || d.actual > 0);

  return { data, isLoading, hasData };
}
