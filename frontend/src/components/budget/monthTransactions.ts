/** The monthly analysis's synthetic roll-up row. */
export const TOTAL_BUDGET = "Total Budget";

interface RuleLike {
  name: string;
  category?: string;
}

interface AnalysisEntryLike<Row> {
  rule: RuleLike;
  data?: Row[] | null;
}

/**
 * Whether an analysis entry is the month's Total Budget row.
 *
 * Its category is the canonical marker (`TOTAL_BUDGET` in
 * `backend/constants/budget.py`); the name is checked too because older
 * fixtures and project analyses carry only that.
 */
export const isTotalBudget = (rule: RuleLike): boolean =>
  rule.category === TOTAL_BUDGET || rule.name === TOTAL_BUDGET;

/**
 * Every transaction the month's monthly pool holds — the Total Budget's list.
 *
 * `GET /budget/analysis` no longer sends the pool twice: the Total Budget
 * entry's `data` is empty whenever another entry exists, because every pool
 * row is already listed under the rule that claimed it or under Other
 * Expenses. The list is their union. A month with only a Total Budget rule
 * still carries its rows on the Total, and so does a response cached before
 * the change — both are used as they are.
 *
 * @param entries - The analysis's `rules`.
 * @returns The pool's rows, each once.
 */
export function monthTransactions<Row>(entries: readonly AnalysisEntryLike<Row>[]): Row[] {
  const total = entries.find((entry) => isTotalBudget(entry.rule));
  if (total?.data?.length) return total.data;
  return entries
    .filter((entry) => !isTotalBudget(entry.rule))
    .flatMap((entry) => entry.data ?? []);
}

interface UncategorizedSource {
  rules?: readonly AnalysisEntryLike<{ category?: string | null; amount?: number | null }>[] | null;
  uncategorized_count?: number;
  uncategorized_amount?: number;
}

/**
 * How many of the month's pool rows carry no category, and their gross total.
 *
 * Served as `uncategorized_count` / `uncategorized_amount`; computed from the
 * Total Budget's rows only for a response cached before those fields existed.
 */
export function uncategorizedSummary(analysis: UncategorizedSource | undefined): {
  count: number;
  amount: number;
} {
  if (analysis?.uncategorized_count !== undefined) {
    return { count: analysis.uncategorized_count, amount: analysis.uncategorized_amount ?? 0 };
  }
  const total = (analysis?.rules ?? []).find((entry) => isTotalBudget(entry.rule));
  const rows = (total?.data ?? []).filter((row) => !row.category);
  return {
    count: rows.length,
    amount: rows.reduce((sum, row) => sum + Math.abs(row.amount ?? 0), 0),
  };
}
