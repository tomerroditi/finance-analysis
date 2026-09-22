import { useRef } from "react";
import { CHART_TEXT_COLOR } from "../../utils/chartStyle";

interface LegendEntry {
  value?: string | number;
  color?: string;
  type?: string;
  dataKey?: string | number;
  payload?: { legendType?: string };
}

interface ChartLegendProps {
  payload?: LegendEntry[];
  /** Text size in px (Plotly-era legends used 10–11). */
  fontSize?: number;
  /** Extra top gap between the plot area and the legend row. */
  gapTop?: number;
  /**
   * Series keys currently hidden. Only meaningful alongside `onToggle` —
   * without it the legend stays the plain, unclickable row it has always been.
   */
  hidden?: ReadonlySet<string>;
  /** Show or hide one series. Passing it makes the legend interactive. */
  onToggle?: (key: string) => void;
  /** Narrow to one series, or back to all of them. Needs `onToggle` too. */
  onIsolate?: (key: string) => void;
}

/** How long a click waits to see whether it is the first half of a double. */
const DOUBLE_CLICK_GRACE_MS = 220;

/**
 * Shared legend content for all Recharts charts, styled like the Plotly-era
 * legends: a centered horizontal row of colour dots with uniformly muted
 * labels (series colour lives in the dot, not the text). Pass to
 * `<Legend content={<ChartLegend />} />`.
 *
 * Given `onToggle`, each entry becomes a button: a click hides or shows that
 * series and a double-click narrows the chart to it alone (double-clicking
 * the one already alone brings the rest back). Hidden series are dimmed
 * rather than dropped, so the way back is where the way out was.
 */
export function ChartLegend({
  payload,
  fontSize = 11,
  gapTop = 6,
  hidden,
  onToggle,
  onIsolate,
}: ChartLegendProps) {
  // A double-click also fires two clicks, so a click holds back long enough to
  // find out which it was. Held in a ref: a pending click must not re-render.
  const pendingClick = useRef<ReturnType<typeof setTimeout> | null>(null);

  const entries = (payload ?? []).filter(
    (e) => e.value !== undefined && e.payload?.legendType !== "none" && e.type !== "none",
  );
  if (entries.length === 0) return null;

  const keyOf = (entry: LegendEntry) =>
    entry.dataKey !== undefined ? String(entry.dataKey) : String(entry.value);

  const handleClick = (key: string) => {
    if (pendingClick.current) return;
    pendingClick.current = setTimeout(() => {
      pendingClick.current = null;
      onToggle?.(key);
    }, DOUBLE_CLICK_GRACE_MS);
  };

  const handleDoubleClick = (key: string) => {
    if (pendingClick.current) {
      clearTimeout(pendingClick.current);
      pendingClick.current = null;
    }
    onIsolate?.(key);
  };

  return (
    <ul
      className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1"
      style={{ paddingTop: gapTop, fontSize, color: CHART_TEXT_COLOR }}
    >
      {entries.map((entry, i) => {
        const key = keyOf(entry);
        const isHidden = hidden?.has(key) ?? false;
        const label = (
          <>
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              // Multi-colour series (per-Cell bars) have no single colour —
              // fall back to a neutral dot instead of an invisible one.
              style={{ backgroundColor: entry.color ?? "#64748b" }}
            />
            {/* Series labels are user data (investment/account names) and can
                be long — cap them so a handful of verbose names can't push the
                legend into eating the plot area. `dir="auto"` keeps the
                ellipsis on the reading-end under RTL; the full text stays in
                `title`. */}
            <span className="max-w-[14rem] truncate" dir="auto">
              {entry.value}
            </span>
          </>
        );

        return (
          <li key={`${entry.value}-${i}`} className="flex items-center">
            {onToggle ? (
              <button
                type="button"
                onClick={() => handleClick(key)}
                onDoubleClick={() => handleDoubleClick(key)}
                aria-pressed={!isHidden}
                title={String(entry.value)}
                className={`flex items-center gap-1.5 whitespace-nowrap cursor-pointer transition-opacity hover:opacity-100 ${
                  isHidden ? "opacity-40" : ""
                }`}
              >
                {label}
              </button>
            ) : (
              <span
                className="flex items-center gap-1.5 whitespace-nowrap"
                title={String(entry.value)}
              >
                {label}
              </span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
