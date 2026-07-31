/**
 * Depletion truncation for the net worth projection chart.
 *
 * Lives in its own module (not NetWorthProjectionChart.tsx) so the chart
 * file only exports a component — react-refresh/only-export-components.
 */

export interface ProjectionPoint {
  age: number;
  net_worth_optimistic: number;
  net_worth_baseline: number;
  net_worth_conservative: number;
}

const SCENARIO_KEYS = [
  "net_worth_optimistic",
  "net_worth_baseline",
  "net_worth_conservative",
] as const;

type ScenarioKey = (typeof SCENARIO_KEYS)[number];

export type TruncatedPoint = { age: number } & Record<
  ScenarioKey,
  number | null
>;

/**
 * Cut the projection off where the portfolio is exhausted.
 *
 * Each scenario line ends at its own depletion point: the first age (in the
 * drawdown phase, `age >= targetAge`) where it reaches 0 or below is clamped
 * to exactly 0, and everything after it becomes `null` so the line stops
 * instead of diving into meaningless negative territory. The chart's x-range
 * ends where the LONGEST-surviving track hits zero; if any track never
 * depletes, the full horizon is kept.
 *
 * A negative value BEFORE the target age is not depletion — that's a normal
 * accumulation-phase state for anyone carrying a mortgage — so those points
 * are plotted as-is.
 */
export function truncateProjectionAtDepletion(
  data: ProjectionPoint[],
  targetAge: number,
): TruncatedPoint[] {
  const depletionIdx = {} as Record<ScenarioKey, number>;
  for (const key of SCENARIO_KEYS) {
    depletionIdx[key] = data.findIndex(
      (d) => d.age >= targetAge && d[key] <= 0,
    );
  }

  const indices = SCENARIO_KEYS.map((key) => depletionIdx[key]);
  const cutoffIdx = indices.every((i) => i !== -1)
    ? Math.max(...indices)
    : data.length - 1;

  return data.slice(0, cutoffIdx + 1).map((d, i) => {
    const value = (key: ScenarioKey): number | null => {
      const di = depletionIdx[key];
      if (di === -1 || i < di) return d[key];
      return i === di ? 0 : null; // touch zero, then stop the line
    };
    return {
      age: d.age,
      net_worth_optimistic: value("net_worth_optimistic"),
      net_worth_baseline: value("net_worth_baseline"),
      net_worth_conservative: value("net_worth_conservative"),
    };
  });
}
