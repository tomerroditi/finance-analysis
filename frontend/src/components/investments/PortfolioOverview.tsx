import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Wallet, DollarSign, Percent } from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { investmentsApi } from "../../services/api";
import { AXIS_DEFAULTS, CHART_COLORS, formatAxisNumber } from "../../utils/chartStyle";
import { ChartTooltip } from "../charts/ChartTooltip";
import { ChartLegend } from "../charts/ChartLegend";
import { DonutChart } from "../charts/DonutChart";
import { formatDate, formatShortDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { useQueryKeys } from "../../hooks/useQueryKeys";

interface AllocationItem {
  id: number;
  name: string;
  balance: number;
  percentage: number;
  profit_loss?: number;
  roi?: number;
}

interface BalancePoint {
  date: string;
  balance: number;
}

interface BalanceSeries {
  name: string;
  data: BalancePoint[];
}

interface PortfolioAnalysis {
  total_value: number;
  total_profit: number;
  portfolio_roi: number;
  allocation: AllocationItem[];
}

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ size: number }>;
  color: string;
}) {
  return (
    <div className="bg-[var(--surface)] rounded-xl p-3 md:p-5 border border-[var(--surface-light)] flex items-center justify-between shadow-sm">
      <div>
        <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
          {title}
        </p>
        <p className="text-xl font-black mt-1 text-white" dir="ltr">{value}</p>
      </div>
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon size={20} />
      </div>
    </div>
  );
}

const formatPercent = (val: number) =>
  `${val >= 0 ? "+" : "-"}${Math.abs(val).toFixed(2)}%`;


interface PortfolioOverviewProps {
  portfolioAnalysis: PortfolioAnalysis;
}

export function PortfolioOverview({ portfolioAnalysis }: PortfolioOverviewProps) {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const [chartIncludeClosed, setChartIncludeClosed] = useState(true);

  const { data: balanceHistory } = useQuery({
    queryKey: qk.investments.balanceHistory(chartIncludeClosed),
    queryFn: () =>
      investmentsApi.getPortfolioBalanceHistory(chartIncludeClosed).then((res) => res.data),
  });

  // Unified rows keyed by date: one key per investment series + "__total",
  // so every line renders on a single shared x-axis.
  const balanceRows = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>();
    const ensure = (date: string) => {
      let row = byDate.get(date);
      if (!row) {
        row = { date };
        byDate.set(date, row);
      }
      return row;
    };
    for (const s of (balanceHistory?.series ?? []) as BalanceSeries[]) {
      for (const p of s.data) ensure(p.date)[s.name] = p.balance;
    }
    for (const p of (balanceHistory?.total ?? []) as BalancePoint[]) {
      ensure(p.date).__total = p.balance;
    }
    return [...byDate.values()].sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    );
  }, [balanceHistory]);

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 md:gap-4">
        <StatCard
          title={t("investments.totalValue")}
          value={formatCurrency(portfolioAnalysis.total_value)}
          icon={Wallet}
          color="bg-blue-500/10 text-blue-400"
        />
        <StatCard
          title={t("investments.totalProfitLoss")}
          value={formatCurrency(portfolioAnalysis.total_profit)}
          icon={DollarSign}
          color={
            portfolioAnalysis.total_profit >= 0
              ? "bg-emerald-500/10 text-emerald-400"
              : "bg-red-500/10 text-red-400"
          }
        />
        <StatCard
          title={t("investments.portfolioRoi")}
          value={formatPercent(portfolioAnalysis.portfolio_roi)}
          icon={Percent}
          color={
            portfolioAnalysis.portfolio_roi >= 0
              ? "bg-emerald-500/10 text-emerald-400"
              : "bg-red-500/10 text-red-400"
          }
        />
      </div>
      {/* Charts: Balance Over Time + Allocation side-by-side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        {/* Balance Over Time Chart */}
        <div className="lg:col-span-2 bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-4">
            <h3 className="text-xs sm:text-sm font-bold uppercase tracking-widest text-[var(--text-muted)]">
              {t("investments.balanceOverTime")}
            </h3>
            <button
              onClick={() => setChartIncludeClosed(!chartIncludeClosed)}
              className={`px-2 md:px-3 py-1.5 rounded-lg text-xs font-bold border transition-all whitespace-nowrap ${chartIncludeClosed ? "bg-[var(--surface-light)] border-[var(--surface-light)] text-white" : "border-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
            >
              {chartIncludeClosed ? t("investments.hideClosed") : t("investments.includeClosed")}
            </button>
          </div>
          <div className="h-[300px]">
            {balanceHistory?.series?.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={balanceRows} margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
                  <XAxis
                    dataKey="date"
                    {...AXIS_DEFAULTS}
                    tickFormatter={(d) => formatShortDate(String(d))}
                  />
                  <YAxis {...AXIS_DEFAULTS} tickFormatter={formatAxisNumber} width={56} />
                  <Tooltip
                    content={<ChartTooltip labelFormatter={(d) => formatDate(String(d))} />}
                  />
                  <Legend content={<ChartLegend fontSize={10} />} />
                  {(balanceHistory.series as BalanceSeries[]).map((s, i) => (
                    <Line
                      key={s.name}
                      dataKey={s.name}
                      name={s.name}
                      type="monotone"
                      stroke={CHART_COLORS[i % CHART_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  ))}
                  <Line
                    dataKey="__total"
                    name="Total"
                    type="monotone"
                    stroke="#f8fafc"
                    strokeWidth={3}
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-[var(--text-muted)] text-sm">
                {t("investments.noBalanceHistory")}
              </div>
            )}
          </div>
        </div>

        {/* Allocation Pie Chart */}
        {portfolioAnalysis.allocation.filter((d) => d.balance > 0).length > 0 && (
          <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
            <h3 className="text-xs sm:text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
              {t("investments.portfolioAllocation")}
            </h3>
            <div className="h-[300px]">
              <DonutChart
                data={portfolioAnalysis.allocation
                  .filter((d) => d.balance > 0)
                  .map((d) => ({ name: d.name, value: d.balance }))}
                sorted
                showLegend
                labelMode="percent"
                centerLabel={
                  <span className="text-base font-semibold text-[#f8fafc]">
                    {formatCurrency(portfolioAnalysis.total_value)}
                  </span>
                }
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
