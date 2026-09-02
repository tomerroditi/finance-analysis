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
 * A track is depleted at the point after its LAST positive value — i.e.
 * where it drops to 0 or below and never recovers, in any phase. That point
 * is clamped to exactly 0 and everything after it becomes `null`, so the
 * line touches zero and stops instead of diving into meaningless negative
 * territory. The chart's x-range ends where the LONGEST-surviving track
 * depletes; if any track never depletes, the full horizon is kept.
 *
 * Tracks that dip to/below zero but climb back (a planned big expense, a
 * debt-heavy start that recovers) are NOT depleted — they plot in full,
 * negative stretch included, because the recovery is the story. Only a
 * terminal collapse is cut.
 */
export function truncateProjectionAtDepletion(
  data: ProjectionPoint[],
): TruncatedPoint[] {
  const depletionIdx = {} as Record<ScenarioKey, number>;
  for (const key of SCENARIO_KEYS) {
    let lastPositive = -1;
    for (let i = data.length - 1; i >= 0; i--) {
      if (data[i][key] > 0) {
        lastPositive = i;
        break;
      }
    }
    // Depletion = a positive point followed by a terminal <= 0 tail. A track
    // that is never positive, or is still positive at the horizon, never
    // depletes.
    depletionIdx[key] =
      lastPositive >= 0 && lastPositive < data.length - 1
        ? lastPositive + 1
        : -1;
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
