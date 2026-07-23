import { CHART_TEXT_COLOR } from "../../utils/chartStyle";

interface LegendEntry {
  value?: string | number;
  color?: string;
  type?: string;
  payload?: { legendType?: string };
}

interface ChartLegendProps {
  payload?: LegendEntry[];
  /** Text size in px (Plotly-era legends used 10–11). */
  fontSize?: number;
  /** Extra top gap between the plot area and the legend row. */
  gapTop?: number;
}

/**
 * Shared legend content for all Recharts charts, styled like the Plotly-era
 * legends: a centered horizontal row of colour dots with uniformly muted
 * labels (series colour lives in the dot, not the text). Pass to
 * `<Legend content={<ChartLegend />} />`.
 */
export function ChartLegend({ payload, fontSize = 11, gapTop = 6 }: ChartLegendProps) {
  const entries = (payload ?? []).filter(
    (e) => e.value !== undefined && e.payload?.legendType !== "none" && e.type !== "none",
  );
  if (entries.length === 0) return null;

  return (
    <ul
      className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1"
      style={{ paddingTop: gapTop, fontSize, color: CHART_TEXT_COLOR }}
    >
      {entries.map((entry, i) => (
        <li
          key={`${entry.value}-${i}`}
          className="flex items-center gap-1.5 whitespace-nowrap"
          title={String(entry.value)}
        >
          <span
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            // Multi-colour series (per-Cell bars) have no single colour —
            // fall back to a neutral dot instead of an invisible one.
            style={{ backgroundColor: entry.color ?? "#64748b" }}
          />
          {/* Series labels are user data (investment/account names) and can be
              long — cap them so a handful of verbose names can't push the
              legend into eating the plot area. `dir="auto"` keeps the ellipsis
              on the reading-end under RTL; the full text stays in `title`. */}
          <span className="max-w-[14rem] truncate" dir="auto">
            {entry.value}
          </span>
        </li>
      ))}
    </ul>
  );
}
