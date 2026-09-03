/**
 * Helpers for the per-rule trend sparklines on the Budget page.
 *
 * Monthly rules get their series from the trailing per-month analyses (see
 * `useBudgetTrend`), which already fetches them. Yearly and project rules have
 * no per-period endpoint, so their series is bucketed client-side from the
 * transactions the analysis already returns with each rule.
 */

export interface TrendTransaction {
  date?: string | null;
  amount?: number | null;
}

/** `YYYY-MM` keys for `count` calendar months ending at (and including) year/month. */
export function monthKeysEndingAt(
  year: number,
  month: number,
  count: number,
): string[] {
  return Array.from({ length: count }, (_, i) => {
    const date = new Date(year, month - 1 - (count - 1 - i));
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
  });
}

/** `YYYY-MM` keys for every month of a calendar year. */
export function monthKeysOfYear(year: number): string[] {
  return Array.from(
    { length: 12 },
    (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`,
  );
}

/**
 * Sum transactions into one bucket per month key.
 *
 * Amounts are summed as spend-positive (`-amount`, since expenses are stored
 * negative). `spentReference` is the authoritative total the row already
 * displays: when its sign disagrees with the bucketed total, the whole series
 * is flipped, so a caller passing either sign convention gets a series whose
 * total matches what the row shows instead of a mirrored chart.
 */
export function bucketByMonth(
  transactions: TrendTransaction[] | undefined,
  monthKeys: string[],
  spentReference?: number,
): number[] {
  const index = new Map(monthKeys.map((key, i) => [key, i]));
  const series = monthKeys.map(() => 0);

  for (const tx of transactions ?? []) {
    if (!tx?.date) continue;
    const key = String(tx.date).slice(0, 7);
    const slot = index.get(key);
    if (slot === undefined) continue;
    series[slot] += -(tx.amount ?? 0);
  }

  const total = series.reduce((acc, v) => acc + v, 0);
  if (spentReference !== undefined && total !== 0 && spentReference !== 0) {
    if (Math.sign(total) !== Math.sign(spentReference)) {
      return series.map((v) => -v);
    }
  }
  return series;
}

/** Running total of a series — the shape a burn-down chart plots. */
export function cumulative(series: number[]): number[] {
  let running = 0;
  return series.map((v) => (running += v));
}

/**
 * Index of the last period with activity, used to stop a burn line at "now"
 * instead of drawing a flat tail across months that haven't happened yet.
 * Falls back to the last period so a rule with no spend still plots a point.
 */
export function lastActivePeriod(series: number[]): number {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i] !== 0) return i;
  }
  return series.length - 1;
}
