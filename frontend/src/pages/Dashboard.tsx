import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Wallet, PiggyBank, Landmark } from "lucide-react";
import Plot from "react-plotly.js";
import { analyticsApi, bankBalancesApi } from "../services/api";
import { SankeyChart } from "../components/SankeyChart";
import { ScrapingWidget } from "../components/dashboard/ScrapingWidget";
import { useTestMode } from "../context/TestModeContext";
import { formatDate } from "../utils/dateFormatting";

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

  const { data: netBalanceData } = useQuery({
    queryKey: ["net-balance-trend", isTestMode],
    queryFn: async () => {
      const res = await analyticsApi.getNetBalanceOverTime();
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
        <StatCard
          title="Net Balance"
          value={overviewLoading ? "..." : formatCurrency(overview?.net_balance_change || 0)}
          icon={Wallet}
          color="bg-blue-500/20 text-blue-400"
        />
        <StatCard
          title="Transactions"
          value={overviewLoading ? "..." : overview?.total_transactions || 0}
          icon={PiggyBank}
          color="bg-purple-500/20 text-purple-400"
        />
      </div>

      {/* Bank Balances */}
      {bankBalances && bankBalances.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-muted)] mb-4">Bank Balances</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              title="Total Bank Balance"
              value={formatCurrency(bankBalances.reduce((sum, b) => sum + b.balance, 0))}
              icon={Landmark}
              color="bg-amber-500/20 text-amber-400"
            />
            {bankBalances.map((b) => (
              <StatCard
                key={`${b.provider}-${b.account_name}`}
                title={b.account_name}
                value={formatCurrency(b.balance)}
                icon={Landmark}
                color="bg-amber-500/20 text-amber-300"
              />
            ))}
          </div>
        </div>
      )}

      {/* Net Worth Over Time */}
      {netWorthData && netWorthData.length > 0 && (
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <h3 className="text-lg font-bold mb-4">Net Worth Over Time</h3>
          <div className="h-[350px]">
            <Plot
              data={[
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
              ]}
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
        <div>
          <ScrapingWidget />
        </div>
      </div>

      {/* Net Balance Over Time Chart */}
      <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
        <h3 className="text-lg font-bold mb-4">Net Balance Over Time</h3>
        <div className="h-[350px]">
          <Plot
            data={
              !netBalanceData || netBalanceData.length === 0
                ? []
                : [
                    {
                      x: netBalanceData.map((d) => d.month),
                      y: netBalanceData.map((d) => d.net_change),
                      name: "Monthly Net",
                      type: "bar",
                      marker: {
                        color: netBalanceData.map((d) =>
                          d.net_change >= 0 ? "#10b981" : "#ef4444"
                        ),
                      },
                      yaxis: "y",
                    },
                    {
                      x: netBalanceData.map((d) => d.month),
                      y: netBalanceData.map((d) => d.cumulative_balance),
                      name: "Cumulative Balance",
                      type: "scatter",
                      mode: "lines+markers",
                      line: { color: "#3b82f6", width: 3 },
                      marker: { size: 8, color: "#3b82f6" },
                    },
                  ]
            }
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
