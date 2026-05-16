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
 * Use this constant (or spread `chartTheme.xaxis`/`chartTheme.yaxis`) instead
 * of hard-coding bright `#334155` solids or rolling per-file values.
 */
export const CHART_GRID_COLOR = "rgba(148, 163, 184, 0.1)";
export const CHART_ZEROLINE_COLOR = "rgba(148, 163, 184, 0.18)";

/** Shared Plotly layout theme for dark mode charts */
export const chartTheme: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", family: "Inter, sans-serif" },
  margin: { t: 40, b: 40, l: 40, r: 20 },
  hoverlabel: { bgcolor: "#1e293b", bordercolor: "#334155", font: { color: "#e2e8f0" }, namelength: -1 },
  hovermode: isTouchDevice ? "closest" : "x unified",
  legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center", font: { size: 11 }, itemwidth: 30 },
  xaxis: {
    showspikes: false,
    gridcolor: CHART_GRID_COLOR,
    zerolinecolor: CHART_ZEROLINE_COLOR,
  },
  yaxis: {
    gridcolor: CHART_GRID_COLOR,
    zerolinecolor: CHART_ZEROLINE_COLOR,
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
    ...extra,
  };
}

