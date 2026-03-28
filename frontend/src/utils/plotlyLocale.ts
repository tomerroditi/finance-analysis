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

/** Shared Plotly layout theme for dark mode charts */
export const chartTheme: Partial<Plotly.Layout> = {
  paper_bgcolor: "rgba(0,0,0,0)",
  plot_bgcolor: "rgba(0,0,0,0)",
  font: { color: "#94a3b8", family: "Inter, sans-serif" },
  margin: { t: 40, b: 40, l: 40, r: 20 },
  hoverlabel: { bgcolor: "#1e293b", bordercolor: "#334155", font: { color: "#e2e8f0" }, namelength: -1 },
  hovermode: isTouchDevice ? "closest" : "x unified",
  xaxis: { showspikes: false },
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

