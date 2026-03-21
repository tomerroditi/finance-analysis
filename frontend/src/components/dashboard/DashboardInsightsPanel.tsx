import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import Plot from "react-plotly.js";
import { TrendingDown, Calculator, Tag } from "lucide-react";
import { SankeyChart } from "../SankeyChart";
import { Skeleton } from "../common/Skeleton";
import { chartTheme, plotlyConfig } from "../../utils/plotlyLocale";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth";
type InsightTab = "monthly_expenses" | "net_worth" | "cash_flow" | "income_expenses" | "category";

interface NetWorthDataPoint {
  month: string;
  bank_balance: number;
  investment_value: number;
  cash: number;
  net_worth: number;
}

interface IncomeOutcomeDataPoint {
  month: string;
  income: number;
  expenses: number;
}

interface MonthlyExpensesData {
  months: { month: string; expenses: number; project_expenses?: number }[];
  avg_3_months: number;
  avg_6_months: number;
  avg_12_months: number;
}

interface CategoryDataItem {
  category: string;
  amount: number;
}

interface CategoryData {
  expenses: CategoryDataItem[];
  refunds: CategoryDataItem[];
}

interface IncomeBySourceDataPoint {
  month: string;
  sources: Record<string, number>;
}

interface SankeyData {
  nodes: number[];
  node_labels: string[];
  links: {
    source: number;
    target: number;
    value: number;
    label: string;
  }[];
}

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(val || 0);


interface DashboardInsightsPanelProps {
  netWorthData: NetWorthDataPoint[] | undefined;
  incomeOutcome: IncomeOutcomeDataPoint[] | undefined;
  monthlyExpenses: MonthlyExpensesData | undefined;
  categoryData: CategoryData | undefined;
  sankeyData: SankeyData | undefined;
  sankeyLoading: boolean;
  incomeBySourceData: IncomeBySourceDataPoint[] | undefined;
  categoryIcons: Record<string, string> | undefined;
  excludePendingRefunds: boolean;
  setExcludePendingRefunds: (val: boolean) => void;
  includeProjects: boolean;
  setIncludeProjects: (val: boolean) => void;
}

