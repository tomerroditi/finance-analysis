import { useState } from "react";
import { useQuery, useQueries, useMutation, useQueryClient } from "@tanstack/react-query";
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
  Pencil,
  Settings,
} from "lucide-react";
import { investmentsApi, taggingApi } from "../services/api";
import { SelectDropdown } from "../components/common/SelectDropdown";
import { Skeleton } from "../components/common/Skeleton";
import { Sparkline } from "../components/common/Sparkline";
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

const RATE_TYPES = new Set(["bonds", "pension", "p2p_lending"]);

function InvestmentCard({
  inv,
  onViewAnalysis,
  onClose,
  onReopen,
  onDelete,
  onUpdateBalance,
  onEditCloseDate,
  onEdit,
  analysisData,
}: any) {
  const snapshotAgeDays = inv.latest_snapshot_date
    ? Math.floor(
        (new Date().getTime() - new Date(inv.latest_snapshot_date).getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : 0;

  const formatCardCurrency = (val: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
      maximumFractionDigits: 0,
    }).format(val);

  return (
    <div
      className={`group bg-[var(--surface)] rounded-2xl border ${inv.is_closed ? "border-red-500/10" : "border-[var(--surface-light)]"} p-6 shadow-sm hover:shadow-xl transition-all flex flex-col`}
    >
      <div className="flex items-start justify-between mb-4">
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
                {inv.tag}
              </span>
            </div>
          </div>
        </div>
        {!!inv.is_closed && (
          <div className="px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-tighter bg-red-500/20 text-red-400">
            Closed
          </div>
        )}
      </div>

      {/* Balance + Sparkline */}
      <div className="flex items-center justify-between mb-4 p-4 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
        <div>
          {analysisData ? (
            inv.is_closed ? (
              <>
                <p
                  className={`text-2xl font-black ${analysisData.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {analysisData.profit_loss >= 0 ? "+" : ""}
                  {formatCardCurrency(analysisData.profit_loss)}
                </p>
                <p className="text-sm font-semibold mt-1 text-[var(--text-muted)]">
                  {analysisData.roi != null &&
                    `ROI: ${analysisData.roi >= 0 ? "+" : ""}${analysisData.roi.toFixed(1)}%`}
                </p>
              </>
            ) : (
              <>
                <p className="text-2xl font-black text-white">
                  {formatCardCurrency(analysisData.balance)}
                </p>
                <p
                  className={`text-sm font-semibold mt-1 ${analysisData.profit_loss >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                >
                  {analysisData.profit_loss >= 0 ? "+" : ""}
                  {formatCardCurrency(analysisData.profit_loss)}
                  {analysisData.roi != null &&
                    ` (${analysisData.roi >= 0 ? "+" : ""}${analysisData.roi.toFixed(1)}%)`}
                </p>
              </>
            )
          ) : (
            <div className="space-y-2">
              <Skeleton variant="card" className="h-7 w-28" />
              <Skeleton variant="card" className="h-4 w-20" />
            </div>
          )}
        </div>
        <div className="flex-shrink-0 ml-4">
          {analysisData?.history?.length >= 2 ? (
            <Sparkline
              data={analysisData.history}
              width={100}
              height={40}
              color={analysisData.profit_loss >= 0 ? "#10b981" : "#f43f5e"}
            />
          ) : !analysisData ? (
            <Skeleton variant="card" className="w-[100px] h-[40px]" />
          ) : null}
        </div>
      </div>

      {/* Metrics Strip */}
      <div className={`grid ${RATE_TYPES.has(inv.type) && inv.interest_rate ? "grid-cols-3" : "grid-cols-2"} gap-3 mb-4`}>
        <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">Deposits</p>
          <p className="text-sm font-bold text-white mt-0.5">
            {analysisData ? formatCardCurrency(analysisData.total_deposits) : "—"}
          </p>
        </div>
        <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">Withdrawals</p>
          <p className="text-sm font-bold text-white mt-0.5">
            {analysisData ? formatCardCurrency(analysisData.total_withdrawals) : "—"}
          </p>
        </div>
        {RATE_TYPES.has(inv.type) && !!inv.interest_rate && (
          <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
            <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">Rate</p>
            <p className="text-sm font-bold text-white mt-0.5">{inv.interest_rate}%</p>
          </div>
        )}
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--text-muted)] font-medium mb-4 px-1">
        <span>Opened {inv.first_transaction_date || inv.created_date}</span>
        {inv.latest_snapshot_date && (
          <>
            <span>·</span>
            <span className={snapshotAgeDays > 30 ? "text-amber-400" : ""}>
              Updated {inv.latest_snapshot_date}
              {snapshotAgeDays > 30 ? ` (${snapshotAgeDays}d ago)` : ""}
            </span>
          </>
        )}
        {!!inv.is_closed && inv.closed_date && (
          <>
            <span>·</span>
            <span className="text-red-400 inline-flex items-center gap-1">
              Closed {inv.closed_date}
              <button
                onClick={() => onEditCloseDate(inv.id, inv.closed_date)}
                className="hover:text-white transition-all"
                title="Edit close date"
              >
                <Pencil size={10} />
              </button>
            </span>
          </>
        )}
      </div>

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
          {inv.notes && (
            <div className="group/notes relative">
              <div className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] cursor-help">
                <Info size={16} />
              </div>
              <div className="absolute bottom-full left-0 mb-2 w-48 p-2 rounded-lg bg-[var(--surface-light)] text-[10px] text-white opacity-0 group-hover/notes:opacity-100 transition-all pointer-events-none z-10 shadow-xl border border-white/5">
                {inv.notes}
              </div>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onEdit(inv)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title="Edit"
          >
            <Settings size={16} />
          </button>
          {!inv.is_closed && (
            <button
              onClick={() => onUpdateBalance(inv.id)}
              className="p-2 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all"
              title="Update Balance"
            >
              <DollarSign size={16} />
            </button>
          )}
          <button
            onClick={() => onViewAnalysis(inv.id)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title="View Analysis"
          >
            <BarChart2 size={16} />
          </button>
        </div>
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
  const [editForm, setEditForm] = useState<{
    investmentId: number | null;
    name: string;
    type: string;
    interest_rate: number;
    interest_rate_type: string;
    notes: string;
  }>({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", notes: "" });

  const [balanceForm, setBalanceForm] = useState<{
    investmentId: number | null;
    date: string;
    balance: string;
  }>({ investmentId: null, date: new Date().toISOString().split("T")[0], balance: "" });

  const [closeForm, setCloseForm] = useState<{
    investmentId: number | null;
    date: string;
    mode: "close" | "edit";
  }>({ investmentId: null, date: new Date().toISOString().split("T")[0], mode: "close" });

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

  const [chartIncludeClosed, setChartIncludeClosed] = useState(true);
  const { data: balanceHistory } = useQuery({
    queryKey: ["portfolio-balance-history", chartIncludeClosed],
    queryFn: () =>
      investmentsApi.getPortfolioBalanceHistory(chartIncludeClosed).then((res) => res.data),
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
  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      investmentsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      setEditForm({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", notes: "" });
    },
  });

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
    mutationFn: ({ id, closedDate }: { id: number; closedDate: string }) =>
      investmentsApi.close(id, closedDate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      setCloseForm({ investmentId: null, date: new Date().toISOString().split("T")[0], mode: "close" });
    },
  });

  const updateCloseDateMutation = useMutation({
    mutationFn: ({ id, closedDate }: { id: number; closedDate: string }) =>
      investmentsApi.update(id, { closed_date: closedDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      setCloseForm({ investmentId: null, date: new Date().toISOString().split("T")[0], mode: "close" });
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
      queryClient.invalidateQueries({ queryKey: ["investments"] });
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
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      queryClient.invalidateQueries({ queryKey: ["investment-snapshots"] });
      queryClient.invalidateQueries({ queryKey: ["investment-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["portfolio-analysis"] });
    },
  });

  const calculateMutation = useMutation({
    mutationFn: (investmentId: number) =>
      investmentsApi.calculateFixedRateSnapshots(investmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["investments"] });
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

  const closedAnalysisQueries = useQueries({
    queries: includeClosed
      ? closedInvestments.map((inv: any) => ({
          queryKey: ["investment-analysis", inv.id],
          queryFn: () =>
            investmentsApi.getInvestmentAnalysis(inv.id).then((res) => res.data),
          staleTime: 5 * 60 * 1000,
        }))
      : [],
  });

  const getClosedAnalysisData = (invId: number) => {
    const idx = closedInvestments.findIndex((inv: any) => inv.id === invId);
    const query = closedAnalysisQueries[idx];
    if (!query?.data) return undefined;
    const d: any = query.data;
    const history = d.history?.map((h: any) => h.balance) || [];
    // Downsample to ~30 points for sparkline
    let condensed = history;
    if (history.length > 30) {
      const step = Math.floor(history.length / 30);
      condensed = history.filter((_: any, i: number) => i % step === 0);
      if (condensed[condensed.length - 1] !== history[history.length - 1]) {
        condensed.push(history[history.length - 1]);
      }
    }
    return {
      balance: d.metrics.current_balance,
      profit_loss: d.metrics.absolute_profit_loss,
      roi: d.metrics.roi_percentage,
      total_deposits: d.metrics.total_deposits,
      total_withdrawals: d.metrics.total_withdrawals,
      history: condensed,
    };
  };

  if (isLoading)
    return (
      <div className="space-y-8 p-8">
        <Skeleton variant="text" lines={2} className="w-64" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Skeleton variant="card" className="h-40" />
          <Skeleton variant="card" className="h-40" />
        </div>
      </div>
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
        <div className="space-y-6">
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
            {/* Charts: Balance Over Time + Allocation side-by-side */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Balance Over Time Chart */}
              <div className="lg:col-span-2 bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)]">
                    Balance Over Time
                  </h3>
                  <button
                    onClick={() => setChartIncludeClosed(!chartIncludeClosed)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all ${chartIncludeClosed ? "bg-[var(--surface-light)] border-[var(--surface-light)] text-white" : "border-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
                  >
                    {chartIncludeClosed ? "Hide Closed" : "Include Closed"}
                  </button>
                </div>
                <div className="h-[300px]">
                  {balanceHistory?.series?.length > 0 ? (
                    <Plot
                      data={[
                        ...balanceHistory.series.map((s: any, i: number) => ({
                          x: s.data.map((d: any) => d.date),
                          y: s.data.map((d: any) => d.balance),
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
                          x: balanceHistory.total.map((d: any) => d.date),
                          y: balanceHistory.total.map((d: any) => d.balance),
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
                      config={{ displayModeBar: false }}
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-[var(--text-muted)] text-sm">
                      No balance history available
                    </div>
                  )}
                </div>
              </div>

              {/* Allocation Pie Chart */}
              {portfolioAnalysis.allocation.length > 0 && (
                <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)]">
                  <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
                    Portfolio Allocation
                  </h3>
                  <div className="h-[300px]">
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
                  onClose={(id: number) =>
                    setCloseForm({ investmentId: id, date: new Date().toISOString().split("T")[0], mode: "close" })
                  }
                  onReopen={reopenMutation.mutate}
                  onDelete={deleteMutation.mutate}
                  onUpdateBalance={(id: number) =>
                    setBalanceForm({
                      investmentId: id,
                      date: new Date().toISOString().split("T")[0],
                      balance: "",
                    })
                  }
                  onEditCloseDate={() => {}}
                  onEdit={(inv: any) => setEditForm({
                    investmentId: inv.id,
                    name: inv.name,
                    type: inv.type || "",
                    interest_rate: inv.interest_rate || 0,
                    interest_rate_type: inv.interest_rate_type || "variable",
                    notes: inv.notes || "",
                  })}
                  analysisData={portfolioAnalysis?.allocation?.find(
                    (a: any) => a.name === inv.name
                  )}
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
                onClose={(id: number) =>
                  setCloseForm({ investmentId: id, date: new Date().toISOString().split("T")[0], mode: "close" })
                }
                onReopen={reopenMutation.mutate}
                onDelete={deleteMutation.mutate}
                onUpdateBalance={(id: number) =>
                  setBalanceForm({
                    investmentId: id,
                    date: new Date().toISOString().split("T")[0],
                    balance: "",
                  })
                }
                onEditCloseDate={(id: number, closedDate: string) =>
                  setCloseForm({ investmentId: id, date: closedDate, mode: "edit" })
                }
                onEdit={(inv: any) => setEditForm({
                  investmentId: inv.id,
                  name: inv.name,
                  type: inv.type || "",
                  interest_rate: inv.interest_rate || 0,
                  interest_rate_type: inv.interest_rate_type || "variable",
                  notes: inv.notes || "",
                })}
                analysisData={getClosedAnalysisData(inv.id)}
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
                    !!investments?.find((i: any) => i.id === selectedAnalysisId)
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
                  {selectedSnapshots?.length > 0 && (
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

      {/* Close / Edit Close Date Modal */}
      {closeForm.investmentId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              {closeForm.mode === "close" ? "Close Investment" : "Edit Close Date"}
            </h3>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                Close Date
              </label>
              <input
                type="date"
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                value={closeForm.date}
                onChange={(e) =>
                  setCloseForm({ ...closeForm, date: e.target.value })
                }
              />
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  setCloseForm({ investmentId: null, date: new Date().toISOString().split("T")[0], mode: "close" })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!closeForm.date || closeMutation.isPending || updateCloseDateMutation.isPending}
                onClick={() => {
                  if (closeForm.mode === "close") {
                    closeMutation.mutate({ id: closeForm.investmentId!, closedDate: closeForm.date });
                  } else {
                    updateCloseDateMutation.mutate({ id: closeForm.investmentId!, closedDate: closeForm.date });
                  }
                }}
                className="flex-[2] py-3 bg-red-500 rounded-xl text-white font-bold hover:bg-red-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {closeMutation.isPending || updateCloseDateMutation.isPending
                  ? "Saving..."
                  : closeForm.mode === "close"
                    ? "Close Investment"
                    : "Update Date"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Investment Modal */}
      {editForm.investmentId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">Edit Investment</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Name
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              {RATE_TYPES.has(editForm.type) && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      Interest Rate %
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                      value={editForm.interest_rate}
                      onChange={(e) => setEditForm({ ...editForm, interest_rate: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      Rate Type
                    </label>
                    <select
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                      value={editForm.interest_rate_type}
                      onChange={(e) => setEditForm({ ...editForm, interest_rate_type: e.target.value })}
                    >
                      <option value="variable">Variable</option>
                      <option value="fixed">Fixed</option>
                    </select>
                  </div>
                </div>
              )}
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Notes
                </label>
                <textarea
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium resize-none"
                  rows={3}
                  value={editForm.notes}
                  onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setEditForm({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", notes: "" })}
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!editForm.name || editMutation.isPending}
                onClick={() =>
                  editMutation.mutate({
                    id: editForm.investmentId!,
                    data: {
                      name: editForm.name,
                      interest_rate: editForm.interest_rate,
                      interest_rate_type: editForm.interest_rate_type,
                      notes: editForm.notes,
                    },
                  })
                }
                className="flex-[2] py-3 bg-[var(--primary)] rounded-xl text-white font-bold hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {editMutation.isPending ? "Saving..." : "Save"}
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
              {RATE_TYPES.has(newInvestment.type) && (
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
              )}
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
