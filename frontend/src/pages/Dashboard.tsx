import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  TrendingDown,
  Calculator,
  Tag,
} from "lucide-react";
import Plot from "react-plotly.js";
import {
  analyticsApi,
  cashBalancesApi,
  bankBalancesApi,
  investmentsApi,
  transactionsApi,
  taggingApi,
  type BankBalance,
} from "../services/api";
import { BudgetSpendingGauge } from "../components/dashboard/BudgetSection";
import { RecentTransactionsFeed } from "../components/dashboard/RecentTransactionsSection";
import { SankeyChart } from "../components/SankeyChart";
import { Skeleton } from "../components/common/Skeleton";
import { useDemoMode } from "../context/DemoModeContext";
import { useTranslation } from "react-i18next";
import { formatCurrency, formatCompactCurrency } from "../utils/numberFormatting";
import { chartTheme, plotlyConfig, isTouchDevice } from "../utils/plotlyLocale";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth" | "debt_payments";


/* ------------------------------------------------------------------ */
/*  Helper sub-components (extracted to avoid creating during render)  */
/* ------------------------------------------------------------------ */

function MomBadge({ mom }: { mom: { delta: number; percent: number | null } | null }) {
  if (!mom) return null;
  const { delta, percent } = mom;
  const color = delta >= 0 ? "text-emerald-400" : "text-rose-400";
  const sign = delta >= 0 ? "+" : "";
  return (
    <span dir="ltr" className={`text-[10px] font-semibold ${color}`}>
      {sign}{formatCompactCurrency(delta)} {percent !== null && `(${sign}${percent.toFixed(1)}%)`}
    </span>
  );
}

