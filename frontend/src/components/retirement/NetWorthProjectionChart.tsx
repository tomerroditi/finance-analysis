import Plot from "react-plotly.js";
import { useTranslation } from "react-i18next";
import { plotlyConfig, chartTheme, isTouchDevice } from "../../utils/plotlyLocale";

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

  const ages = data.map((d) => d.age);

  const traces: Plotly.Data[] = [
    // Conservative-optimistic band
    {
      x: [...ages, ...ages.slice().reverse()],
      y: [
        ...data.map((d) => d.net_worth_optimistic),
        ...data
          .slice()
          .reverse()
          .map((d) => d.net_worth_conservative),
      ],
      fill: "toself",
      fillcolor: "rgba(59, 130, 246, 0.1)",
      line: { color: "transparent" },
      showlegend: false,
      hoverinfo: "skip" as const,
      type: "scatter" as const,
    },
    // Baseline line
    {
      x: ages,
      y: data.map((d) => d.net_worth_baseline),
      name: t("earlyRetirement.charts.baseline"),
      line: { color: "#3b82f6", width: 3 },
      type: "scatter" as const,
      mode: "lines" as const,
    },
    // Optimistic
    {
      x: ages,
      y: data.map((d) => d.net_worth_optimistic),
      name: t("earlyRetirement.charts.optimistic"),
      line: { color: "#10b981", width: 1.5, dash: "dot" },
      type: "scatter" as const,
      mode: "lines" as const,
    },
    // Conservative
    {
      x: ages,
      y: data.map((d) => d.net_worth_conservative),
      name: t("earlyRetirement.charts.conservative"),
      line: { color: "#f59e0b", width: 1.5, dash: "dot" },
      type: "scatter" as const,
      mode: "lines" as const,
    },
  ];

  const shapes: Partial<Plotly.Shape>[] = [
    // FIRE number threshold
    {
      type: "line",
      x0: ages[0],
      x1: ages[ages.length - 1],
      y0: fireNumber,
      y1: fireNumber,
      line: { color: "#ef4444", width: 2, dash: "dash" },
    },
    // Target retirement age
    {
      type: "line",
      x0: targetAge,
      x1: targetAge,
      y0: 0,
      y1: Math.max(...data.map((d) => d.net_worth_optimistic)) * 1.1,
      line: { color: "#a855f7", width: 2, dash: "dashdot" },
    },
    // Age 67 - Bituach Leumi
    {
      type: "line",
      x0: 67,
      x1: 67,
      y0: 0,
      y1: Math.max(...data.map((d) => d.net_worth_optimistic)) * 1.1,
      line: { color: "#6b7280", width: 1, dash: "dot" },
    },
  ];

  const annotations: Partial<Plotly.Annotations>[] = [
    {
      x: ages[ages.length - 1],
      y: fireNumber,
      text: t("earlyRetirement.charts.fireTarget"),
      showarrow: false,
      font: { color: "#ef4444", size: 11 },
      xanchor: "right" as const,
      yshift: 15,
    },
    {
      x: targetAge,
      y: 0,
      text: t("earlyRetirement.charts.retirementAge"),
      showarrow: false,
      font: { color: "#a855f7", size: 11 },
      textangle: "-90",
      xshift: -15,
      yshift: 60,
    },
    {
      x: 67,
      y: 0,
      text: t("earlyRetirement.charts.pensionAge"),
      showarrow: false,
      font: { color: "#6b7280", size: 10 },
      textangle: "-90",
      xshift: -12,
      yshift: 50,
    },
  ];

  return (
    <Plot
      data={traces}
      layout={{
        ...chartTheme,
        margin: { ...chartTheme.margin, l: 80 },
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
        shapes,
        annotations,
        hovermode: isTouchDevice ? "closest" : ("x unified" as const),
      }}
      config={plotlyConfig()}
      useResizeHandler
      style={{ width: "100%", minHeight: "300px", height: "400px" }}
    />
  );
}
