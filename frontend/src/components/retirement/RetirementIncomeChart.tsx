import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { useTranslation } from "react-i18next";
import { AXIS_DEFAULTS, CHART_TEXT_COLOR, formatAxisNumber } from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";
import {
  stackEnds,
  roundedStackShape,
  type StackRow,
} from "../charts/stackedBarShape";

interface DataPoint {
  age: number;
  salary_savings: number;
  portfolio_withdrawal: number;
  pension: number;
  bituach_leumi: number;
  passive_income: number;
  total_income: number;
  expenses: number;
}

interface Props {
  data: DataPoint[];
}

/** The stacked income sources, in the order they fill a year's column. */
const INCOME_SERIES = [
  { dataKey: "salary_savings", labelKey: "earlyRetirement.income.salarySavings", color: "#06b6d4" },
  { dataKey: "portfolio_withdrawal", labelKey: "earlyRetirement.income.portfolioWithdrawal", color: "#3b82f6" },
  { dataKey: "pension", labelKey: "earlyRetirement.income.pension", color: "#10b981" },
  { dataKey: "bituach_leumi", labelKey: "earlyRetirement.income.bituachLeumi", color: "#a855f7" },
  { dataKey: "passive_income", labelKey: "earlyRetirement.income.passiveIncome", color: "#f59e0b" },
] as const;

export function RetirementIncomeChart({ data }: Props) {
  const { t } = useTranslation();

  const ages = data.map((d) => d.age);
  const minAge = ages[0] ?? 0;
  const maxAge = ages[ages.length - 1] ?? 0;
  const ageTicks = useMemo(() => {
    const ticks: number[] = [];
    for (let a = Math.ceil(minAge / 5) * 5; a <= maxAge; a += 5) ticks.push(a);
    return ticks;
  }, [minAge, maxAge]);

  const bars = INCOME_SERIES.map((s) => ({ ...s, name: t(s.labelKey) }));

  // Each year's income sources stack into one column, so only the topmost
  // source present that year is rounded — a projection runs over decades, and
  // rounding every segment turns each column into a string of beads.
  const ends = useMemo(
    () =>
      stackEnds(
        data as unknown as StackRow[],
        INCOME_SERIES.map((s) => s.dataKey),
        "age",
      ),
    [data],
  );

  return (
    <div className="w-full" style={{ minHeight: 300, height: 400 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, bottom: 4, left: 8, right: 8 }}>
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
            cursor={false}
            content={
              <ChartTooltip labelFormatter={(age) => `${t("earlyRetirement.charts.age")} ${age}`} />
            }
          />
          <Legend content={<ChartLegend />} />
          {bars.map((b) => (
            <Bar
              key={b.dataKey}
              dataKey={b.dataKey}
              name={b.name}
              stackId="income"
              fill={b.color}
              shape={roundedStackShape(ends, b.dataKey, "age")}
              isAnimationActive={false}
            />
          ))}
          <Line
            dataKey="expenses"
            name={t("earlyRetirement.income.expenses")}
            stroke="#ef4444"
            strokeWidth={2.5}
            strokeDasharray="6 4"
            type="monotone"
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
