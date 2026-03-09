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

/** Plotly config with locale-aware date formatting */
export function plotlyConfig(
  extra?: Partial<Plotly.Config>,
): Partial<Plotly.Config> {
  return {
    displayModeBar: false,
    responsive: true,
    locale: i18n.language,
    locales: { he: heLocale },
    ...extra,
  };
}
