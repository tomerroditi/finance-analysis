import { hexToRgba } from "../../utils/chartStyle";

/**
 * Soft vertical gradient for an area chart fill — a tint near the line fading
 * to transparent at the baseline. Render inside the chart and reference via
 * `fill={`url(#${id})`}` on the `<Area>`:
 *
 * ```tsx
 * <AreaChart data={data}>
 *   <AreaGradientDef id="cashflow" color={CHART_COLORS[0]} />
 *   <Area dataKey="balance" stroke={CHART_COLORS[0]} fill="url(#cashflow)" />
 * </AreaChart>
 * ```
 *
 * Use only on single-series charts — stacking gradient fills from multiple
 * overlapping lines looks muddy. For multi-line charts keep plain lines.
 */
export function AreaGradientDef({
  id,
  color,
  topOpacity = 0.35,
}: {
  id: string;
  color: string;
  topOpacity?: number;
}) {
  return (
    <defs>
      <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={hexToRgba(color, topOpacity)} />
        <stop offset="100%" stopColor={hexToRgba(color, 0)} />
      </linearGradient>
    </defs>
  );
}
