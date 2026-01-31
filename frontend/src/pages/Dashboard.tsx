import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Wallet, PiggyBank } from "lucide-react";
import Plot from "react-plotly.js";
import { format } from "date-fns";
import { analyticsApi } from "../services/api";
import { DateRangePicker, type DateRange } from "../components/DateRangePicker";
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
  const [dateRange, setDateRange] = useState<DateRange>({
    start: null,
    end: null,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["overview", dateRange.start, dateRange.end, isTestMode],
    queryFn: async () => {
      const start = dateRange.start
        ? format(dateRange.start, "yyyy-MM-dd")
        : undefined;
      const end = dateRange.end
        ? format(dateRange.end, "yyyy-MM-dd")
        : undefined;
      const res = await analyticsApi.getOverview(start, end);
      return res.data;
    },
    enabled:
      (dateRange.start === null && dateRange.end === null) ||
      (!!dateRange.start && !!dateRange.end),
  });

  const { data: incomeOutcome, isLoading: ioLoading } = useQuery({
    queryKey: ["income-outcome", dateRange.start, dateRange.end, isTestMode],
    queryFn: async () => {
      const start = dateRange.start
        ? format(dateRange.start, "yyyy-MM-dd")
        : undefined;
      const end = dateRange.end
        ? format(dateRange.end, "yyyy-MM-dd")
        : undefined;
      const res = await analyticsApi.getIncomeOutcome(start, end);
      return res.data;
    },
    enabled:
      (dateRange.start === null && dateRange.end === null) ||
      (!!dateRange.start && !!dateRange.end),
  });

  const { data: categoryData } = useQuery({
    queryKey: [
      "analytics-category",
      dateRange.start,
      dateRange.end,
      isTestMode,
    ],
    queryFn: async () => {
      const start = dateRange.start
        ? format(dateRange.start, "yyyy-MM-dd")
        : undefined;
      const end = dateRange.end
        ? format(dateRange.end, "yyyy-MM-dd")
        : undefined;
      const res = await analyticsApi.getByCategory(start, end);
      return res.data;
    },
    enabled:
      (dateRange.start === null && dateRange.end === null) ||
      (!!dateRange.start && !!dateRange.end),
  });

  const { data: trendData } = useQuery({
    queryKey: ["analytics-trend", dateRange.start, dateRange.end, isTestMode],
    queryFn: async () => {
      const start = dateRange.start
        ? format(dateRange.start, "yyyy-MM-dd")
        : undefined;
      const end = dateRange.end
        ? format(dateRange.end, "yyyy-MM-dd")
        : undefined;
      const res = await analyticsApi.getMonthlyTrend(start, end);
      return res.data;
    },
    enabled:
      (dateRange.start === null && dateRange.end === null) ||
      (!!dateRange.start && !!dateRange.end),
  });

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", dateRange.start, dateRange.end, isTestMode],
    queryFn: async () => {
      const start = dateRange.start
        ? format(dateRange.start, "yyyy-MM-dd")
        : undefined;
      const end = dateRange.end
        ? format(dateRange.end, "yyyy-MM-dd")
        : undefined;
      const res = await analyticsApi.getSankeyData(start, end);
      return res.data;
    },
    // Enable if both are null (All Time) OR if both are set (Specific Range)
    enabled:
      (dateRange.start === null && dateRange.end === null) ||
      (!!dateRange.start && !!dateRange.end),
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
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-[var(--text-muted)] mt-1">
            Overview of your financial data
          </p>
        </div>
        <DateRangePicker value={dateRange} onChange={setDateRange} />
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Income"
          value={
            ioLoading ? "..." : formatCurrency(incomeOutcome?.total_income || 0)
          }
          icon={TrendingUp}
          color="bg-emerald-500/20 text-emerald-400"
        />
        <StatCard
          title="Total Expenses"
          value={
            ioLoading
              ? "..."
              : formatCurrency(incomeOutcome?.total_outcome || 0)
          }
          icon={TrendingDown}
          color="bg-red-500/20 text-red-400"
        />
        <StatCard
          title="Net Balance"
          value={ioLoading ? "..." : formatCurrency(incomeOutcome?.net || 0)}
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Monthly Trend Chart */}
        <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
          <h3 className="text-lg font-bold mb-4">Monthly Income vs Expenses</h3>
          <div className="h-[350px]">
            <Plot
              data={[
                {
                  x: trendData?.map((d: any) => d.month),
                  y: trendData?.map((d: any) => d.salary),
                  name: "Salary",
                  type: "bar",
                  marker: { color: "#059669" },
                },
                {
                  x: trendData?.map((d: any) => d.month),
                  y: trendData?.map((d: any) => d.other_income),
                  name: "Other Income",
                  type: "bar",
                  marker: { color: "#34d399" },
                },
                {
                  x: trendData?.map((d: any) => d.month),
                  y: trendData?.map((d: any) => d.outcome),
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
