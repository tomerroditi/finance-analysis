import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";
import { useTranslation } from "react-i18next";
import { AXIS_DEFAULTS, CHART_TEXT_COLOR, formatAxisNumber } from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";

interface DataPoint {
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
  data: DataPoint[],
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

interface Props {
  data: DataPoint[];
  fireNumber: number;
  targetAge: number;
  /** Gender-resolved full pension age (67 male / 65 female). */
  pensionAge?: number;
}

export function NetWorthProjectionChart({
  data,
  fireNumber,
  targetAge,
  pensionAge = 67,
}: Props) {
  const { t } = useTranslation();

  const rows = useMemo(
    () =>
      truncateProjectionAtDepletion(data, targetAge).map((d) => ({
        ...d,
        // Conservative→optimistic range rendered as a band area — ends
        // together with whichever of its two bounding lines stops first.
        band:
          d.net_worth_conservative != null && d.net_worth_optimistic != null
            ? ([d.net_worth_conservative, d.net_worth_optimistic] as [
                number,
                number,
              ])
            : null,
      })),
    [data, targetAge],
  );

  const minAge = rows[0]?.age ?? 0;
  const maxAge = rows[rows.length - 1]?.age ?? 0;
  const ageTicks = useMemo(() => {
    const ticks: number[] = [];
    for (let a = Math.ceil(minAge / 5) * 5; a <= maxAge; a += 5) ticks.push(a);
    return ticks;
  }, [minAge, maxAge]);

  return (
    <div className="w-full" style={{ minHeight: 300, height: 400 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 16, bottom: 4, left: 8, right: 8 }}>
          <XAxis
            dataKey="age"
            type="number"
            domain={[minAge, maxAge]}
            ticks={ageTicks}
            {...AXIS_DEFAULTS}
            label={{
              value: t("earlyRetirement.charts.age"),
              position: "insideBottom",
              offset: -2,
              style: { fill: CHART_TEXT_COLOR, fontSize: 11 },
            }}
          />
          <YAxis {...AXIS_DEFAULTS} tickFormatter={formatAxisNumber} width={56} />
          <Tooltip
            content={
              <ChartTooltip labelFormatter={(age) => `${t("earlyRetirement.charts.age")} ${age}`} />
            }
          />
          <Legend content={<ChartLegend />} />
          <Area
            dataKey="band"
            stroke="none"
            fill="rgba(59, 130, 246, 0.1)"
            legendType="none"
            tooltipType="none"
            isAnimationActive={false}
            activeDot={false}
          />
          <Line
            dataKey="net_worth_baseline"
            name={t("earlyRetirement.charts.baseline")}
            stroke="#3b82f6"
            strokeWidth={3}
            type="monotone"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="net_worth_optimistic"
            name={t("earlyRetirement.charts.optimistic")}
            stroke="#10b981"
            strokeWidth={1.5}
            strokeDasharray="2 3"
            type="monotone"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="net_worth_conservative"
            name={t("earlyRetirement.charts.conservative")}
            stroke="#f59e0b"
            strokeWidth={1.5}
            strokeDasharray="2 3"
            type="monotone"
            dot={false}
            isAnimationActive={false}
          />
          <ReferenceLine
            y={fireNumber}
            stroke="#ef4444"
            strokeWidth={2}
            strokeDasharray="6 4"
            label={{
              value: t("earlyRetirement.charts.fireTarget"),
              position: "insideTopRight",
              fill: "#ef4444",
              fontSize: 11,
            }}
          />
          <ReferenceLine
            x={targetAge}
            stroke="#a855f7"
            strokeWidth={2}
            strokeDasharray="8 4 2 4"
            label={{
              value: t("earlyRetirement.charts.retirementAge"),
              angle: -90,
              position: "insideBottomLeft",
              fill: "#a855f7",
              fontSize: 11,
            }}
          />
          {/* Skip the marker when the chart is truncated before pension age */}
          {pensionAge <= maxAge && (
            <ReferenceLine
              x={pensionAge}
              stroke="#6b7280"
              strokeWidth={1}
              strokeDasharray="2 3"
              label={{
                value: t("earlyRetirement.charts.pensionAge"),
                angle: -90,
                position: "insideBottomLeft",
                fill: "#6b7280",
                fontSize: 10,
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
