import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calculator } from "lucide-react";
import Plot from "../common/LazyPlot";
import { analyticsApi } from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";
import { chartTheme, plotlyConfig, isTouchDevice, barMarker, CHART_COLORS } from "../../utils/plotlyLocale";

/** Income & Expenses dashboard card (KPI averages, refund/project filters, Totals/Income/Expenses sub-views). */
export function IncomeExpensesCard() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  const [excludeRefunds, setExcludeRefunds] = useState(false);

  const { data: incomeOutcome } = useQuery({
    queryKey: qk.analytics.incomeExpensesOverTime(includeProjects, excludeRefunds),
    queryFn: async () => (await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludeRefunds)).data,
  });
  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: qk.analytics.expensesByCategoryOverTime(),
    queryFn: async () => (await analyticsApi.getExpensesByCategoryOverTime()).data,
  });
  const { data: incomeBySourceData } = useQuery({
    queryKey: qk.analytics.incomeBySourceOverTime(),
    queryFn: async () => (await analyticsApi.getIncomeBySourceOverTime()).data,
  });
  const { data: monthlyExpenses } = useQuery({
    queryKey: qk.analytics.monthlyExpenses(excludePendingRefunds, includeProjects),
    queryFn: async () => (await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects)).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.incomeAndExpenses")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 md:gap-3 mb-3">
            {(() => {
              const recent3 = incomeOutcome?.slice(-3) || [];
              const recent6 = incomeOutcome?.slice(-6) || [];
              const recent12 = incomeOutcome?.slice(-12) || [];
              const avgIncome3 = recent3.length ? recent3.reduce((s, d) => s + d.income, 0) / recent3.length : 0;
              const avgIncome6 = recent6.length ? recent6.reduce((s, d) => s + d.income, 0) / recent6.length : 0;
              const avgIncome12 = recent12.length ? recent12.reduce((s, d) => s + d.income, 0) / recent12.length : 0;
              return (
                <>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome3Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome3)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome6Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome6)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgIncome12Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(avgIncome12)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses3Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_3_months ?? 0)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses6Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_6_months ?? 0)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 py-2 flex items-center gap-2">
                    <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400"><Calculator size={14} /></div>
                    <div>
                      <p className="text-[var(--text-muted)] text-[10px]">{t("dashboard.avgExpenses12Months")}</p>
                      <p className="text-sm font-bold">{formatCurrency(monthlyExpenses?.avg_12_months ?? 0)}</p>
                    </div>
                  </div>
                </>
              );
            })()}
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 mb-3">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  excludePendingRefunds
                    ? "bg-[var(--primary)]/10 border-[var(--primary)]/20 text-[var(--primary)]"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {excludePendingRefunds
                  ? t("dashboard.pendingRefundsExcluded")
                  : t("dashboard.pendingRefundsIncluded")}
              </button>
              <button
                onClick={() => setExcludeRefunds(!excludeRefunds)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  excludeRefunds
                    ? "bg-cyan-500/10 border-cyan-500/20 text-cyan-400"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {excludeRefunds
                  ? t("dashboard.refundsExcluded")
                  : t("dashboard.refundsIncluded")}
              </button>
              <button
                onClick={() => setIncludeProjects(!includeProjects)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors ${
                  includeProjects
                    ? "bg-indigo-500/10 border-indigo-500/20 text-indigo-400"
                    : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
                }`}
              >
                {includeProjects
                  ? t("dashboard.projectExpensesIncluded")
                  : t("dashboard.projectExpensesExcluded")}
              </button>
            </div>
            <div className="flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
              {([
                { key: "overview" as const, label: t("dashboard.totals") },
                { key: "by_source" as const, label: t("dashboard.incomeBreakdown") },
                { key: "by_category" as const, label: t("dashboard.expensesBreakdown") },
              ]).map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setIncomeView(key)}
                  className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
                    incomeView === key
                      ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                      : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {incomeView === "overview" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              <Plot
                data={[
                  {
                    y: incomeOutcome?.map((d: { month: string }) => d.month) || [],
                    x: incomeOutcome?.map((d: { income: number }) => d.income) || [],
                    name: t("dashboard.income"),
                    type: "bar",
                    orientation: "h",
                    marker: barMarker("#10b981"),
                  },
                  {
                    y: incomeOutcome?.map((d: { month: string }) => d.month) || [],
                    x: incomeOutcome?.map((d: { expenses: number }) => Math.abs(d.expenses)) || [],
                    name: t("dashboard.expenses"),
                    type: "bar",
                    orientation: "h",
                    marker: barMarker(
                      incomeOutcome?.map((d: { expenses: number }) =>
                        d.expenses >= 0 ? "#f43f5e" : "#fda4af"
                      ) || "#f43f5e",
                    ),
                  },
                ]}
                layout={{
                  ...chartTheme,
                  barmode: "group",
                  autosize: true,
                  height: Math.max(400, (incomeOutcome?.length ?? 0) * 25),
                  legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                  xaxis: { ...chartTheme.xaxis },
                  yaxis: { ...chartTheme.yaxis, automargin: true, type: "category", dtick: 1, ticksuffix: "  " },
                  margin: { ...chartTheme.margin, l: 80, r: 20 },
                }}
                style={{ width: "100%", height: "100%" }}
                config={plotlyConfig()}
              />
            </div>
          )}
          {incomeView === "by_source" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {incomeBySourceData && incomeBySourceData.length > 0 ? (() => {
                const allSources = Array.from(
                  new Set(
                    incomeBySourceData.flatMap((d) => Object.keys(d.sources)),
                  ),
                );
                const colors = CHART_COLORS;
                const maxStack = Math.max(...incomeBySourceData.map((d) => Object.values(d.sources).reduce((s, v) => s + v, 0)));
                return (
                  <Plot
                    data={allSources.map((source, i) => ({
                      y: incomeBySourceData.map((d) => d.month),
                      x: incomeBySourceData.map((d) => d.sources[source] || 0),
                      name: source,
                      type: "bar" as const,
                      orientation: "h" as const,
                      marker: barMarker(colors[i % colors.length]),
                      hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                    }))}
                    layout={{
                      ...chartTheme,
                      barmode: "stack",
                      autosize: true,
                      height: Math.max(400, incomeBySourceData.length * 25),
                      hovermode: isTouchDevice ? "closest" : "y unified",
                      xaxis: { ...chartTheme.xaxis, range: [0, maxStack * 1.05], fixedrange: true, showspikes: false },
                      yaxis: { ...chartTheme.yaxis, automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                      legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                      margin: { ...chartTheme.margin, l: 80, r: 20 },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                );
              })() : (
                <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noIncomeSourceData")}</p>
              )}
            </div>
          )}
          {incomeView === "by_category" && (
            <div className="flex-1 min-h-0 overflow-y-auto">
              {expensesByCategoryOverTime && expensesByCategoryOverTime.length > 0 ? (() => {
                const allCategories = Array.from(
                  new Set(
                    expensesByCategoryOverTime.flatMap((d) => Object.keys(d.categories)),
                  ),
                ).sort();
                const colors = [
                  "#f43f5e", "#ef4444", "#f97316", "#f59e0b",
                  "#eab308", "#84cc16", "#22c55e", "#14b8a6",
                  "#06b6d4", "#3b82f6", "#6366f1", "#8b5cf6",
                  "#a855f7", "#d946ef", "#ec4899", "#fb7185",
                ];
                const maxStackTotal = Math.max(
                  ...expensesByCategoryOverTime.map((d) =>
                    Object.values(d.categories).reduce((s, v) => s + v, 0),
                  ),
                );
                return (
                  <Plot
                    data={allCategories.map((cat, i) => ({
                      y: expensesByCategoryOverTime.map((d) => d.month),
                      x: expensesByCategoryOverTime.map((d) => d.categories[cat] || 0),
                      name: cat,
                      type: "bar" as const,
                      orientation: "h" as const,
                      marker: barMarker(colors[i % colors.length]),
                      hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                    }))}
                    layout={{
                      ...chartTheme,
                      barmode: "stack",
                      autosize: true,
                      height: Math.max(400, expensesByCategoryOverTime.length * 25),
                      hovermode: isTouchDevice ? "closest" : "y unified",
                      xaxis: { ...chartTheme.xaxis, range: [0, maxStackTotal * 1.05], fixedrange: true, showspikes: false },
                      yaxis: { ...chartTheme.yaxis, automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                      legend: { orientation: "h", y: -0.15, x: 0.5, xanchor: "center" },
                      margin: { ...chartTheme.margin, l: 80, r: 20 },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                );
              })() : (
                <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
