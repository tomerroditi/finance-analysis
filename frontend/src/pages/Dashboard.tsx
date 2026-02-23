import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, LineChart, Landmark, Calculator } from "lucide-react";
import Plot from "react-plotly.js";
import { analyticsApi, bankBalancesApi, investmentsApi } from "../services/api";
import { SankeyChart } from "../components/SankeyChart";
import { useTestMode } from "../context/TestModeContext";
import { formatDate } from "../utils/dateFormatting";

type NetWorthView = "all" | "bank_balance" | "investments" | "net_worth";

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)]">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[var(--text-muted)] text-sm">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
        </div>
        <div className={`p-3 rounded-lg ${color}`}>
          <Icon size={24} />
        </div>
      </div>
    </div>
  );
}

export function Dashboard() {
  const { isTestMode } = useTestMode();
  const [netWorthView, setNetWorthView] = useState<NetWorthView>("all");

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["overview", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getOverview();
      return res.data;
    },
  });

  const { data: incomeOutcome } = useQuery({
    queryKey: ["income-outcome", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeExpensesOverTime();
      return res.data;
    },
  });

  const { data: categoryData } = useQuery({
    queryKey: ["analytics-category", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getByCategory();
      return res.data;
    },
  });

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getSankeyData();
      return res.data;
    },
  });

  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isTestMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: netWorthData } = useQuery({
    queryKey: ["net-worth-over-time", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getNetWorthOverTime();
      return res.data;
    },
  });

  const { data: incomeBySourceData } = useQuery({
    queryKey: ["income-by-source", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getIncomeBySourceOverTime();
      return res.data;
    },
  });

  const { data: portfolioAnalysis } = useQuery({
    queryKey: ["portfolio-analysis", isTestMode],
    queryFn: () => investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const [excludePendingRefunds, setExcludePendingRefunds] = useState(true);

  const { data: monthlyExpenses } = useQuery({
    queryKey: ["monthly-expenses", excludePendingRefunds, isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getMonthlyExpenses(excludePendingRefunds);
      return res.data;
    },
  });

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(val);

  const chartTheme = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#94a3b8", family: "Inter, sans-serif" },
    margin: { t: 40, b: 40, l: 40, r: 20 },
  };

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
    bank_balance: { label: "Bank Balance", color: "#f59e0b", dataKey: "bank_balance", deltaKey: "bank_balance_delta" },
    investments: { label: "Investments", color: "#6366f1", dataKey: "investment_value", deltaKey: "investment_value_delta" },
    net_worth: { label: "Net Worth", color: "#10b981", dataKey: "net_worth", deltaKey: "net_worth_delta" },
  } as const;

  const getNetWorthTraces = (): Plotly.Data[] => {
    if (!netWorthData || netWorthData.length === 0) return [];

    if (netWorthView === "all") {
      return [
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.bank_balance),
          name: "Bank Balance",
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#f59e0b", width: 2 },
          marker: { size: 4, color: "#f59e0b" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.investment_value),
          name: "Investments",
          type: "scatter",
          mode: "lines+markers",
          line: { color: "#6366f1", width: 2 },
          marker: { size: 4, color: "#6366f1" },
        },
        {
          x: netWorthData.map((d) => d.month),
          y: netWorthData.map((d) => d.net_worth),
          name: "Net Worth",
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
        name: "Monthly Change",
        type: "bar",
        marker: {
          color: netWorthDeltas.map((d) =>
            d[config.deltaKey] >= 0 ? "#10b981" : "#ef4444"
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
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-[var(--text-muted)] mt-1">
          Overview of your financial data
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Income"
          value={
            overviewLoading ? "..." : formatCurrency(overview?.total_income || 0)
          }
          icon={TrendingUp}
          color="bg-emerald-500/20 text-emerald-400"
        />
        <StatCard
          title="Total Expenses"
          value={
            overviewLoading
              ? "..."
              : formatCurrency(overview?.total_expenses || 0)
          }
          icon={TrendingDown}
          color="bg-red-500/20 text-red-400"
        />
        <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[var(--text-muted)] text-sm">Total Bank Balance</p>
              <p className="text-2xl font-bold mt-1">
                {formatCurrency(bankBalances?.reduce((sum, b) => sum + b.balance, 0) ?? 0)}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-amber-500/20 text-amber-400">
              <Landmark size={24} />
            </div>
          </div>
          {bankBalances && bankBalances.length > 1 && (
            <div className="mt-3 pt-3 border-t border-[var(--surface-light)] space-y-1.5">
              {bankBalances.map((b) => (
                <div key={`${b.provider}-${b.account_name}`} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--text-muted)]">{b.account_name}</span>
                  <span className="font-medium">{formatCurrency(b.balance)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[var(--text-muted)] text-sm">Total Investments</p>
              <p className="text-2xl font-bold mt-1">
                {overviewLoading ? "..." : formatCurrency(overview?.total_investments || 0)}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-purple-500/20 text-purple-400">
              <LineChart size={24} />
            </div>
          </div>
          {portfolioAnalysis?.allocation && portfolioAnalysis.allocation.length > 1 && (
            <div className="mt-3 pt-3 border-t border-[var(--surface-light)] space-y-1.5">
              {portfolioAnalysis.allocation.map((inv: any) => (
                <div key={inv.name} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--text-muted)]">{inv.name}</span>
                  <span className="font-medium">{formatCurrency(inv.balance)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Monthly Expenses Section */}
      {monthlyExpenses && monthlyExpenses.months.length > 0 && (
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold">Monthly Expenses</h3>
            <button
              onClick={() => setExcludePendingRefunds(!excludePendingRefunds)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                excludePendingRefunds
                  ? "bg-[var(--primary)]/10 border-[var(--primary)]/20 text-[var(--primary)]"
                  : "bg-[var(--surface-light)] border-[var(--surface-light)] text-[var(--text-muted)]"
              }`}
            >
              {excludePendingRefunds
                ? "Pending Refunds Excluded"
                : "Pending Refunds Included"}
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400">
                <Calculator size={18} />
              </div>
              <div>
                <p className="text-[var(--text-muted)] text-xs">Avg 3 Months</p>
                <p className="text-lg font-bold">{formatCurrency(monthlyExpenses.avg_3_months)}</p>
              </div>
            </div>
            <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-orange-500/20 text-orange-400">
                <Calculator size={18} />
              </div>
              <div>
                <p className="text-[var(--text-muted)] text-xs">Avg 6 Months</p>
                <p className="text-lg font-bold">{formatCurrency(monthlyExpenses.avg_6_months)}</p>
              </div>
            </div>
            <div className="bg-[var(--surface-light)] rounded-xl px-4 py-3 flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400">
                <Calculator size={18} />
              </div>
              <div>
                <p className="text-[var(--text-muted)] text-xs">Avg 12 Months</p>
                <p className="text-lg font-bold">{formatCurrency(monthlyExpenses.avg_12_months)}</p>
              </div>
            </div>
          </div>
          <div className="h-[350px]">
            <Plot
              data={[
                {
                  x: monthlyExpenses.months.map((d) => d.month),
                  y: monthlyExpenses.months.map((d) => d.expenses),
                  type: "bar",
                  marker: { color: "#f43f5e" },
                  name: "Expenses",
                },
              ]}
              layout={{
                ...chartTheme,
                autosize: true,
                height: 350,
                yaxis: {
                  title: {
                    text: "Amount (ILS)",
                    font: { color: "#94a3b8" },
                  },
                  tickfont: { color: "#94a3b8" },
                },
              }}
              style={{ width: "100%", height: "100%" }}
              config={{ displayModeBar: false, responsive: true }}
            />
          </div>
        </div>
      )}

      {/* Net Worth Over Time */}
      {netWorthData && netWorthData.length > 0 && (
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold">Net Worth Over Time</h3>
            <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
              {([
                { key: "all", label: "All" },
                { key: "bank_balance", label: "Bank Balance" },
                { key: "investments", label: "Investments" },
                { key: "net_worth", label: "Net Worth" },
              ] as const).map(({ key, label }) => (
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
          <div className="h-[350px]">
            <Plot
              data={getNetWorthTraces()}
              layout={{
                ...chartTheme,
                autosize: true,
                height: 350,
                yaxis: {
                  title: { text: "Amount (ILS)", font: { color: "#94a3b8" } },
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
              config={{ displayModeBar: false, responsive: true }}
            />
          </div>
        </div>
      )}

      {/* Actions & Status Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          {/* Sankey Flow Diagram */}
          <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden h-full">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold">Cash Flow</h3>
              {sankeyLoading && (
                <span className="text-sm text-[var(--text-muted)]">
                  Loading...
                </span>
              )}
            </div>
            <div className="h-[500px]">
              <SankeyChart data={sankeyData} height={500} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Monthly Trend Chart */}
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <h3 className="text-lg font-bold mb-4">Monthly Income vs Expenses</h3>
          <div className="h-[350px]">
            <Plot
              data={[
                {
                  x: incomeOutcome?.map((d: any) => d.month) || [],
                  y: incomeOutcome?.map((d: any) => d.income) || [],
                  name: "Income",
                  type: "bar",
                  marker: { color: "#059669" },
                },
                {
                  x: incomeOutcome?.map((d: any) => d.month) || [],
                  y: incomeOutcome?.map((d: any) => d.expenses) || [],
                  name: "Expenses",
                  type: "bar",
                  marker: { color: "#f43f5e" },
                },
              ]}
              layout={{
                ...chartTheme,
                barmode: "group",
                autosize: true,
                height: 350,
              }}
              style={{ width: "100%", height: "100%" }}
              config={{ displayModeBar: false, responsive: true }}
            />
          </div>
        </div>

        {/* Income Breakdown by Source */}
        {incomeBySourceData && incomeBySourceData.length > 0 && (() => {
          // Collect all unique source labels across all months
          const allSources = Array.from(
            new Set(incomeBySourceData.flatMap((d) => Object.keys(d.sources)))
          );

          // Green-toned palette for income sources
          const colors = [
            "#059669", "#10b981", "#34d399", "#6ee7b7",
            "#a7f3d0", "#047857", "#065f46", "#064e3b",
          ];

          return (
            <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
              <h3 className="text-lg font-bold mb-4">Income by Source</h3>
              <div className="h-[350px]">
                <Plot
                  data={allSources.map((source, i) => ({
                    x: incomeBySourceData.map((d) => d.month),
                    y: incomeBySourceData.map((d) => d.sources[source] || 0),
                    name: source,
                    type: "bar" as const,
                    marker: { color: colors[i % colors.length] },
                  }))}
                  layout={{
                    ...chartTheme,
                    barmode: "stack",
                    autosize: true,
                    height: 350,
                    yaxis: {
                      title: { text: "Amount (ILS)", font: { color: "#94a3b8" } },
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
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </div>
          );
        })()}

        {/* Category Breakdown Charts */}
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <h3 className="text-lg font-bold mb-4">Category Breakdown</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 h-[350px]">
            {/* Expenses Chart */}
            <div className="relative">
              <p className="text-sm font-bold text-center text-red-400 mb-2 uppercase tracking-wider">
                Expenses
              </p>
              <div className="h-full">
                <Plot
                  data={[
                    {
                      values:
                        categoryData?.expenses?.map((d: any) => d.amount) || [],
                      labels:
                        categoryData?.expenses?.map((d: any) => d.category) ||
                        [],
                      type: "pie",
                      hole: 0.4,
                      marker: {
                        colors: [
                          "#ef4444",
                          "#f87171",
                          "#fca5a5",
                          "#fecaca",
                          "#fee2e2",
                        ],
                      },
                      textinfo: "label+percent",
                      hoverinfo: "label+value+percent",
                    },
                  ]}
                  layout={{
                    ...chartTheme,
                    autosize: true,
                    showlegend: false,
                    margin: { t: 0, b: 0, l: 0, r: 0 },
                  }}
                  style={{ width: "95%", height: "95%" }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </div>

            {/* Refunds Chart */}
            <div className="relative">
              <p className="text-sm font-bold text-center text-emerald-400 mb-2 uppercase tracking-wider">
                Refunds
              </p>
              <div className="h-full">
                <Plot
                  data={[
                    {
                      values:
                        categoryData?.refunds?.map((d: any) => d.amount) || [],
                      labels:
                        categoryData?.refunds?.map((d: any) => d.category) ||
                        [],
                      type: "pie",
                      hole: 0.4,
                      marker: {
                        colors: [
                          "#10b981",
                          "#34d399",
                          "#6ee7b7",
                          "#a7f3d0",
                          "#d1fae5",
                        ],
                      },
                      textinfo: "label+percent",
                      hoverinfo: "label+value+percent",
                    },
                  ]}
                  layout={{
                    ...chartTheme,
                    autosize: true,
                    showlegend: false,
                    margin: { t: 0, b: 0, l: 0, r: 0 },
                  }}
                  style={{ width: "95%", height: "95%" }}
                  config={{ displayModeBar: false, responsive: true }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Latest Data Info */}
      <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)] flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold mb-1">Data Status</h2>
          <p className="text-[var(--text-muted)] text-sm">
            Latest transaction date:{" "}
            {overview?.latest_data_date
              ? formatDate(overview.latest_data_date)
              : "No data available"}
          </p>
        </div>
        <div className="text-[var(--primary)] font-bold text-xs uppercase tracking-widest px-3 py-1 bg-[var(--primary)]/10 rounded-full border border-[var(--primary)]/20">
          Live Updates Active
        </div>
      </div>
    </div>
  );
}
