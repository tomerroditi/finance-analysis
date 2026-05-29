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

const EXCLUDED_RULES = new Set(["Total Budget", "Other Expenses"]);

/**
 * Build a budget-vs-actual series for the trailing `months` calendar months
 * ending at (and including) the given year/month.
 *
 * Reuses the per-month `["budgetAnalysis", y, m, includeSplitParents]` queries
 * — the monthly view already prefetches ±2 months, so most of these are warm
 * cache hits. `budget` and `actual` are derived with the same exclusions the
 * KPI summary uses, keeping a single source of truth for the totals.
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
    const relevant = rules.filter((item) => !EXCLUDED_RULES.has(item.rule.name));
    const budget = relevant.reduce((sum, item) => sum + (item.rule.amount || 0), 0);
    const actual = relevant.reduce(
      (sum, item) => sum + Math.abs(item.current_amount || 0),
      0,
    );
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