function BreakdownList({ items }: { items: { name: string; amount: number }[] }) {
  return (
    <div className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1">
      {items.map((item) => (
        <div key={item.name} className="flex justify-between text-xs">
          <span className="text-[var(--text-muted)] truncate me-2">{item.name}</span>
          <span className="tabular-nums font-medium shrink-0">{formatCurrency(item.amount)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section 1 — Financial Health Header                               */
/* ------------------------------------------------------------------ */

function FinancialHealthHeader({
  netWorthData,
  cashBalances,
  bankBalances,
  portfolioAllocation,
  isLoading,
}: {
  netWorthData:
    | { month: string; bank_balance: number; investment_value: number; cash: number; net_worth: number }[]
    | undefined;
  cashBalances: { account_name: string; balance: number }[] | undefined;
  bankBalances: BankBalance[] | undefined;
  portfolioAllocation: { name: string; balance: number }[] | undefined;
  isLoading: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const latestNetWorth = netWorthData?.length ? netWorthData[netWorthData.length - 1] : null;
  const previousNetWorth =
    netWorthData && netWorthData.length >= 2 ? netWorthData[netWorthData.length - 2] : null;

  const calcMom = (current: number | undefined, previous: number | undefined) => {
    if (current == null || previous == null) return null;
    const delta = current - previous;
    const percent = previous !== 0 ? (delta / Math.abs(previous)) * 100 : null;
    return { delta, percent };
  };

  const netWorthMom = calcMom(latestNetWorth?.net_worth, previousNetWorth?.net_worth);
  const bankMom = calcMom(latestNetWorth?.bank_balance, previousNetWorth?.bank_balance);
  const investmentMom = calcMom(latestNetWorth?.investment_value, previousNetWorth?.investment_value);
  const cashMom = calcMom(latestNetWorth?.cash, previousNetWorth?.cash);

  const totalCash = cashBalances?.reduce((sum, c) => sum + c.balance, 0) ?? 0;
  const openInvestments = portfolioAllocation?.filter((i) => i.balance > 0);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="card" className="h-16" />
        ))}
      </div>
    );
  }

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 cursor-pointer"
      onClick={() => setExpanded((v) => !v)}
    >
      {/* Net Worth */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">💰 {t("dashboard.netWorth")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.net_worth) : "--"}
        </p>
        <MomBadge mom={netWorthMom} />
      </div>

      {/* Bank Balance */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">🏦 {t("dashboard.bankBalance")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.bank_balance) : "--"}
        </p>
        <MomBadge mom={bankMom} />
        {expanded && bankBalances && bankBalances.length > 0 && (
          <BreakdownList
            items={bankBalances.map((b) => ({ name: b.account_name, amount: b.balance }))}
          />
        )}
      </div>

      {/* Investments */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">📈 {t("dashboard.investmentValue")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">
          {latestNetWorth ? formatCurrency(latestNetWorth.investment_value) : "--"}
        </p>
        <MomBadge mom={investmentMom} />
        {expanded && openInvestments && openInvestments.length > 0 && (
          <BreakdownList
            items={openInvestments.map((i) => ({ name: i.name, amount: i.balance }))}
          />
        )}
      </div>

      {/* Cash */}
      <div className="bg-[var(--surface)] rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 border border-[var(--surface-light)] overflow-hidden">
        <p className="text-[10px] sm:text-xs text-[var(--text-muted)] truncate">💵 {t("dashboard.cashBalance")}</p>
        <p className="text-base sm:text-lg font-bold mt-0.5 truncate">{formatCurrency(totalCash)}</p>
        <MomBadge mom={cashMom} />
        {expanded && cashBalances && cashBalances.length > 0 && (
          <BreakdownList
            items={cashBalances.map((c) => ({ name: c.account_name, amount: c.balance }))}
          />
        )}
      </div>

    </div>
  );
}

/* ================================================================== */
/*  Main Dashboard Component                                          */
/* ================================================================== */

// BudgetSpendingGauge → components/dashboard/BudgetSection.tsx
// RecentTransactionsFeed → components/dashboard/RecentTransactionsSection.tsx

export function Dashboard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");
  const [incomeView, setIncomeView] = useState<"overview" | "by_source" | "by_category">("overview");
  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);
  const [includeProjects, setIncludeProjects] = useState(false);
  const [excludeRefunds, setExcludeRefunds] = useState(false);
  const [insightTab, setInsightTab] = useState<
    "income_expenses" | "net_worth" | "cash_flow" | "category"
  >("income_expenses");

  // ---- Existing queries (kept) ----

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", includeProjects, excludeRefunds, isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeExpensesOverTime(!includeProjects, false, excludeRefunds);
      return res.data;
    },
  });

  const { data: debtPaymentsData } = useQuery({
    queryKey: ["debt-payments", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getDebtPaymentsOverTime();
      return res.data;
    },
  });

  const { data: expensesByCategoryOverTime } = useQuery({
    queryKey: ["expenses-by-category-over-time", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getExpensesByCategoryOverTime();
      return res.data;
    },
  });

  const { data: categoryData } = useQuery({
    queryKey: ["analytics-category", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getByCategory();
      return res.data;
    },
  });

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getSankeyData();
      return res.data;
    },
  });

  const { data: cashBalances } = useQuery({
    queryKey: ["cash-balances", isDemoMode],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
  });

  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isDemoMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: portfolioData } = useQuery({
    queryKey: ["portfolio-analysis", isDemoMode],
    queryFn: () => investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const { data: netWorthData, isLoading: netWorthLoading } = useQuery({
    queryKey: ["net-worth-over-time", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getNetWorthOverTime();
      return res.data;
    },
  });

  const { data: incomeBySourceData } = useQuery({
    queryKey: ["income-by-source", isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeBySourceOverTime();
      return res.data;
    },
  });


  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, includeProjects, isDemoMode],
    queryFn: async () => {
      const res = await analyticsApi.getMonthlyExpenses(excludePendingRefunds, includeProjects);
      return res.data;
    },
  });

  const { data: allTransactions, isLoading: transactionsLoading } = useQuery({
    queryKey: ["all-transactions", isDemoMode],
    queryFn: async () => {
      const res = await transactionsApi.getAll(undefined, false);
      return res.data;
    },
  });

  const { data: categoryIcons } = useQuery({
    queryKey: ["category-icons", isDemoMode],
    queryFn: async () => {
      const res = await taggingApi.getIcons();
      return res.data;
    },
  });

  // ---- Computed values for charts (kept) ----

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
      color: "#ef4444",
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
          line: { color: "#ef4444", width: 3 },
          marker: { size: 5, color: "#ef4444" },
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

  // ================================================================
  //  Render
  // ================================================================

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold">📊 {t("dashboard.title")}</h1>
        <p className="text-[var(--text-muted)] mt-1 text-sm md:text-base">✨ {t("dashboard.subtitle")}</p>
      </div>

      {/* Section 1: Financial Health Header */}
      <FinancialHealthHeader
        netWorthData={netWorthData}
        cashBalances={cashBalances}
        bankBalances={bankBalances}
        portfolioAllocation={portfolioData?.allocation}
        isLoading={netWorthLoading}
      />

      {/* Section 2 & 3: Spending Gauge + Recent Transactions — side by side on large screens */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-8">
        <BudgetSpendingGauge
          categoryIcons={categoryIcons}
        />
        <RecentTransactionsFeed
          transactions={allTransactions}
          categoryIcons={categoryIcons}
          isLoading={transactionsLoading}
        />
      </div>

      {/* Section 4: Tabbed Insights */}
      <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
        {/* Tab bar */}
        <div className="px-3 md:px-6 pt-4 md:pt-5 pb-0">
          <div className="flex bg-[var(--surface-light)] p-1 rounded-xl gap-1 overflow-x-auto scrollbar-auto-hide">
            {([
              { key: "income_expenses" as const, label: `⚖️ ${t("dashboard.incomeAndExpenses")}` },
              { key: "net_worth" as const, label: `📈 ${t("dashboard.netWorth")}` },
              { key: "cash_flow" as const, label: `🌊 ${t("dashboard.cashFlow")}` },
              { key: "category" as const, label: `🍕 ${t("dashboard.categories")}` },
            ]).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setInsightTab(key)}
                className={`sm:flex-1 text-center px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap shrink-0 ${
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
        <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
          {/* Net Worth Over Time */}
          {insightTab === "net_worth" && (
            <div className="flex flex-col flex-1 min-h-0">
              {netWorthData && netWorthData.length > 0 ? (
                <>
                  {/* Net Worth Change KPIs + View Buttons */}
                  <div className="flex flex-wrap items-center gap-2 md:gap-3 mb-3">
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
                    <div className="w-full md:w-auto md:ms-auto flex bg-[var(--surface-light)] p-1 rounded-xl overflow-x-auto scrollbar-auto-hide">
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
                          className={`px-2 md:px-3 py-1.5 rounded-lg text-xs md:text-sm font-bold transition-all whitespace-nowrap ${
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
                              xaxis: { ...chartTheme.xaxis, type: "category" },
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
                          xaxis: { ...chartTheme.xaxis, type: "date" },
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
                  <SankeyChart data={sankeyData} height={560} />
                </div>
              )}
            </div>
          )}

          {/* Income & Expenses */}
          {insightTab === "income_expenses" && (
            <div className="flex flex-col flex-1 min-h-0">
              {/* KPI Cards */}
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

              {/* Sub-tabs + Filter Toggles */}
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
                    { key: "overview" as const, label: `📊 ${t("dashboard.totals")}` },
                    { key: "by_source" as const, label: `💼 ${t("dashboard.incomeBreakdown")}` },
                    { key: "by_category" as const, label: `🍕 ${t("dashboard.expensesBreakdown")}` },
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
                        marker: { color: "#059669" },
                      },
                      {
                        y: incomeOutcome?.map((d: { month: string }) => d.month) || [],
                        x: incomeOutcome?.map((d: { expenses: number }) => Math.abs(d.expenses)) || [],
                        name: t("dashboard.expenses"),
                        type: "bar",
                        orientation: "h",
                        marker: {
                          color: incomeOutcome?.map((d: { expenses: number }) =>
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
                          hovermode: isTouchDevice ? "closest" : "y unified",
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
                          hovermode: isTouchDevice ? "closest" : "y unified",
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
              .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
            const refunds = categoryData?.refunds
              ?.slice()
              .sort((a: { amount: number }, b: { amount: number }) => b.amount - a.amount) || [];
            const totalExpenses = expenses.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
            const totalRefunds = refunds.reduce((s: number, d: { amount: number }) => s + d.amount, 0);
            const topCategory = expenses[0];
            const maxExpense = topCategory?.amount || 1;
            const maxRefund = refunds[0]?.amount || 1;

            return (
              <div className="flex flex-col flex-1 min-h-0 space-y-5">
                {/* Summary strip */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                      <TrendingDown size={18} />
                    </div>
                    <div>
                      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.totalExpenses")}</p>
                      <p className="text-lg font-bold text-rose-400">{formatCurrency(totalExpenses)}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 text-lg">
                      {topCategory ? (categoryIcons?.[topCategory.category] || "📊") : "—"}
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t("dashboard.topCategory")}</p>
                      <p className="text-sm font-bold truncate">{topCategory?.category || "—"}</p>
                    </div>
                  </div>
                  <div className="bg-[var(--surface-light)] rounded-xl px-3 md:px-4 py-2.5 md:py-3 flex items-center gap-3">
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
                  <div className="space-y-1.5 max-h-[350px] overflow-y-auto pr-1">
                    {expenses.map((d: { category: string; amount: number }, i: number) => {
                      const pct = totalExpenses > 0 ? (d.amount / totalExpenses) * 100 : 0;
                      const barWidth = (d.amount / maxExpense) * 100;
                      const icon = categoryIcons?.[d.category] ?? "";
                      return (
                        <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                          <span className="text-base w-6 text-center shrink-0">{icon || (d.category === "Uncategorized" ? "❓" : `${i + 1}.`)}</span>
                          <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                          <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-rose-600 to-rose-400 transition-all duration-500"
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                          <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                          <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
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
                    <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
                      {refunds.map((d: { category: string; amount: number }, i: number) => {
                        const pct = totalRefunds > 0 ? (d.amount / totalRefunds) * 100 : 0;
                        const barWidth = (d.amount / maxRefund) * 100;
                        const icon = categoryIcons?.[d.category] ?? "";
                        return (
                          <div key={d.category} className="group flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-[var(--surface-light)] transition-colors">
                            <span className="text-base w-6 text-center shrink-0">{icon || `${i + 1}.`}</span>
                            <span className="text-xs md:text-sm font-medium w-20 md:w-28 truncate shrink-0" title={d.category}>{d.category}</span>
                            <div className="flex-1 h-5 bg-[var(--surface-light)] rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                                style={{ width: `${barWidth}%` }}
                              />
                            </div>
                            <span className="text-xs md:text-sm font-bold tabular-nums w-16 md:w-24 text-end shrink-0">{formatCurrency(d.amount)}</span>
                            <span className="text-[10px] md:text-xs text-[var(--text-muted)] w-10 md:w-12 text-end shrink-0">{pct.toFixed(1)}%</span>
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

    </div>
  );
}
