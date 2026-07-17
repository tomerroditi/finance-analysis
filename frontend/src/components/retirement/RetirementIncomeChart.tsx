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

  const bars = [
    { dataKey: "salary_savings", name: t("earlyRetirement.income.salarySavings"), color: "#06b6d4" },
    { dataKey: "portfolio_withdrawal", name: t("earlyRetirement.income.portfolioWithdrawal"), color: "#3b82f6" },
    { dataKey: "pension", name: t("earlyRetirement.income.pension"), color: "#10b981" },
    { dataKey: "bituach_leumi", name: t("earlyRetirement.income.bituachLeumi"), color: "#a855f7" },
    { dataKey: "passive_income", name: t("earlyRetirement.income.passiveIncome"), color: "#f59e0b" },
  ];

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
            content={
              <ChartTooltip labelFormatter={(age) => `${t("earlyRetirement.charts.age")} ${age}`} />
            }
          />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11, color: CHART_TEXT_COLOR }} />
          {bars.map((b) => (
            <Bar
              key={b.dataKey}
              dataKey={b.dataKey}
              name={b.name}
              stackId="income"
              fill={b.color}
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
