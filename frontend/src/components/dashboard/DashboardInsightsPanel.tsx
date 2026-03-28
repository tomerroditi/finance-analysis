import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import Plot from "react-plotly.js";
import { TrendingDown, Calculator, Tag } from "lucide-react";
import { SankeyChart } from "../SankeyChart";
import { Skeleton } from "../common/Skeleton";
import { chartTheme, plotlyConfig } from "../../utils/plotlyLocale";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";
type InsightTab = "income_expenses" | "net_worth" | "cash_flow" | "category";

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

interface DebtPaymentsDataPoint {
  month: string;
  amount: number;
  tags: Record<string, number>;
}

interface ExpensesByCategoryDataPoint {
  month: string;
  categories: Record<string, number>;
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

const formatCompactCurrency = (val: number) => {
  const abs = Math.abs(val || 0);
  if (abs >= 1_000_000) return `₪${(val / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `₪${(val / 1_000).toFixed(0)}K`;
  if (abs >= 1_000) return `₪${(val / 1_000).toFixed(1)}K`;
  return formatCurrency(val);
};


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
  debtPaymentsData: DebtPaymentsDataPoint[] | undefined;
  expensesByCategoryOverTime: ExpensesByCategoryDataPoint[] | undefined;
  excludeRefunds: boolean;
  setExcludeRefunds: (val: boolean) => void;
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
  debtPaymentsData,
  expensesByCategoryOverTime,
  excludeRefunds,
  setExcludeRefunds,
}: DashboardInsightsPanelProps) {
  const { t } = useTranslation();
  const [insightTab, setInsightTab] = useState<InsightTab>("income_expenses");
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");

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
    if (netWorthView === "debt_payments") return [];

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
      },
    ];
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
      {/* Tab bar */}
      <div className="px-6 pt-5 pb-0">
        <div className="flex bg-[var(--surface-light)] p-1 rounded-xl gap-1">
          {([
            { key: "income_expenses" as const, label: `⚖️ ${t("dashboard.incomeAndExpenses")}` },
            { key: "net_worth" as const, label: `📈 ${t("dashboard.netWorth")}` },
            { key: "cash_flow" as const, label: `🌊 ${t("dashboard.cashFlow")}` },
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
        {/* Net Worth Over Time */}
        {insightTab === "net_worth" && (
          <div className="flex flex-col flex-1 min-h-0">
            {netWorthData && netWorthData.length > 0 ? (
              <>
                {/* Net Worth Change KPIs + View Buttons */}
                <div className="flex items-center gap-3 mb-3">
                  {(() => {
                    const latest = netWorthData[netWorthData.length - 1];
                    const findMonthsAgo = (n: number) => {
                      const d = new Date();
                      d.setMonth(d.getMonth() - n);
                      const target = d.toISOString().slice(0, 7);
                      return [...netWorthData].reverse().find((d) => d.month <= target) ?? netWorthData[0];
                    };
                    const periods = [
                      { label: t("dashboard.change5Y"), months: 60 },
                      { label: t("dashboard.change3Y"), months: 36 },
                      { label: t("dashboard.change1Y"), months: 12 },
                      { label: t("dashboard.change6M"), months: 6 },
                      { label: t("dashboard.change1M"), months: 1 },
                    ];
                    return periods.map(({ label, months }) => {
                      const past = findMonthsAgo(months);
                      const delta = latest.net_worth - past.net_worth;
                      const pct = past.net_worth !== 0 ? (delta / Math.abs(past.net_worth)) * 100 : null;
                      const isPositive = delta >= 0;
                      return (
                        <div key={label} className="bg-[var(--surface-light)] rounded-lg px-2.5 py-1.5 text-center shrink-0 whitespace-nowrap" title={`${isPositive ? "+" : ""}${formatCurrency(delta)}`}>
                          <p className="text-[var(--text-muted)] text-[9px] leading-tight">{label}</p>
                          <p dir="ltr" className={`text-xs font-bold leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                            {isPositive ? "+" : ""}{formatCompactCurrency(delta)}
                          </p>
                          {pct !== null && (
                            <p className={`text-[9px] leading-tight ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                              {isPositive ? "+" : ""}{pct.toFixed(1)}%
                            </p>
                          )}
                        </div>
                      );
                    });
                  })()}
                  <div className="ms-auto flex bg-[var(--surface-light)] p-1 rounded-xl">
                    {(
                      [
                        { key: "all", label: t("dashboard.all") },
                        { key: "bank_balance", label: t("dashboard.bankBalance") },
                        { key: "investments", label: t("dashboard.investmentValue") },
                        { key: "net_worth", label: t("dashboard.netWorth") },
                        { key: "debt_payments", label: t("dashboard.debtPayments") },
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
                  {netWorthView === "debt_payments" ? (
                    debtPaymentsData && debtPaymentsData.length > 0 ? (() => {
                      const allTags = Array.from(
                        new Set(debtPaymentsData.flatMap((d) => Object.keys(d.tags))),
                      ).sort();
                      const colors = [
                        "#f43f5e", "#3b82f6", "#f59e0b", "#8b5cf6",
                        "#06b6d4", "#ec4899", "#10b981", "#f97316",
                      ];
                      return (
                        <Plot
                          data={allTags.map((tag, i) => ({
                            x: debtPaymentsData.map((d) => d.month),
                            y: debtPaymentsData.reduce((acc: number[], d) => {
                              acc.push((acc.length > 0 ? acc[acc.length - 1] : 0) + (d.tags[tag] || 0));
                              return acc;
                            }, []),
                            type: "scatter" as const,
                            mode: "lines+markers" as const,
                            line: { color: colors[i % colors.length], width: 2 },
                            marker: { size: 5, color: colors[i % colors.length] },
                            name: tag,
                            stackgroup: "debt",
                          }))}
                          layout={{
                            ...chartTheme,
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
                      );
                    })() : (
                      <p className="text-[var(--text-muted)]">{t("dashboard.noData")}</p>
                    )
                  ) : (
                    <Plot
                      data={getNetWorthTraces()}
                      layout={{
                        ...chartTheme,
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
                  )}
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
            {/* KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-3">
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

            {/* Sub-tabs + Filter Toggles */}
            <div className="flex items-center justify-between mb-3">
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
              <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
                {([
                  { key: "overview" as const, label: `📊 ${t("dashboard.totals")}` },
                  { key: "by_source" as const, label: `💼 ${t("dashboard.incomeBreakdown")}` },
                  { key: "by_category" as const, label: `🍕 ${t("dashboard.expensesBreakdown")}` },
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
            {incomeView === "overview" && (
              <div className="flex-1 min-h-0 overflow-y-auto">
                <Plot
                  data={[
                    {
                      y: incomeOutcome?.map((d) => d.month) || [],
                      x: incomeOutcome?.map((d) => d.income) || [],
                      name: t("dashboard.income"),
                      type: "bar",
                      orientation: "h",
                      marker: { color: "#059669" },
                    },
                    {
                      y: incomeOutcome?.map((d) => d.month) || [],
                      x: incomeOutcome?.map((d) => Math.abs(d.expenses)) || [],
                      name: t("dashboard.expenses"),
                      type: "bar",
                      orientation: "h",
                      marker: {
                        color: incomeOutcome?.map((d) =>
                          d.expenses >= 0 ? "#f43f5e" : "#fda4af"
                        ) || "#f43f5e",
                      },
                    },
                  ]}
                  layout={{
                    ...chartTheme,
                    barmode: "group",
                    autosize: true,
                    height: Math.max(400, (incomeOutcome?.length ?? 0) * 25),
                    legend: {
                      orientation: "h",
                      y: -0.15,
                      x: 0.5,
                      xanchor: "center",
                    },
                    yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  " },
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
                  const colors = [
                    "#10b981", "#3b82f6", "#f59e0b", "#8b5cf6",
                    "#06b6d4", "#ec4899", "#14b8a6", "#f97316",
                  ];
                  const maxStack = Math.max(...incomeBySourceData.map((d) => Object.values(d.sources).reduce((s, v) => s + v, 0)));
                  return (
                    <Plot
                      data={allSources.map((source, i) => ({
                        y: incomeBySourceData.map((d) => d.month),
                        x: incomeBySourceData.map(
                          (d) => d.sources[source] || 0,
                        ),
                        name: source,
                        type: "bar" as const,
                        orientation: "h" as const,
                        marker: { color: colors[i % colors.length], line: { width: 0 } },
                        hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                      }))}
                      layout={{
                        ...chartTheme,
                        barmode: "stack",
                        autosize: true,
                        height: Math.max(400, incomeBySourceData.length * 25),
                        hovermode: "y unified",
                        hoverlabel: { bgcolor: "#1e293b", bordercolor: "#334155", font: { color: "#e2e8f0" } },
                        xaxis: {
                          range: [0, maxStack * 1.05],
                          fixedrange: true,
                          showspikes: false,
                        },
                        yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                        legend: {
                          orientation: "h",
                          y: -0.15,
                          x: 0.5,
                          xanchor: "center",
                        },
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
                        marker: { color: colors[i % colors.length], line: { width: 0 } },
                        hovertemplate: "%{data.name}: %{x:,.0f}<extra></extra>",
                      }))}
                      layout={{
                        ...chartTheme,
                        barmode: "stack",
                        autosize: true,
                        height: Math.max(400, expensesByCategoryOverTime.length * 25),
                        hovermode: "y unified",
                        hoverlabel: { bgcolor: "#1e293b", bordercolor: "#334155", font: { color: "#e2e8f0" } },
                        xaxis: { range: [0, maxStackTotal * 1.05], fixedrange: true, showspikes: false },
                        yaxis: { automargin: true, type: "category", dtick: 1, ticksuffix: "  ", showspikes: false },
                        legend: {
                          orientation: "h",
                          y: -0.15,
                          x: 0.5,
                          xanchor: "center",
                        },
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
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
