import { useMemo } from "react";
import { ResponsiveContainer, Sankey, Tooltip, Rectangle } from "recharts";
import { useTranslation } from "react-i18next";
import { ChartTooltip } from "./charts/ChartTooltip";
import { CHART_COLORS } from "../utils/chartStyle";

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

interface SankeyNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  containerWidth?: number;
  payload?: { name: string; value: number };
}

/**
 * Node renderer: coloured bar + label beside it. Labels sit to the right of
 * left-half nodes and to the left of right-half nodes so the outermost
 * columns' labels stay inside the chart bounds.
 */
function SankeyNode({ x = 0, y = 0, width = 0, height = 0, index = 0, containerWidth = 0, payload }: SankeyNodeProps) {
  const isRightHalf = x + width / 2 > containerWidth / 2;
  return (
    <g>
      <Rectangle
        x={x}
        y={y}
        width={width}
        height={height}
        fill={CHART_COLORS[index % CHART_COLORS.length]}
        fillOpacity={0.9}
      />
      <text
        x={isRightHalf ? x - 6 : x + width + 6}
        y={y + height / 2}
        textAnchor={isRightHalf ? "end" : "start"}
        dominantBaseline="central"
        fontSize={11}
        fill="#cbd5e1"
        fontFamily="Inter, sans-serif"
      >
        {payload?.name}
      </text>
    </g>
  );
}

export function SankeyChart({ data, height = 500 }: SankeyChartProps) {
  const { t } = useTranslation();

  const sankeyData = useMemo(() => {
    if (!data || data.nodes.length === 0) return null;
    return {
      nodes: data.node_labels.map((name) => ({ name })),
      links: data.links.map((l) => ({
        source: l.source,
        target: l.target,
        value: l.value,
      })),
    };
  }, [data]);

  if (!sankeyData) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
        {t("common.noData")}
      </div>
    );
  }

  return (
    <div style={{ height }} className="w-full" data-testid="sankey-chart">
      <ResponsiveContainer width="100%" height="100%">
        <Sankey
          data={sankeyData}
          node={<SankeyNode />}
          nodePadding={28}
          nodeWidth={20}
          link={{ stroke: "rgba(148, 163, 184, 0.3)" }}
          margin={{ top: 20, bottom: 20, left: 10, right: 120 }}
        >
          <Tooltip content={<ChartTooltip />} />
        </Sankey>
      </ResponsiveContainer>
    </div>
  );
}
