import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  Power,
  PowerOff,
  TrendingUp,
  Info,
  BarChart2,
  X,
  Wallet,
  DollarSign,
  Percent,
} from "lucide-react";
import { investmentsApi, taggingApi } from "../services/api";
import { SelectDropdown } from "../components/common/SelectDropdown";
import Plot from "react-plotly.js";

function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  icon: any;
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

function InvestmentCard({
  inv,
  onViewAnalysis,
  onClose,
  onReopen,
  onDelete,
  onUpdateBalance,
}: any) {
  const snapshotAgeDays = inv.latest_snapshot_date
    ? Math.floor(
        (new Date().getTime() - new Date(inv.latest_snapshot_date).getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : 0;

  return (
    <div
      className={`group bg-[var(--surface)] rounded-2xl border ${inv.is_closed ? "border-red-500/10" : "border-[var(--surface-light)]"} p-6 shadow-sm hover:shadow-xl transition-all flex flex-col`}
    >
      <div className="flex items-start justify-between mb-6">
        <div className="flex items-center gap-4">
          <div
            className={`p-3 rounded-xl ${inv.is_closed ? "bg-red-500/10 text-red-400" : "bg-emerald-500/10 text-emerald-400"}`}
          >
            <TrendingUp size={24} />
          </div>
          <div>
            <h3 className="font-bold text-lg text-white">{inv.name}</h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)]">
                {(inv.type || "").replace("_", " ")}
              </span>
              <span className="text-[var(--text-muted)]">•</span>
              <span className="text-xs text-[var(--text-muted)] font-medium">
                {inv.category} / {inv.tag}
              </span>
            </div>
          </div>
        </div>
        <div
          className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-tighter ${inv.is_closed ? "bg-red-500/20 text-red-400" : "bg-emerald-500/20 text-emerald-400"}`}
        >
          {inv.is_closed ? "Closed" : "Active"}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
          <p className="text-[10px] uppercase font-bold text-[var(--text-muted)] mb-1">
            Interest Rate
          </p>
          <p className="text-lg font-black text-white">
            {inv.interest_rate || 0}%
          </p>
        </div>
        <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
          <p className="text-[10px] uppercase font-bold text-[var(--text-muted)] mb-1">
            Created
          </p>
          <p className="text-xs font-bold text-white mt-1.5">
            {inv.created_date}
          </p>
        </div>
      </div>

      {inv.latest_snapshot_date && (
        <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)] -mt-4 mb-8">
          <p className="text-[10px] uppercase font-bold text-[var(--text-muted)] mb-1">
            Last Balance Update
          </p>
          <p className={`text-xs font-bold mt-1.5 ${
            snapshotAgeDays > 30 ? "text-amber-400" : "text-white"
          }`}>
            {inv.latest_snapshot_date}
            {snapshotAgeDays > 30 ? ` (${snapshotAgeDays}d ago)` : ""}
          </p>
        </div>
      )}

      {!inv.is_closed && (
        <button
          onClick={() => onUpdateBalance(inv.id)}
          className="w-full py-2.5 mb-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 font-bold transition-all flex items-center justify-center gap-2 text-sm"
        >
          <DollarSign size={14} /> Update Balance
        </button>
      )}
      <button
        onClick={() => onViewAnalysis(inv.id)}
        className="w-full py-3 mb-4 rounded-xl bg-[var(--surface-light)] hover:bg-[var(--primary)] text-[var(--text-muted)] hover:text-white font-bold transition-all flex items-center justify-center gap-2"
      >
        <BarChart2 size={16} /> View Analysis
      </button>

      <div className="mt-auto flex items-center justify-between pt-4 border-t border-[var(--surface-light)]">
        <div className="flex gap-2">
          {!inv.is_closed ? (
            <button
              onClick={() => onClose(inv.id)}
              className="p-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-all"
              title="Close"
            >
              <PowerOff size={16} />
            </button>
          ) : (
            <button
              onClick={() => onReopen(inv.id)}
              className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all"
              title="Reopen"
            >
              <Power size={16} />
            </button>
          )}
          <button
            onClick={() => {
              if (window.confirm("Delete investment record?")) onDelete(inv.id);
            }}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-red-400 transition-all"
            title="Delete"
          >
            <Trash2 size={16} />
          </button>
        </div>
        {inv.notes && (
          <div className="group/notes relative">
            <Info size={16} className="text-[var(--text-muted)] cursor-help" />
            <div className="absolute bottom-full right-0 mb-2 w-48 p-2 rounded-lg bg-[var(--surface-light)] text-[10px] text-white opacity-0 group-hover/notes:opacity-100 transition-all pointer-events-none z-10 shadow-xl border border-white/5">
              {inv.notes}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function Investments() {
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | null>(
    null,
  );

  // Form state
  const [newInvestment, setNewInvestment] = useState({
    name: "",
    category: "",
    tag: "",
    type: "stocks",
    interest_rate: 0,
    notes: "",
  });

  const [includeClosed, setIncludeClosed] = useState(false);
  const [balanceForm, setBalanceForm] = useState<{
    investmentId: number | null;
    date: string;
    balance: string;
  }>({ investmentId: null, date: new Date().toISOString().split("T")[0], balance: "" });

  // Queries
  const {
    data: investments,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["investments"],
    queryFn: () => investmentsApi.getAll(true).then((res) => res.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const { data: portfolioAnalysis } = useQuery({
    queryKey: ["portfolio-analysis"],
    queryFn: () =>
      investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });

  const { data: selectedAnalysis } = useQuery({
    queryKey: ["investment-analysis", selectedAnalysisId],
    queryFn: () =>
      selectedAnalysisId
        ? investmentsApi
            .getInvestmentAnalysis(selectedAnalysisId)
            .then((res) => res.data)
        : null,
    enabled: !!selectedAnalysisId,
  });

  const { data: selectedSnapshots } = useQuery({
    queryKey: ["investment-snapshots", selectedAnalysisId],
    queryFn: () =>
      selectedAnalysisId
        ? investmentsApi
            .getBalanceSnapshots(selectedAnalysisId)
            .then((res) => res.data)
        : null,
    enabled: !!selectedAnalysisId,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: any) => investmentsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      setIsAddOpen(false);
      setNewInvestment({
        name: "",
        category: "",
        tag: "",
        type: "stocks",
        interest_rate: 0,
        notes: "",
      });
    },
  });

  const closeMutation = useMutation({
    mutationFn: (id: number) =>
      investmentsApi.close(id, new Date().toISOString().split("T")[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: (id: number) => investmentsApi.reopen(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => investmentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const balanceSnapshotMutation = useMutation({
    mutationFn: (data: { investmentId: number; date: string; balance: number }) =>
      investmentsApi.createBalanceSnapshot(data.investmentId, {
        date: data.date,
        balance: data.balance,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      setBalanceForm({ investmentId: null, date: new Date().toISOString().split("T")[0], balance: "" });
    },
  });

  const deleteSnapshotMutation = useMutation({
    mutationFn: ({ investmentId, snapshotId }: { investmentId: number; snapshotId: number }) =>
      investmentsApi.deleteBalanceSnapshot(investmentId, snapshotId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const calculateMutation = useMutation({
    mutationFn: (investmentId: number) =>
      investmentsApi.calculateFixedRateSnapshots(investmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  // Filtering logic for New Investment dropdowns
  const usedTagsSet = new Set(
    investments?.map((inv: any) => `${inv.category}:${inv.tag}`),
  );

  const filteredCategories = categories
    ? Object.keys(categories)
        .filter((cat) => ["Investments"].includes(cat))
        .reduce((obj, key) => {
          const availableTags = categories[key].filter(
            (tag: string) => !usedTagsSet.has(`${key}:${tag}`),
          );
          if (availableTags.length > 0) {
            obj[key] = availableTags;
          }
          return obj;
        }, {} as any)
    : {};

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(val);
  const formatPercent = (val: number) =>
    `${val > 0 ? "+" : ""}${val.toFixed(2)}%`;

  const chartTheme = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#94a3b8", family: "Inter, sans-serif" },
    margin: { t: 30, b: 30, l: 40, r: 20 },
  };

  const activeInvestments =
    investments?.filter((inv: any) => !inv.is_closed) || [];
  const closedInvestments =
    investments?.filter((inv: any) => inv.is_closed) || [];

  if (isLoading)
    return (
      <div className="p-8 text-center text-[var(--text-muted)]">Loading...</div>
    );

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-20">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Investments</h1>
          <p className="text-[var(--text-muted)] mt-1">
            Track and manage your diverse investment portfolio
          </p>
        </div>
        <div className="flex gap-4">
          <button
            onClick={() => setIncludeClosed(!includeClosed)}
            className={`px-4 py-2 rounded-xl text-sm font-bold border ${includeClosed ? "bg-[var(--surface-light)] border-[var(--surface-light)] text-white" : "border-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
          >
            {includeClosed ? "Hide Closed" : "Show Closed"}
          </button>
          <button
            onClick={() => setIsAddOpen(true)}
            disabled={Object.keys(filteredCategories).length === 0}
            className="flex items-center gap-2 px-6 py-2 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:grayscale"
            title={
              Object.keys(filteredCategories).length === 0
                ? "All available tags in Savings/Investments are already in use"
                : ""
            }
          >
            <Plus size={18} /> New Investment
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-medium">
          Failed to load investments.
        </div>
      )}

      {/* Portfolio Overview */}
      {portfolioAnalysis && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <StatCard
                title="Total Value"
                value={formatCurrency(portfolioAnalysis.total_value)}
                icon={Wallet}
                color="bg-blue-500/10 text-blue-400"
              />
              <StatCard
                title="Total Profit/Loss"
                value={formatCurrency(portfolioAnalysis.total_profit)}
                icon={DollarSign}
                color={
                  portfolioAnalysis.total_profit >= 0
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-red-500/10 text-red-400"
                }
              />
              <StatCard
                title="Portfolio ROI"
                value={formatPercent(portfolioAnalysis.portfolio_roi)}
                icon={Percent}
                color={
                  portfolioAnalysis.portfolio_roi >= 0
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-red-500/10 text-red-400"
                }
              />
            </div>
            {/* Allocation Chart */}
            {portfolioAnalysis.allocation.length > 0 && (
              <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
                <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
                  Portfolio Allocation
                </h3>
                <div className="h-[200px]">
                  <Plot
                    data={[
                      {
                        values: portfolioAnalysis.allocation.map(
                          (d: any) => d.balance,
                        ),
                        labels: portfolioAnalysis.allocation.map(
                          (d: any) => d.name,
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
                    config={{ displayModeBar: false }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Active Investments */}
      <div>
        {activeInvestments.length > 0 ? (
          <>
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              Active Investments
              <span className="text-[10px] font-black bg-[var(--primary)]/20 text-[var(--primary)] px-2 py-0.5 rounded-full">
                {activeInvestments.length}
              </span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {activeInvestments.map((inv: any) => (
                <InvestmentCard
                  key={inv.id}
                  inv={inv}
                  onViewAnalysis={setSelectedAnalysisId}
                  onClose={closeMutation.mutate}
                  onReopen={reopenMutation.mutate}
                  onDelete={deleteMutation.mutate}
                  onUpdateBalance={(id: number) =>
                    setBalanceForm({
                      investmentId: id,
                      date: new Date().toISOString().split("T")[0],
                      balance: "",
                    })
                  }
                />
              ))}
            </div>
          </>
        ) : (
          <div className="bg-[var(--surface)] border border-dashed border-[var(--surface-light)] rounded-3xl p-16 text-center">
            <div className="p-4 bg-[var(--surface-light)] rounded-2xl w-fit mx-auto mb-6 text-[var(--text-muted)]">
              <TrendingUp size={32} />
            </div>
            <h2 className="text-xl font-bold mb-2">No active investments</h2>
            <p className="text-[var(--text-muted)] max-w-sm mx-auto">
              You don't have any active investments currently.
            </p>
          </div>
        )}
      </div>

      {/* Closed Investments */}
      {includeClosed && closedInvestments.length > 0 && (
        <div className="pt-8 border-t border-[var(--surface-light)]">
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-[var(--text-muted)]">
            Closed Investments
            <span className="text-[10px] font-black bg-[var(--surface-light)] px-2 py-0.5 rounded-full">
              {closedInvestments.length}
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 opacity-75 grayscale-[0.5]">
            {closedInvestments.map((inv: any) => (
              <InvestmentCard
                key={inv.id}
                inv={inv}
                onViewAnalysis={setSelectedAnalysisId}
                onClose={closeMutation.mutate}
                onReopen={reopenMutation.mutate}
                onDelete={deleteMutation.mutate}
                onUpdateBalance={(id: number) =>
                  setBalanceForm({
                    investmentId: id,
                    date: new Date().toISOString().split("T")[0],
                    balance: "",
                  })
                }
              />
            ))}
          </div>
        </div>
      )}

      {/* Analysis Modal */}
      {selectedAnalysisId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="sticky top-0 z-10 bg-[var(--surface)]/95 backdrop-blur border-b border-[var(--surface-light)] p-6 flex justify-between items-center">
              <h2 className="text-2xl font-bold flex items-center gap-3">
                <BarChart2 className="text-[var(--primary)]" /> Investment
                Analysis
              </h2>
              <button
                onClick={() => setSelectedAnalysisId(null)}
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
                      title="Current Balance"
                      value={formatCurrency(
                        selectedAnalysis.metrics.current_balance,
                      )}
                      icon={Wallet}
                      color="bg-blue-500/10 text-blue-400"
                    />
                    <StatCard
                      title="Profit/Loss"
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
                      title="ROI"
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
                      title="CAGR"
                      value={formatPercent(
                        selectedAnalysis.metrics.cagr_percentage,
                      )}
                      icon={TrendingUp}
                      color="bg-purple-500/10 text-purple-400"
                    />
                  </div>

                  <div className="bg-[var(--surface-base)] rounded-2xl p-6 border border-[var(--surface-light)]">
                    <h3 className="text-lg font-bold mb-6">Balance History</h3>
                    <div className="h-[400px]">
                      <Plot
                        data={[
                          {
                            x: selectedAnalysis.history.map((d: any) => d.date),
                            y: selectedAnalysis.history.map(
                              (d: any) => d.balance,
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
                        config={{ displayModeBar: false }}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-6 text-sm text-[var(--text-muted)] font-medium bg-[var(--surface-base)] p-6 rounded-2xl border border-[var(--surface-light)]">
                    <div>
                      <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                        Total Deposits
                      </p>
                      <p className="text-white text-lg font-bold">
                        {formatCurrency(
                          selectedAnalysis.metrics.total_deposits,
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                        Total Withdrawals
                      </p>
                      <p className="text-white text-lg font-bold">
                        {formatCurrency(
                          selectedAnalysis.metrics.total_withdrawals,
                        )}
                      </p>
                    </div>
                    <div>
                      <p className="uppercase text-[10px] tracking-widest font-bold mb-1">
                        Holding Period
                      </p>
                      <p className="text-white text-lg font-bold">
                        {selectedAnalysis.metrics.total_years.toFixed(1)} Years
                      </p>
                    </div>
                  </div>

                  {/* Fixed-Rate Calculation */}
                  {investments?.find((i: any) => i.id === selectedAnalysisId)
                    ?.interest_rate_type === "fixed" &&
                    investments?.find((i: any) => i.id === selectedAnalysisId)
                      ?.interest_rate && (
                    <div className="flex justify-end">
                      <button
                        onClick={() => calculateMutation.mutate(selectedAnalysisId!)}
                        disabled={calculateMutation.isPending}
                        className="px-4 py-2 bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 rounded-xl text-sm font-bold transition-all disabled:opacity-50"
                      >
                        {calculateMutation.isPending
                          ? "Calculating..."
                          : "Calculate Fixed Rate"}
                      </button>
                    </div>
                  )}

                  {/* Balance Snapshots */}
                  {selectedSnapshots && selectedSnapshots.length > 0 && (
                    <div className="bg-[var(--surface-base)] rounded-2xl p-6 border border-[var(--surface-light)]">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-bold">Balance Snapshots</h3>
                        <span className="text-xs text-[var(--text-muted)]">
                          {selectedSnapshots.length} entries
                        </span>
                      </div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                              <th className="text-left py-2 font-bold">Date</th>
                              <th className="text-right py-2 font-bold">Balance</th>
                              <th className="text-center py-2 font-bold">Source</th>
                              <th className="text-right py-2 font-bold"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedSnapshots.map((snap: any) => (
                              <tr
                                key={snap.id}
                                className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30"
                              >
                                <td className="py-2 text-white font-medium">
                                  {snap.date}
                                </td>
                                <td className="py-2 text-right text-white font-bold">
                                  {formatCurrency(snap.balance)}
                                </td>
                                <td className="py-2 text-center">
                                  <span
                                    className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                                      snap.source === "manual"
                                        ? "bg-blue-500/20 text-blue-400"
                                        : snap.source === "calculated"
                                          ? "bg-purple-500/20 text-purple-400"
                                          : "bg-emerald-500/20 text-emerald-400"
                                    }`}
                                  >
                                    {snap.source}
                                  </span>
                                </td>
                                <td className="py-2 text-right">
                                  <button
                                    onClick={() =>
                                      deleteSnapshotMutation.mutate({
                                        investmentId: selectedAnalysisId!,
                                        snapshotId: snap.id,
                                      })
                                    }
                                    className="p-1 rounded hover:bg-red-500/20 text-[var(--text-muted)] hover:text-red-400 transition-all"
                                  >
                                    <Trash2 size={14} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-20 text-[var(--text-muted)]">
                  Loading analysis...
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Update Balance Modal */}
      {balanceForm.investmentId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">Update Balance</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Date
                </label>
                <input
                  type="date"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={balanceForm.date}
                  onChange={(e) =>
                    setBalanceForm({ ...balanceForm, date: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Current Market Value
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="e.g. 125000"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={balanceForm.balance}
                  onChange={(e) =>
                    setBalanceForm({ ...balanceForm, balance: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  setBalanceForm({
                    investmentId: null,
                    date: new Date().toISOString().split("T")[0],
                    balance: "",
                  })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!balanceForm.balance || balanceSnapshotMutation.isPending}
                onClick={() =>
                  balanceSnapshotMutation.mutate({
                    investmentId: balanceForm.investmentId!,
                    date: balanceForm.date,
                    balance: parseFloat(balanceForm.balance),
                  })
                }
                className="flex-[2] py-3 bg-blue-500 rounded-xl text-white font-bold hover:bg-blue-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {balanceSnapshotMutation.isPending ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Modal (Existing) */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-8 shadow-2xl w-full max-w-lg animate-in zoom-in-95 duration-200">
            {/* ... Existing Add Modal Code ... */}
            <div className="flex items-center gap-3 mb-6">
              <div className="p-3 rounded-2xl bg-[var(--primary)] text-white shadow-lg shadow-[var(--primary)]/20">
                <TrendingUp size={24} />
              </div>
              <h2 className="text-2xl font-bold">New Investment</h2>
            </div>

            {createMutation.isError && (
              <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-medium animate-in slide-in-from-top-2">
                {(createMutation.error as any)?.response?.data?.detail ||
                  "Failed to create investment."}
              </div>
            )}

            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="col-span-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Investment Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. S&P 500 Index Fund"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newInvestment.name}
                  onChange={(e) =>
                    setNewInvestment({ ...newInvestment, name: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Category
                </label>
                <SelectDropdown
                  options={Object.keys(filteredCategories).map((cat) => ({ label: cat, value: cat }))}
                  value={newInvestment.category}
                  onChange={(val) =>
                    setNewInvestment({
                      ...newInvestment,
                      category: val,
                      tag: "",
                    })
                  }
                  placeholder="Select Category"
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Tag
                </label>
                <SelectDropdown
                  options={newInvestment.category && filteredCategories[newInvestment.category] ? filteredCategories[newInvestment.category].map((tag: string) => ({ label: tag, value: tag })) : []}
                  value={newInvestment.tag}
                  onChange={(val) =>
                    setNewInvestment({ ...newInvestment, tag: val })
                  }
                  placeholder="Select Tag"
                  disabled={!newInvestment.category}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Type
                </label>
                <SelectDropdown
                  options={[
                    { label: "Stocks", value: "stocks" },
                    { label: "Crypto", value: "crypto" },
                    { label: "Bonds", value: "bonds" },
                    { label: "Real Estate", value: "real_estate" },
                    { label: "Pension", value: "pension" },
                    { label: "Brokerage Account", value: "brokerage_account" },
                    { label: "Other", value: "other" },
                  ]}
                  value={newInvestment.type}
                  onChange={(val) =>
                    setNewInvestment({ ...newInvestment, type: val })
                  }
                  placeholder="Select Type"
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Int. Rate (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newInvestment.interest_rate}
                  onChange={(e) =>
                    setNewInvestment({
                      ...newInvestment,
                      interest_rate:
                        e.target.value === "" ? 0 : parseFloat(e.target.value),
                    })
                  }
                />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Notes
                </label>
                <textarea
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all h-24 font-medium"
                  value={newInvestment.notes}
                  onChange={(e) =>
                    setNewInvestment({
                      ...newInvestment,
                      notes: e.target.value,
                    })
                  }
                />
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setIsAddOpen(false)}
                className="flex-1 py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={
                  !newInvestment.name ||
                  !newInvestment.category ||
                  !newInvestment.tag ||
                  createMutation.isPending
                }
                onClick={() => createMutation.mutate(newInvestment)}
                className="flex-[2] py-4 bg-[var(--primary)] rounded-2xl text-white font-black hover:bg-[var(--primary-dark)] transition-all shadow-xl shadow-[var(--primary)]/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending ? "Creating..." : "Create Investment"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
