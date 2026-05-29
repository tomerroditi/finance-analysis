import i18n from "../i18n";

const heLocale = {
  moduleType: "locale" as const,
  name: "he",
  dictionary: {},
  format: {
    days: ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"],
    shortDays: ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "שבת"],
    months: [
      "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
      "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
    ],
    shortMonths: [
      "ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני",
      "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳",
    ],
    date: "%d/%m/%Y",
  },
};

export const isTouchDevice =
  typeof window !== "undefined" &&
  (navigator.maxTouchPoints > 0 || "ontouchstart" in window);

/**
 * Default grid color for chart axes — slate-400 @ 10% opacity.
 * Subtle enough to disappear behind data, visible enough to give scale.
 *
 * NOTE: the soft-gradient chart theme below intentionally hides gridlines for
 * a cleaner, app-native look. These constants are kept for the rare chart that
 * genuinely needs a faint reference grid (spread `gridcolor: CHART_GRID_COLOR`
 * onto a single axis) — don't reach for them by default.
 */
export const CHART_GRID_COLOR = "rgba(148, 163, 184, 0.1)";
export const CHART_ZEROLINE_COLOR = "rgba(148, 163, 184, 0.18)";

/**
 * Soft, modern categorical palette (fintech aesthetic). Use this everywhere a
 * chart needs to cycle colours instead of rolling a per-file rainbow array, so
 * the whole dashboard stays visually consistent.
 */
export const CHART_COLORS = [
  "#3b82f6", // blue (primary)
  "#10b981", // emerald
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
  "#84cc16", // lime
];

/** Surface colour used to separate donut/pie segments (matches --surface). */
export const CHART_SURFACE_COLOR = "#1e293b";

/** Default corner radius (px) for bars — gives the soft rounded-bar look. */
export const BAR_CORNER_RADIUS = 6;

/** Convert a `#rrggbb` hex string to an `rgba(...)` string at the given alpha. */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Soft vertical gradient area fill for a single-series trend/area trace —
 * transparent at the baseline fading up to a tint near the line. Spread the
 * result into a `scatter` trace:
 *
 * ```ts
 * { x, y, type: "scatter", mode: "lines", line: { color, width: 3, shape: "spline" },
 *   ...gradientFill(color) }
 * ```
 *
 * Use only on single-series charts — stacking gradient fills from multiple
 * overlapping lines looks muddy. For multi-line charts keep plain lines.
 */
export function gradientFill(
  color: string,
  topOpacity = 0.35,
): { fill: "tozeroy"; fillgradient: Record<string, unknown> } {
  // Return type is deliberately narrow (only `fill` + `fillgradient`, no `type`
  // discriminant) so spreading it into a scatter trace literal doesn't widen the
  // trace's `type` union and break Plotly's discriminated-union narrowing.
  // `fillgradient` is valid in plotly.js 3.x but missing from the bundled types,
  // so it rides along as an excess (spread-exempt) property.
  return {
    fill: "tozeroy",
    fillgradient: {
      type: "vertical",
      colorscale: [
        [0, hexToRgba(color, 0)],
        [1, hexToRgba(color, topOpacity)],
      ],
    },
  };
}

/**
 * Rounded, borderless bar marker in the soft style. Pass a single colour or a
 * per-bar colour array; `extra` merges/overrides (e.g. `{ opacity: 0.7 }`).
 */
export function barMarker(
  color: string | string[],
  extra?: Record<string, unknown>,
): Partial<Plotly.PlotMarker> {
  return {
    color,
    cornerradius: BAR_CORNER_RADIUS,
    line: { width: 0 },
    ...extra,
  } as unknown as Partial<Plotly.PlotMarker>;
}

/**
 * Donut/pie marker defaults: segments separated by thin surface-coloured gaps
 * so a dark-on-dark donut reads cleanly. Pass the slice colours (defaults to
 * the shared palette); `extra` overrides.
 */
export function donutMarker(
  colors: string[] = CHART_COLORS,
  extra?: Record<string, unknown>,
): Partial<Plotly.PlotMarker> {
  return {
    colors,
    line: { color: CHART_SURFACE_COLOR, width: 2 },
    ...extra,
  } as unknown as Partial<Plotly.PlotMarker>;
}

/**
 * Shared Plotly layout theme — "soft gradient" dark style.
 *
 * Deliberately strips chart chrome (gridlines, zerolines, axis lines, tick
 * marks) so charts read as product UI rather than technical plots. Tick
 * *labels* are kept (light) for readability; pair line charts with
 * `gradientFill()` and bars with `barMarker()` for the full look.
 */
export const chartTheme: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", family: "Inter, sans-serif", size: 12 },
  colorway: CHART_COLORS,
  margin: { t: 24, b: 36, l: 48, r: 16 },
  hoverlabel: {
    bgcolor: "#1e293b",
    bordercolor: "rgba(148, 163, 184, 0.2)",
    font: { color: "#e2e8f0" },
    namelength: -1,
  },
  hovermode: isTouchDevice ? "closest" : "x unified",
  // On touch devices Plotly's default `dragmode: "zoom"` hijacks a single-finger
  // gesture to draw a zoom box, so dragging over a chart zooms it instead of
  // scrolling the page. Disabling drag lets the touch fall through to page
  // scroll; tapping still shows the hover tooltip. Desktop keeps drag-to-zoom.
  dragmode: isTouchDevice ? false : "zoom",
  legend: { orientation: "h", y: -0.18, x: 0.5, xanchor: "center", font: { size: 11 }, itemwidth: 30 },
  xaxis: {
    showspikes: false,
    showgrid: false,
    zeroline: false,
    showline: false,
    ticks: "",
    automargin: true,
    tickfont: { size: 11, color: "#64748b" },
  },
  yaxis: {
    showgrid: false,
    zeroline: false,
    showline: false,
    ticks: "",
    automargin: true,
    tickfont: { size: 11, color: "#64748b" },
  },
};

/** Plotly config with locale-aware date formatting */
export function plotlyConfig(
  extra?: Partial<Plotly.Config>,
): Partial<Plotly.Config> {
  return {
    displayModeBar: false,
    responsive: true,
    locale: i18n.language,
    locales: { he: heLocale },
    doubleClick: "reset+autosize",
    // Keep pinch / wheel from zooming the chart instead of scrolling the page.
    scrollZoom: false,
    ...extra,
  };
}

