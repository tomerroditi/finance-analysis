import { useEffect, useMemo, useRef, useState } from "react";
import { Sankey, Tooltip, Rectangle } from "recharts";
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

// Mirror the Plotly-era layout: room for outside labels on the left (source
// column) and right (destination column).
const MARGIN = { top: 20, bottom: 20, left: 90, right: 140 };

interface SankeyNodeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
  payload?: { name: string; value: number };
}

/**
 * Node renderer: coloured bar + label beside it, Plotly-style — first-column
 * nodes (laid out at the left margin) get their label outside to the left;
 * every other column's label sits to the right of the node.
 */
function SankeyNode({ x = 0, y = 0, width = 0, height = 0, index = 0, payload }: SankeyNodeProps) {
  const isLeftColumn = x <= MARGIN.left + 4;
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
        x={isLeftColumn ? x - 6 : x + width + 6}
        y={y + height / 2}
        textAnchor={isLeftColumn ? "end" : "start"}
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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);

  // Recharts' Sankey needs explicit pixel dimensions (its ResponsiveContainer
  // interplay is unreliable for custom node renderers), so measure the
  // container ourselves and re-render on resize.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setWidth(el.getBoundingClientRect().width);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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
    <div ref={containerRef} style={{ height }} className="w-full" data-testid="sankey-chart">
      {width > 0 && (
        <Sankey
          width={width}
          height={height}
          data={sankeyData}
          node={<SankeyNode />}
          nodePadding={28}
          nodeWidth={20}
          link={{ stroke: "rgba(148, 163, 184, 0.3)" }}
          margin={MARGIN}
        >
          <Tooltip content={<ChartTooltip />} />
        </Sankey>
      )}
    </div>
  );
}
