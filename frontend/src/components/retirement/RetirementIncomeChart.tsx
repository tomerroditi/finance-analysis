import Plot from "react-plotly.js";
import { useTranslation } from "react-i18next";
import { plotlyConfig, chartTheme } from "../../utils/plotlyLocale";

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

  const traces: Plotly.Data[] = [
    {
      x: ages,
      y: data.map((d) => d.salary_savings),
      name: t("earlyRetirement.income.salarySavings"),
      type: "bar" as const,
      marker: { color: "#06b6d4" },
    },
    {
      x: ages,
      y: data.map((d) => d.portfolio_withdrawal),
      name: t("earlyRetirement.income.portfolioWithdrawal"),
      type: "bar" as const,
      marker: { color: "#3b82f6" },
    },
    {
      x: ages,
      y: data.map((d) => d.pension),
      name: t("earlyRetirement.income.pension"),
      type: "bar" as const,
      marker: { color: "#10b981" },
    },
    {
      x: ages,
      y: data.map((d) => d.bituach_leumi),
      name: t("earlyRetirement.income.bituachLeumi"),
      type: "bar" as const,
      marker: { color: "#a855f7" },
    },
    {
      x: ages,
      y: data.map((d) => d.passive_income),
      name: t("earlyRetirement.income.passiveIncome"),
      type: "bar" as const,
      marker: { color: "#f59e0b" },
    },
    {
      x: ages,
      y: data.map((d) => d.expenses),
      name: t("earlyRetirement.income.expenses"),
      type: "scatter" as const,
      mode: "lines" as const,
      line: { color: "#ef4444", width: 2.5, dash: "dash" },
    },
  ];

  return (
    <Plot
      data={traces}
      layout={{
        ...chartTheme,
        margin: { ...chartTheme.margin, l: 80 },
        barmode: "stack" as const,
        xaxis: {
          title: { text: t("earlyRetirement.charts.age") },
          gridcolor: "rgba(148, 163, 184, 0.1)",
          dtick: 5,
        },
        yaxis: {
          gridcolor: "rgba(148, 163, 184, 0.1)",
          tickformat: ",.0f",
          automargin: true,
        },
        legend: {
          orientation: "h" as const,
          y: -0.2,
          x: 0.5,
          xanchor: "center" as const,
        },
        hovermode: "x unified" as const,
      }}
      config={plotlyConfig()}
      useResizeHandler
      style={{ width: "100%", height: "400px" }}
    />
  );
}
