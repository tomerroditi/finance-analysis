import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../../hooks/useScrollLock";
import {
  X,
  Wallet,
  DollarSign,
  Percent,
  TrendingUp,
  Trash2,
  BarChart2,
} from "lucide-react";
import Plot from "react-plotly.js";
import { investmentsApi } from "../../services/api";
import { chartTheme, plotlyConfig } from "../../utils/plotlyLocale";
import { formatCurrency } from "../../utils/numberFormatting";

interface Investment {
  id: number;
  name: string;
  interest_rate?: number;
  interest_rate_type?: string;
}

interface BalancePoint {
  date: string;
  balance: number;
}

interface Snapshot {
  id: number;
  date: string;
  balance: number;
  source: string;
}

interface MonthlyTransaction {
  month: string;
  deposits: number;
  withdrawals: number;
}

interface MonthRow {
  key: string;
  month: string;
  date: string | null;
  snapshot: Snapshot | null;
  deposits: number;
  withdrawals: number;
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
    <div className="bg-[var(--surface)] rounded-xl p-5 border border-[var(--surface-light)] flex items-center justify-between shadow-sm">
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


interface InvestmentAnalysisModalProps {
  investmentId: number;
  investment: Investment | undefined;
  onClose: () => void;
}

export function InvestmentAnalysisModal({
  investmentId,
  investment,
  onClose,
}: InvestmentAnalysisModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  useScrollLock(true);

  const { data: selectedAnalysis } = useQuery({
    queryKey: ["investment-analysis", investmentId],
    queryFn: () =>
      investmentsApi
        .getInvestmentAnalysis(investmentId)
        .then((res) => res.data),
  });

  const { data: selectedSnapshots } = useQuery({
    queryKey: ["investment-snapshots", investmentId],
    queryFn: () =>
      investmentsApi
        .getBalanceSnapshots(investmentId)
        .then((res) => res.data),
  });

  const deleteSnapshotMutation = useMutation({
    mutationFn: ({ snapshotId }: { snapshotId: number }) =>
      investmentsApi.deleteBalanceSnapshot(investmentId, snapshotId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const calculateMutation = useMutation({
    mutationFn: () =>
      investmentsApi.calculateFixedRateSnapshots(investmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl animate-in zoom-in-95 duration-200">
        <div className="sticky top-0 z-10 bg-[var(--surface)]/95 backdrop-blur border-b border-[var(--surface-light)] p-6 flex justify-between items-center">
          <h2 className="text-2xl font-bold flex items-center gap-3">
            <BarChart2 className="text-[var(--primary)]" /> {t("investments.investmentAnalysis")}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[var(--surface-light)] rounded-full transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        <div className="p-8 space-y-8">
          {selectedAnalysis ? (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard
                  title={t("investments.currentBalance")}
                  value={formatCurrency(
                    selectedAnalysis.metrics.current_balance,
                  )}
                  icon={Wallet}
                  color="bg-blue-500/10 text-blue-400"
                />
                <StatCard
                  title={t("investments.profitLoss")}
                  value={formatCurrency(
                    selectedAnalysis.metrics.absolute_profit_loss,
                  )}
                  icon={DollarSign}
                  color={
                    selectedAnalysis.metrics.absolute_profit_loss >= 0
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-red-500/10 text-red-400"
                  }
                />
                <StatCard
                  title={t("investments.roi")}
                  value={formatPercent(
                    selectedAnalysis.metrics.roi_percentage,
                  )}
                  icon={Percent}
                  color={
                    selectedAnalysis.metrics.roi_percentage >= 0
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-red-500/10 text-red-400"
                  }
                />
                <StatCard
                  title={t("investments.cagr")}
                  value={formatPercent(
                    selectedAnalysis.metrics.cagr_percentage,
                  )}
                  icon={TrendingUp}
                  color="bg-purple-500/10 text-purple-400"
                />
              </div>

              <div className="bg-[var(--surface-base)] rounded-2xl p-6 border border-[var(--surface-light)]">
                <h3 className="text-lg font-bold mb-6">{t("investments.balanceHistory")}</h3>
                <div className="h-[400px]">
                  <Plot
                    data={[
                      {
                        x: selectedAnalysis.history.map((d: BalancePoint) => d.date),
                        y: selectedAnalysis.history.map(
                          (d: BalancePoint) => d.balance,
                        ),
                        type: "scatter",
                        mode: "lines",
                        fill: "tozeroy",
                        line: { color: "#3b82f6", width: 3 },
                        fillcolor: "rgba(59, 130, 246, 0.1)",
                      },
                    ]}
                    layout={{
                      ...chartTheme,
                      xaxis: { showgrid: false },
                      yaxis: { gridcolor: "rgba(255,255,255,0.05)" },
                    }}
                    style={{ width: "100%", height: "100%" }}
                    config={plotlyConfig()}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 text-sm text-[var(--text-muted)] font-medium bg-[var(--surface-base)] p-6 rounded-2xl border border-[var(--surface-light)]">
                <div>
                  <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                    {t("investments.totalDeposits")}
                  </p>
                  <p className="text-white text-lg font-bold">
                    {formatCurrency(
                      selectedAnalysis.metrics.total_deposits,
                    )}
                  </p>
                </div>
                <div>
                  <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                    {t("investments.totalWithdrawals")}
                  </p>
                  <p className="text-white text-lg font-bold">
                    {formatCurrency(
                      selectedAnalysis.metrics.total_withdrawals,
                    )}
                  </p>
                </div>
                <div>
                  <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                    {t("investments.holdingPeriod")}
                  </p>
                  <p className="text-white text-lg font-bold">
                    {selectedAnalysis.metrics.total_years.toFixed(1)} {t("investments.years")}
                  </p>
                </div>
              </div>

              {/* Fixed-Rate Calculation */}
              {investment?.interest_rate_type === "fixed" &&
                !!investment?.interest_rate && (
                <div className="flex justify-end">
                  <button
                    onClick={() => calculateMutation.mutate()}
                    disabled={calculateMutation.isPending}
                    className="px-4 py-2 bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
                  >
                    {calculateMutation.isPending
                      ? t("investments.calculating")
                      : t("investments.calculateFixedRate")}
                  </button>
                </div>
              )}

              {/* Monthly Breakdown: Snapshots + Deposits */}
              {(() => {
                const snapshots: Snapshot[] = selectedSnapshots ?? [];
                const monthly: MonthlyTransaction[] =
                  selectedAnalysis.monthly_transactions ?? [];

                if (snapshots.length === 0 && monthly.length === 0) return null;

                const monthMap = new Map<string, MonthRow>();
                for (const m of monthly) {
                  monthMap.set(m.month, {
                    key: `m-${m.month}`,
                    month: m.month,
                    date: null,
                    snapshot: null,
                    deposits: m.deposits,
                    withdrawals: m.withdrawals,
                  });
                }
                const rows: MonthRow[] = [];
                for (const snap of snapshots) {
                  const month = snap.date.slice(0, 7);
                  const monthDeposit = monthMap.get(month);
                  rows.push({
                    key: `s-${snap.id}`,
                    month,
                    date: snap.date,
                    snapshot: snap,
                    deposits: monthDeposit?.deposits ?? 0,
                    withdrawals: monthDeposit?.withdrawals ?? 0,
                  });
                  monthMap.delete(month);
                }
                for (const orphan of monthMap.values()) rows.push(orphan);

                rows.sort((a, b) => {
                  const ka = a.date ?? `${a.month}-00`;
                  const kb = b.date ?? `${b.month}-00`;
                  return kb.localeCompare(ka);
                });

                return (
                  <div className="bg-[var(--surface-base)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-bold">{t("investments.balanceSnapshots")}</h3>
                      <span className="text-xs text-[var(--text-muted)]">
                        {rows.length} {t("investments.entries")}
                      </span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                            <th className="text-start py-2 font-bold">{t("common.date")}</th>
                            <th className="text-end py-2 font-bold">{t("investments.balance")}</th>
                            <th className="text-end py-2 font-bold">{t("investments.deposits")}</th>
                            <th className="text-center py-2 font-bold">{t("investments.source")}</th>
                            <th className="text-end py-2 font-bold"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((row) => (
                            <tr
                              key={row.key}
                              className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30"
                            >
                              <td className="py-2 text-white font-medium">
                                {row.date ?? row.month}
                              </td>
                              <td className="py-2 text-end font-bold">
                                {row.snapshot ? (
                                  <span className="text-white">{formatCurrency(row.snapshot.balance)}</span>
                                ) : (
                                  <span className="text-[var(--text-muted)]">—</span>
                                )}
                              </td>
                              <td className="py-2 text-end font-bold">
                                {row.deposits > 0 ? (
                                  <span className="text-emerald-400">{formatCurrency(row.deposits)}</span>
                                ) : (
                                  <span className="text-[var(--text-muted)]">—</span>
                                )}
                              </td>
                              <td className="py-2 text-center">
                                {row.snapshot ? (
                                  <span
                                    className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                                      row.snapshot.source === "manual"
                                        ? "bg-blue-500/20 text-blue-400"
                                        : row.snapshot.source === "calculated"
                                          ? "bg-purple-500/20 text-purple-400"
                                          : "bg-emerald-500/20 text-emerald-400"
                                    }`}
                                  >
                                    {row.snapshot.source}
                                  </span>
                                ) : (
                                  <span className="text-[var(--text-muted)]">—</span>
                                )}
                              </td>
                              <td className="py-2 text-end">
                                {row.snapshot ? (
                                  <button
                                    onClick={() =>
                                      deleteSnapshotMutation.mutate({
                                        snapshotId: row.snapshot!.id,
                                      })
                                    }
                                    className="p-1 rounded hover:bg-red-500/20 text-[var(--text-muted)] hover:text-red-400 transition-all"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })()}
            </>
          ) : (
            <div className="text-center py-20 text-[var(--text-muted)]">
              {t("investments.loadingAnalysis")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
