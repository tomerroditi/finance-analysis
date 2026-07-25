import type { ReactNode } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { ChartTooltip } from "./ChartTooltip";
import { ChartLegend } from "./ChartLegend";
import { CHART_COLORS, CHART_SURFACE_COLOR, CHART_TEXT_COLOR } from "../../utils/chartStyle";
import { formatCurrency } from "../../utils/numberFormatting";

export interface DonutSlice {
  name: string;
  value: number;
}

interface DonutChartProps {
  data: DonutSlice[];
  /** Slice colours; defaults to the shared palette, cycled. */
  colors?: string[];
  /** Sort slices descending by value before rendering. */
  sorted?: boolean;
  /** Fixed height in px; omit to fill the parent (parent needs a height). */
  height?: number;
  /** Centered overlay in the donut hole (e.g. formatted total). */
  centerLabel?: ReactNode;
  showLegend?: boolean;
  /** Slice labels: none, percent inside the ring, or name+percent outside. */
  labelMode?: "none" | "percent" | "label-percent-outside";
}

interface SliceLabelProps {
  cx?: number;
  cy?: number;
  midAngle?: number;
  innerRadius?: number;
  outerRadius?: number;
  percent?: number;
  name?: string;
}

const RADIAN = Math.PI / 180;

function percentInsideLabel({ cx = 0, cy = 0, midAngle = 0, innerRadius = 0, outerRadius = 0, percent = 0 }: SliceLabelProps) {
  if (percent < 0.04) return null;
  const r = (innerRadius + outerRadius) / 2;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="#f8fafc" fontSize={11} fontWeight={600} textAnchor="middle" dominantBaseline="central">
      {`${Math.round(percent * 100)}%`}
    </text>
  );
}

/** Approximate advance width of one character at ``fontSize={11}``. */
const OUTSIDE_LABEL_CHAR_WIDTH = 6.2;

function outsideLabel({ cx = 0, cy = 0, midAngle = 0, outerRadius = 0, percent = 0, name = "" }: SliceLabelProps) {
  if (percent < 0.02) return null;
  const r = outerRadius + 14;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  const anchorAtStart = x > cx;

  // Trim the label to the space actually left between its anchor and the
  // chart edge. Long track names used to run straight past the SVG bounds,
  // and since the page does not scroll horizontally they were simply
  // clipped — on a 375px viewport the outermost labels were unreadable.
  // `cx` is the pie centre, so `2 * cx` approximates the plot width.
  const available = anchorAtStart ? Math.max(0, 2 * cx - x) : Math.max(0, x);
  const suffix = ` ${Math.round(percent * 100)}%`;
  const maxNameChars =
    Math.floor(available / OUTSIDE_LABEL_CHAR_WIDTH) - suffix.length;

  let label: string;
  if (maxNameChars < 2) {
    label = suffix.trim();
  } else if (name.length > maxNameChars) {
    label = `${name.slice(0, maxNameChars - 1)}…${suffix}`;
  } else {
    label = `${name}${suffix}`;
  }

  return (
    <text
      x={x}
      y={y}
      fill={CHART_TEXT_COLOR}
      fontSize={11}
      textAnchor={anchorAtStart ? "start" : "end"}
      dominantBaseline="central"
    >
      {label}
    </text>
  );
}

/**
 * Shared donut chart — segments separated by thin surface-coloured gaps, an
 * optional centered total in the hole, and a currency+percent tooltip. Covers
 * the income-by-source, portfolio-allocation, debt-allocation, and
 * insurance-allocation donuts with one implementation.
 */
export function DonutChart({
  data,
  colors = CHART_COLORS,
  sorted = false,
  height,
  centerLabel,
  showLegend = false,
  labelMode = "none",
}: DonutChartProps) {
  const slices = sorted ? [...data].sort((a, b) => b.value - a.value) : data;
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  const hasOutsideLabels = labelMode === "label-percent-outside";

  return (
    <div
      className="flex h-full w-full flex-col"
      style={height ? { height } : undefined}
      data-testid="donut-chart"
    >
      {/* The legend renders as a plain row *below* this box (not inside the
          chart), so the pie always fills its own area and the center overlay
          stays centered on the ring no matter how many rows the legend wraps
          into on narrow screens. */}
      <div className="relative min-h-0 w-full flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart margin={hasOutsideLabels ? { top: 16, bottom: 16, left: 16, right: 16 } : undefined}>
            <Pie
              data={slices}
              dataKey="value"
              nameKey="name"
              innerRadius="62%"
              outerRadius={hasOutsideLabels ? "78%" : "92%"}
              stroke={CHART_SURFACE_COLOR}
              strokeWidth={2}
              isAnimationActive={false}
              labelLine={false}
              label={
                labelMode === "percent"
                  ? percentInsideLabel
                  : hasOutsideLabels
                    ? outsideLabel
                    : undefined
              }
            >
              {slices.map((slice, i) => (
                <Cell key={slice.name} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip
              content={
                <ChartTooltip
                  valueFormatter={(value) =>
                    total > 0
                      ? `${formatCurrency(value)} (${Math.round((value / total) * 100)}%)`
                      : formatCurrency(value)
                  }
                />
              }
            />
          </PieChart>
        </ResponsiveContainer>
        {centerLabel !== undefined && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            {centerLabel}
          </div>
        )}
      </div>
      {showLegend && (
        <ChartLegend
          payload={slices.map((slice, i) => ({
            value: slice.name,
            color: colors[i % colors.length],
          }))}
        />
      )}
    </div>
  );
}