export function DashboardInsightsPanel({
  netWorthData,
  incomeOutcome,
  monthlyExpenses,
  categoryData,
  sankeyData,
  sankeyLoading,
  incomeBySourceData,
  categoryIcons,
  excludePendingRefunds,
  setExcludePendingRefunds,
  includeProjects,
  setIncludeProjects,
}: DashboardInsightsPanelProps) {
  const { t } = useTranslation();
  const [insightTab, setInsightTab] = useState<InsightTab>("monthly_expenses");
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");
  const [incomeView, setIncomeView] = useState<"overview" | "by_source">("overview");

  const netWorthDeltas = useMemo(() => {
    if (!netWorthData || netWorthData.length < 2) return null;
    return netWorthData.slice(1).map((d, i) => ({
      month: d.month,
      bank_balance: d.bank_balance,
      investment_value: d.investment_value,
      net_worth: d.net_worth,
      bank_balance_delta: d.bank_balance - netWorthData[i].bank_balance,
      investment_value_delta: d.investment_value - netWorthData[i].investment_value,
      net_worth_delta: d.net_worth - netWorthData[i].net_worth,
    }));
  }, [netWorthData]);

  const seriesConfig = {
    bank_balance: {
      label: t("dashboard.bankBalance"),
      color: "#f59e0b",
      dataKey: "bank_balance" as const,
      deltaKey: "bank_balance_delta" as const,
    },
    investments: {
      label: t("dashboard.investmentValue"),
      color: "#6366f1",
      dataKey: "investment_value" as const,
      deltaKey: "investment_value_delta" as const,
    },
    net_worth: {
      label: t("dashboard.netWorth"),
      color: "#10b981",
      dataKey: "net_worth" as const,
      deltaKey: "net_worth_delta" as const,
    },
  };

  const getNetWorthTraces = (): Plotly.Data[] => {
    if (!netWorthData || netWorthData.length === 0) return [];

    if (netWorthView === "all") {
      return [
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.bank_balance),
          name: t("dashboard.bankBalance"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#f59e0b", width: 2 },
          marker: { size: 4, color: "#f59e0b" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.investment_value),
          name: t("dashboard.investmentValue"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#6366f1", width: 2 },
          marker: { size: 4, color: "#6366f1" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.net_worth),
          name: t("dashboard.netWorth"),
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#10b981", width: 3 },
          marker: { size: 5, color: "#10b981" },
        },
      ];
    }

    if (!netWorthDeltas) return [];
    const config = seriesConfig[netWorthView];

    return [
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.deltaKey]),
        name: t("dashboard.monthlyChange"),
        type: "bar",
        marker: {
          color: netWorthDeltas.map((d) =>
            d[config.deltaKey] >= 0 ? "#10b981" : "#ef4444",
          ),
        },
      },
      {
        x: netWorthDeltas.map((d) => d.month),
        y: netWorthDeltas.map((d) => d[config.dataKey]),
        name: config.label,
        type: "scatter",
        mode: "lines+markers",
        line: { color: config.color, width: 3 },
        marker: { size: 8, color: config.color },
        yaxis: "y2",
      },
    ];
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
      {/* Tab bar */}
      <div className="px-6 pt-5 pb-0">
        <div className="flex bg-[var(--surface-light)] p-1 rounded-xl gap-1">
          {([
            { key: "monthly_expenses" as const, label: `💸 ${t("dashboard.monthlyExpenses")}` },
            { key: "net_worth" as const, label: `📈 ${t("dashboard.netWorth")}` },
            { key: "cash_flow" as const, label: `🌊 ${t("dashboard.cashFlow")}` },
            { key: "income_expenses" as const, label: `⚖️ ${t("dashboard.incomeAndExpenses")}` },
            { key: "category" as const, label: `🍕 ${t("dashboard.categories")}` },
          ]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setInsightTab(key)}
              className={`flex-1 text-center px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
                insightTab === key
                  ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                  : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="px-6 pb-6 pt-4 h-[600px] overflow-y-auto flex flex-col">
        {/* Monthly Expenses */}
        {insightTab === "monthly_expenses" && (
          <div className="flex flex-col flex-1 min-h-0">
            {monthlyExpenses && monthlyExpenses.months.length > 0 ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-4">
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">{t("dashboard.avg3Months")}</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_3_months)}
                      </p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-orange-500/20 text-orange-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">{t("dashboard.avg6Months")}</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_6_months)}
                      </p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
                      <Calculator size={18} />
                    </div>
                    <div>
                      <p className="text-[var(--text-muted)] text-xs">{t("dashboard.avg12Months")}</p>
                      <p className="text-lg font-bold">
                        {formatCurrency(monthlyExpenses.avg_12_months)}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
                    className={`rounded-xl px-4 py-3 text-xs font-medium border transition-colors flex items-center justify-center ${
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
                    onClick={() => setIncludeProjects(!includeProjects)}
                    className={`rounded-xl px-4 py-3 text-xs font-medium border transition-colors flex items-center justify-center ${
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
                <div className="flex-1 min-h-0">
                  <Plot
                    data={[
                      {
                        x: monthlyExpenses.months.map((d) => d.month),
                        y: monthlyExpenses.months.map((d) => d.expenses),
                        type: "bar",
                        marker: { color: "#f43f5e" },
                        name: t("dashboard.expenses"),
                      },
                      ...(includeProjects
                        ? [
                            {
                              x: monthlyExpenses.months.map((d) => d.month),
                              y: monthlyExpenses.months.map((d) => d.project_expenses ?? 0),
                              type: "bar" as const,
                              marker: { color: "#818cf8" },
                              name: t("dashboard.projectExpenses"),
                            },
                          ]
                        : []),
                    ]}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      barmode: includeProjects ? "stack" : undefined,
                      legend: includeProjects
                        ? {
                            orientation: "h" as const,
                            yanchor: "top" as const,
                            y: -0.15,
                            xanchor: "center" as const,
                            x: 0.5,
                            font: { color: "#94a3b8" },
                          }
                        : undefined,
                      yaxis: {
                        title: {
                          text: t("dashboard.amountILS"),
                          font: { color: "#94a3b8" },
                        },
                        tickfont: { color: "#94a3b8" },
                      },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                </div>
              </>
            ) : (
              <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noExpenseData")}</p>
            )}
          </div>
        )}

        {/* Net Worth Over Time */}
        {insightTab === "net_worth" && (
          <div className="flex flex-col flex-1 min-h-0">
            {netWorthData && netWorthData.length > 0 ? (
              <>
                <div className="flex justify-end mb-4">
                  <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                    {(
                      [
                        { key: "all", label: t("dashboard.all") },
                        { key: "bank_balance", label: t("dashboard.bankBalance") },
                        { key: "investments", label: t("dashboard.investmentValue") },
                        { key: "net_worth", label: t("dashboard.netWorth") },
                      ] as const
                    ).map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => setNetWorthView(key)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
                          netWorthView === key
                            ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
                            : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex-1 min-h-0">
                  <Plot
                    data={getNetWorthTraces()}
                    layout={{
                      ...chartTheme,
                      autosize: true,
                      yaxis: {
                        title: {
                          text: netWorthView === "all" ? t("dashboard.amountILS") : t("dashboard.monthlyChange"),
                          font: { color: "#94a3b8" },
                        },
                        tickfont: { color: "#94a3b8" },
                        automargin: true,
                      },
                      ...(netWorthView !== "all" && {
                        yaxis2: {
                          title: {
                            text: seriesConfig[netWorthView].label,
                            font: { color: seriesConfig[netWorthView].color },
                          },
                          tickfont: { color: seriesConfig[netWorthView].color },
                          overlaying: "y" as const,
                          side: "right" as const,
                          showgrid: false,
                          automargin: true,
                        },
                      }),
                      legend: {
                        orientation: "h",
                        y: -0.15,
                        x: 0.5,
                        xanchor: "center",
                      },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                </div>
              </>
            ) : (
              <p className="text-[var(--text-muted)] text-sm">📭 {t("dashboard.noNetWorthData")}</p>
            )}
          </div>
        )}

        {/* Cash Flow (Sankey) */}
        {insightTab === "cash_flow" && (
          <div className="flex flex-col flex-1 min-h-0">
            {sankeyLoading ? (
              <Skeleton variant="chart" className="flex-1" />
            ) : (
              <div className="flex-1 min-h-0">
                {sankeyData && <SankeyChart data={sankeyData} height={560} />}
              </div>
            )}
          </div>
        )}

        {/* Income & Expenses */}
        {insightTab === "income_expenses" && (
          <div className="flex flex-col flex-1 min-h-0">
            <div className="flex justify-end mb-4">
              <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                {([
                  { key: "overview" as const, label: `📊 ${t("dashboard.overview")}` },
                  { key: "by_source" as const, label: `💼 ${t("dashboard.bySource")}` },
                ]).map(({ key, label }) => (
                  <button
                    key={key}
                    onClick={() => setIncomeView(key)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-bold transition-all ${
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
            {incomeView === "overview" ? (
              <div className="flex-1 min-h-0">
                <Plot
                  data={[
                    {
                      x: incomeOutcome?.map((d) => d.month) || [],
                      y: incomeOutcome?.map((d) => d.income) || [],
                      name: t("dashboard.income"),
                      type: "bar",
                      marker: { color: "#059669" },
                    },
                    {
                      x: incomeOutcome?.map((d) => d.month) || [],
                      y: incomeOutcome?.map((d) => d.expenses) || [],
                      name: t("dashboard.expenses"),
                      type: "bar",
                      marker: { color: "#f43f5e" },
                    },
                  ]}
                  layout={{
                    ...chartTheme,
                    barmode: "group",
                    autosize: true,
                    legend: {
                      orientation: "h",
                      y: -0.15,
                      x: 0.5,
                      xanchor: "center",
                    },
                  }}
                  style={{ width: "100%", height: "100%" }}
                  config={plotlyConfig()}
                />
              </div>
            ) : (
              <div className="flex-1 min-h-0">
                {incomeBySourceData && incomeBySourceData.length > 0 ? (() => {
                  const allSources = Array.from(
                    new Set(
                      incomeBySourceData.flatMap((d) => Object.keys(d.sources)),
                    ),
                  );
                  const colors = [
                    "#059669", "#10b981", "#34d399", "#6ee7b7",
                    "#a7f3d0", "#047857", "#065f46", "#064e3b",
                  ];
                  return (
                    <Plot
                      data={allSources.map((source, i) => ({
                        x: incomeBySourceData.map((d) => d.month),
                        y: incomeBySourceData.map(
                          (d) => d.sources[source] || 0,
                        ),
                        name: source,
                        type: "bar" as const,
                        marker: { color: colors[i % colors.length] },
                      }))}
                      layout={{
                        ...chartTheme,
                        barmode: "stack",
                        autosize: true,
                        yaxis: {
                          title: {
                            text: t("dashboard.amountILS"),
                            font: { color: "#94a3b8" },
                          },
                          tickfont: { color: "#94a3b8" },
                        },
                        legend: {
                          orientation: "h",
                          y: -0.15,
                          x: 0.5,
                          xanchor: "center",
                        },
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
          </div>
        )}

        {/* Category Breakdown */}
        {insightTab === "category" && (() => {
          const expenses = categoryData?.expenses
            ?.slice()
            .sort((a, b) => b.amount - a.amount) || [];
          const refunds = categoryData?.refunds
            ?.slice()
            .sort((a, b) => b.amount - a.amount) || [];
          const totalExpenses = expenses.reduce((s, d) => s + d.amount, 0);
          const totalRefunds = refunds.reduce((s, d) => s + d.amount, 0);
          const topCategory = expenses[0];
          const maxExpense = topCategory?.amount || 1;
          const maxRefund = refunds[0]?.amount || 1;

          return (
            <div className="flex flex-col flex-1 min-h-0 space-y-5">
              {/* Summary strip */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                    <TrendingDown size={18} />
                  </div>
                  <div>
                    <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.totalExpenses")}</p>
                    <p className="text-lg font-bold text-rose-400">{formatCurrency(totalExpenses)}</p>
                  </div>
                </div>
                <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 text-lg">
                    {topCategory ? (categoryIcons?.[topCategory.category] || "📊") : "—"}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.topCategory")}</p>
                    <p className="text-sm font-bold truncate">{topCategory?.category || "—"}</p>
                  </div>
                </div>
                <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-blue-500/20 text-blue-400">
                    <Tag size={18} />
                  </div>
                  <div>
                    <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.categories")}</p>
                    <p className="text-lg font-bold">{expenses.length}</p>
                  </div>
                </div>
              </div>

              {/* Expenses bars */}
              <div>
                <p className="text-sm font-bold text-rose-400 uppercase tracking-wider mb-3">{t("dashboard.expenses")}</p>
                <div className="space-y-1.5 max-h-[350px] overflow-y-auto pe-1">
                  {expenses.map((d, i) => {
                    const pct = totalExpenses > 0 ? (d.amount / totalExpenses) * 100 : 0;
                    const barWidth = (d.amount / maxExpense) * 100;
                    const icon = categoryIcons?.[d.category] ?? "";
                    return (
                      <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                        <span className="text-base w-6 text-center shrink-0">{icon || (d.category === "Uncategorized" ? "❓" : `${i + 1}.`)}</span>
                        <span className="text-sm font-medium w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                        <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-rose-600 to-rose-400 transition-all duration-500"
                            style={{ width: `${barWidth}%` }}
                          />
                        </div>
                        <span className="text-sm font-bold tabular-nums w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                        <span className="text-xs text-[var(--text-muted)] w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                      </div>
                    );
                  })}
                  {expenses.length === 0 && (
                    <p className="text-[var(--text-muted)] text-sm py-4 text-center">{t("dashboard.noExpenseData")}</p>
                  )}
                </div>
              </div>

              {/* Refunds bars (conditional) */}
              {refunds.length > 0 && (
                <div>
                  <p className="text-sm font-bold text-emerald-400 uppercase tracking-wider mb-3">{t("dashboard.refunds")}</p>
                  <div className="space-y-1.5 max-h-[200px] overflow-y-auto pe-1">
                    {refunds.map((d, i) => {
                      const pct = totalRefunds > 0 ? (d.amount / totalRefunds) * 100 : 0;
                      const barWidth = (d.amount / maxRefund) * 100;
                      const icon = categoryIcons?.[d.category] ?? "";
                      return (
                        <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                          <span className="text-base w-6 text-center shrink-0">{icon || `${i + 1}.`}</span>
                          <span className="text-sm font-medium w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                          <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <span className="text-sm font-bold tabular-nums w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                          <span className="text-xs text-[var(--text-muted)] w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
