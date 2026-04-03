import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Wallet, DollarSign, Percent } from "lucide-react";
import Plot from "react-plotly.js";
import { investmentsApi } from "../../services/api";
import { chartTheme, plotlyConfig } from "../../utils/plotlyLocale";
import { formatCurrency } from "../../utils/numberFormatting";

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
        <p className="text-xl font-black mt-1 text-white">{value}</p>
      </div>
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon size={20} />
      </div>
    </div>
  );
}

const formatPercent = (val: number) =>
  `${val > 0 ? "+" : ""}${val.toFixed(2)}%`;


interface PortfolioOverviewProps {
  portfolioAnalysis: PortfolioAnalysis;
}

export function PortfolioOverview({ portfolioAnalysis }: PortfolioOverviewProps) {
  const { t } = useTranslation();
  const [chartIncludeClosed, setChartIncludeClosed] = useState(true);

  const { data: balanceHistory } = useQuery({
    queryKey: ["portfolio-balance-history", chartIncludeClosed],
    queryFn: () =>
      investmentsApi.getPortfolioBalanceHistory(chartIncludeClosed).then((res) => res.data),
  });

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
              <Plot
                data={[
                  ...balanceHistory.series.map((s: BalanceSeries, i: number) => ({
                    x: s.data.map((d: BalancePoint) => d.date),
                    y: s.data.map((d: BalancePoint) => d.balance),
                    name: s.name,
                    type: "scatter" as const,
                    mode: "lines" as const,
                    line: {
                      color: ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899"][i % 7],
                      width: 2,
                      shape: "hv" as const,
                    },
                  })),
                  {
                    x: balanceHistory.total.map((d: BalancePoint) => d.date),
                    y: balanceHistory.total.map((d: BalancePoint) => d.balance),
                    name: "Total",
                    type: "scatter" as const,
                    mode: "lines" as const,
                    line: { color: "#ffffff", width: 3, shape: "hv" as const },
                  },
                ]}
                layout={{
                  ...chartTheme,
                  xaxis: { showgrid: false },
                  yaxis: { gridcolor: "rgba(255,255,255,0.05)" },
                  showlegend: true,
                  legend: { orientation: "h", y: -0.12, font: { size: 10 } },
                }}
                style={{ width: "100%", height: "100%" }}
                config={plotlyConfig()}
              />
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
              <Plot
                data={[
                  {
                    values: portfolioAnalysis.allocation.filter((d) => d.balance > 0).map(
                      (d) => d.balance,
                    ),
                    labels: portfolioAnalysis.allocation.filter((d) => d.balance > 0).map(
                      (d) => d.name,
                    ),
                    type: "pie",
                    hole: 0.5,
                    marker: {
                      colors: [
                        "#3b82f6",
                        "#10b981",
                        "#f59e0b",
                        "#ef4444",
                        "#8b5cf6",
                      ],
                    },
                  },
                ]}
                layout={{
                  ...chartTheme,
                  margin: { t: 0, b: 0, l: 0, r: 0 },
                  showlegend: true,
                  legend: { orientation: "h" },
                }}
                style={{ width: "100%", height: "100%" }}
                config={plotlyConfig()}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
