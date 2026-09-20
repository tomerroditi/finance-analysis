import { useQuery } from "@tanstack/react-query";
import { budgetApi } from "../services/api";
import { useQueryKeys } from "./useQueryKeys";

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

/** Per-rule spend series, aligned index-for-index with the returned `data`. */
export type RuleTrendMap = Record<string, number[]>;

/**
 * Build a budget-vs-actual series for the trailing `months` calendar months
 * ending at (and including) the given year/month.
 *
 * Served by a single `GET /budget/trend/{year}/{month}`. This used to run one
 * `qk.budget.analysis(y, m, …)` query per month — twelve concurrent requests
 * for a twelve-month sparkline, re-fired in full by the global
 * `MutationCache` invalidation after *every* mutation. Individually cheap,
 * collectively saturating: `/budget/overview` answers in ~0.5 s on its own
 * and ~12 s alongside them, which is how the Overview came to sit on stale
 * data for twelve seconds after reopening a project.
 *
 * `budget` and `actual` come from each month's "Total Budget" row — the same
 * single source of truth the monthly gauge uses — so the trend bars match the
 * gauge exactly. A month with no budget rules at all plots zeros.
 */
export function useBudgetTrend(
  year: number,
  month: number,
  months = 6,
  includeSplitParents = false,
) {
  const qk = useQueryKeys();

  const trendQuery = useQuery({
    queryKey: qk.budget.trend(year, month, months, includeSplitParents),
    queryFn: () =>
      budgetApi
        .getTrend(year, month, months, includeSplitParents)
        .then((res) => res.data),
    staleTime: 60 * 1000,
  });

  // The viewed month, read from the analysis query the page already runs.
  // Same key, so React Query serves both callers from one request rather
  // than issuing a second.
  //
  // It is not redundant with the trend's own last point: `/budget/trend` is
  // read-only, while `/budget/analysis` auto-fills an empty current or future
  // month by copying the previous month's rules. Without this overlay, the
  // first visit to a brand-new month would plot a zero bar for it and keep
  // plotting one until something else invalidated the trend.
  const viewedMonthQuery = useQuery({
    queryKey: qk.budget.analysis(year, month, includeSplitParents),
    queryFn: () =>
      budgetApi
        .getAnalysis(year, month, includeSplitParents)
        .then((res) => res.data),
    staleTime: 60 * 1000,
  });

  const isLoading = trendQuery.isLoading || viewedMonthQuery.isLoading;
  const points = trendQuery.data ?? [];

  const viewedRules: TrendRuleItem[] = viewedMonthQuery.data?.rules ?? [];
  const viewedTotal = viewedRules.find(
    (item) => item.rule.name === "Total Budget",
  );
  const hasViewedMonth = viewedMonthQuery.data !== undefined;

  const isViewedMonth = (p: { year: number; month: number }) =>
    p.year === year && p.month === month;

  const data: BudgetTrendPoint[] = points.map((p) => ({
    key: `${p.year}-${String(p.month).padStart(2, "0")}`,
    year: p.year,
    month: p.month,
    budget:
      hasViewedMonth && isViewedMonth(p) ? viewedTotal?.rule.amount || 0 : p.budget,
    actual:
      hasViewedMonth && isViewedMonth(p)
        ? Math.abs(viewedTotal?.current_amount || 0)
        : p.actual,
  }));

  const hasData = data.some((d) => d.budget > 0 || d.actual > 0);

  // Per-rule series, assembled from the same response the total series is
  // built from — no extra requests. Rules are keyed by NAME, not id: a month
  // with no rules of its own is auto-filled by copying the previous month's,
  // which creates fresh rows, so the same envelope has a different
  // `rule.id` in every month.
  const byRule: RuleTrendMap = {};
  points.forEach((p, i) => {
    // Clamp net refunds to 0: a period where refunds exceeded spend is not
    // negative spending, and a negative bar would read as an overspend. The
    // backend already clamps its own values; the overlay below has not been.
    const monthRules =
      hasViewedMonth && isViewedMonth(p)
        ? Object.fromEntries(
            viewedRules.map((item) => [
              item.rule.name,
              Math.max(item.current_amount || 0, 0),
            ]),
          )
        : p.rules;

    for (const [name, amount] of Object.entries(monthRules)) {
      if (!byRule[name]) byRule[name] = points.map(() => 0);
      byRule[name][i] = amount;
    }
  });

  return { data, isLoading, hasData, byRule };
}
