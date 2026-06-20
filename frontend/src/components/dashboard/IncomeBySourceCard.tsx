import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PieChart, ChevronDown, ChevronUp } from "lucide-react";
import Plot from "../common/LazyPlot";
import { analyticsApi } from "../../services/api";
import { Skeleton } from "../common/Skeleton";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatCompactCurrency } from "../../utils/numberFormatting";
import {
  chartTheme,
  plotlyConfig,
  CHART_COLORS,
  CHART_SURFACE_COLOR,
} from "../../utils/plotlyLocale";

type RangePreset = "all" | "year" | "last12m" | "custom";

/** Resolve a preset (and optional custom inputs) into ISO start/end strings. */
function resolveRange(
  preset: RangePreset,
  customStart: string,
  customEnd: string,
): { start?: string; end?: string } {
  if (preset === "all") return {};
  const now = new Date();
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  if (preset === "year") {
    return { start: `${now.getFullYear()}-01-01`, end: iso(now) };
  }
  if (preset === "last12m") {
    const start = new Date(now);
    start.setMonth(start.getMonth() - 12);
    return { start: iso(start), end: iso(now) };
  }
  // custom
  return { start: customStart || undefined, end: customEnd || undefined };
}

export function IncomeBySourceCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [preset, setPreset] = useState<RangePreset>("all");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [tableOpen, setTableOpen] = useState(true);

  const { start, end } = resolveRange(preset, customStart, customEnd);

  const { data, isLoading } = useQuery({
    queryKey: ["income-by-source", start ?? "all", end ?? "all", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeBySource(start, end);
      return res.data;
    },
  });

  const presets: { key: RangePreset; label: string }[] = useMemo(
    () => [
      { key: "all", label: t("dashboard.incomeBySource.range.all") },
      { key: "year", label: t("dashboard.incomeBySource.range.year") },
      { key: "last12m", label: t("dashboard.incomeBySource.range.last12m") },
      { key: "custom", label: t("dashboard.incomeBySource.range.custom") },
    ],
    [t],
  );

  const sources = data?.sources ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      {/* Header */}
      <div className="flex flex-col gap-3 mb-4">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <PieChart size={18} />
          </div>
          <p className="text-sm md:text-base font-bold">
            {t("dashboard.incomeBySource.title")}
          </p>
        </div>
        {/* Range presets */}
        <div className="flex overflow-x-auto scrollbar-auto-hide gap-1 bg-[var(--surface-light)] p-1 rounded-xl">
          {presets.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setPreset(key)}
              className={`shrink-0 whitespace-nowrap px-2 md:px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                preset === key
                  ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Custom range inputs */}
      {preset === "custom" && (
        <div className="flex flex-col sm:flex-row gap-2 mb-4">
          <label className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            {t("dashboard.incomeBySource.from")}
            <input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="bg-[var(--surface-light)] rounded-lg px-2 py-1 text-[var(--text-default)]"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            {t("dashboard.incomeBySource.to")}
            <input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="bg-[var(--surface-light)] rounded-lg px-2 py-1 text-[var(--text-default)]"
            />
          </label>
        </div>
      )}

      {isLoading ? (
        <Skeleton className="h-[240px] w-full rounded-xl" />
      ) : sources.length === 0 ? (
        <p className="text-[var(--text-muted)] text-sm py-8 text-center">
          📭 {t("dashboard.incomeBySource.empty")}
        </p>
      ) : (
        <div className="flex flex-col gap-4">
          {/* Donut */}
          <div className="w-full min-h-[240px]">
            <Plot
              data={[
                {
                  type: "pie",
                  hole: 0.62,
                  labels: sources.map((s) => s.label),
                  values: sources.map((s) => s.amount),
                  sort: false,
                  marker: {
                    colors: sources.map(
                      (_, i) => CHART_COLORS[i % CHART_COLORS.length],
                    ),
                    line: { color: CHART_SURFACE_COLOR, width: 2 },
                  },
                  textinfo: "none",
                  hovertemplate: "%{label}: %{value:,.0f} ₪ (%{percent})<extra></extra>",
                },
              ]}
              layout={{
                ...chartTheme,
                showlegend: false,
                height: 240,
                margin: { l: 10, r: 10, t: 10, b: 10 },
                annotations: [
                  {
                    text: formatCompactCurrency(total),
                    showarrow: false,
                    font: { size: 18, color: "var(--text-default)" },
                  },
                ],
              }}
              useResizeHandler
              style={{ width: "100%", height: "100%" }}
              config={plotlyConfig()}
            />
          </div>

          {/* Collapsible breakdown table */}
          <div className="w-full">
            <button
              type="button"
              onClick={() => setTableOpen((open) => !open)}
              aria-expanded={tableOpen}
              className="flex items-center gap-1 mb-2 text-xs font-bold text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
            >
              {tableOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              {t("dashboard.incomeBySource.breakdown")}
            </button>
            {tableOpen && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[240px] text-sm">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                      <th className="text-start px-2 py-2 font-bold whitespace-nowrap">
                        {t("dashboard.incomeBySource.source")}
                      </th>
                      <th className="text-center px-2 py-2 font-bold whitespace-nowrap">
                        {t("dashboard.incomeBySource.amount")}
                      </th>
                      <th className="text-center px-2 py-2 font-bold whitespace-nowrap">
                        {t("dashboard.incomeBySource.share")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((s, i) => (
                      <tr
                        key={s.label}
                        className="border-b border-[var(--surface-light)]/50"
                      >
                        <td className="text-start px-2 py-2 whitespace-nowrap">
                          <span className="inline-flex items-center gap-2">
                            <span
                              className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                              style={{
                                backgroundColor:
                                  CHART_COLORS[i % CHART_COLORS.length],
                              }}
                            />
                            <span
                              className="block max-w-[96px] truncate"
                              dir="auto"
                            >
                              {s.label}
                            </span>
                          </span>
                        </td>
                        <td className="text-center px-2 py-2 whitespace-nowrap">
                          <span dir="ltr">{formatCurrency(s.amount)}</span>
                        </td>
                        <td className="text-center px-2 py-2 whitespace-nowrap text-[var(--text-muted)]">
                          {(s.share * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                    <tr className="font-bold border-t-2 border-[var(--surface-light)]">
                      <td className="text-start px-2 py-2 whitespace-nowrap">
                        {t("dashboard.incomeBySource.total")}
                      </td>
                      <td className="text-center px-2 py-2 whitespace-nowrap">
                        <span dir="ltr">{formatCurrency(total)}</span>
                      </td>
                      <td className="text-center px-2 py-2 whitespace-nowrap text-[var(--text-muted)]">
                        100.0%
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
