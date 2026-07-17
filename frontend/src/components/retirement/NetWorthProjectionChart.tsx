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

interface DataPoint {
  age: number;
  net_worth_optimistic: number;
  net_worth_baseline: number;
  net_worth_conservative: number;
}

interface Props {
  data: DataPoint[];
  fireNumber: number;
  targetAge: number;
}

export function NetWorthProjectionChart({ data, fireNumber, targetAge }: Props) {
  const { t } = useTranslation();

  const rows = useMemo(
    () =>
      data.map((d) => ({
        ...d,
        // Conservative→optimistic range rendered as a band area.
        band: [d.net_worth_conservative, d.net_worth_optimistic] as [number, number],
      })),
    [data],
  );

  const ages = data.map((d) => d.age);
  const minAge = ages[0] ?? 0;
  const maxAge = ages[ages.length - 1] ?? 0;
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
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: CHART_TEXT_COLOR }} />
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
          <ReferenceLine
            x={67}
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
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
