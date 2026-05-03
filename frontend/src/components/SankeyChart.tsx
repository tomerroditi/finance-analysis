import Plot from "react-plotly.js";
import { chartTheme, plotlyConfig } from "../utils/plotlyLocale";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

interface SankeyData {
  nodes: number[]; // Indices
  node_labels: string[];
  links: {
    source: number;
    target: number;
    value: number;
    label: string;
  }[];
}

interface SankeyChartProps {
  data: SankeyData;
  height?: number;
}

export function SankeyChart({ data, height = 500 }: SankeyChartProps) {
  const { t } = useTranslation();
  const plotData = useMemo(() => {
    if (!data || data.nodes.length === 0) return [];

    return [
      {
        type: "sankey",
        orientation: "h",
        // Using "perpendicular" arrangement gives Plotly room to space nodes
        // vertically, which reduces the visual collision between right-side
        // labels on dense flows.
        arrangement: "perpendicular",
        textfont: { size: 11, color: "#cbd5e1", family: "Inter, sans-serif" },
        node: {
          // Larger pad = more vertical gap between adjacent nodes (and their
          // labels). Bumping from 15 -> 28 prevents the right-column labels
          // from butting into each other.
          pad: 28,
          thickness: 20,
          line: {
            color: "black",
            width: 0.5,
          },
          label: data.node_labels,
          color: data.node_labels.map((_, i) => {
            // Simple color cycling
            const colors = [
              "#3b82f6",
              "#10b981",
              "#f59e0b",
              "#ef4444",
              "#8b5cf6",
              "#ec4899",
              "#6366f1",
              "#14b8a6",
              "#f97316",
              "#06b6d4",
            ];
            return colors[i % colors.length];
          }),
        },
        link: {
          source: data.links.map((l) => l.source),
          target: data.links.map((l) => l.target),
          value: data.links.map((l) => l.value),
          // color: "rgba(100, 100, 100, 0.2)" // semi-transparent gray
        },
      },
    ];
  }, [data]);

  const layout = {
    ...chartTheme,
    // Reserve real estate for the destination labels on the right (and source
    // labels on the left under RTL flipping). Per
    // .claude/rules/frontend_responsive.md, keep the *other* margins tight.
    margin: { t: 20, b: 20, l: 80, r: 140 },
    height: height,
    autosize: true,
  };

  if (!data || !data.nodes || !data.nodes.length) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
        {t("common.noData")}
      </div>
    );
  }

  return (
    <Plot
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data={plotData as any}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      layout={layout as any}
      useResizeHandler={true}
      style={{ width: "100%", height: "100%" }}
      config={plotlyConfig()}
    />
  );
}
