import { useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../hooks/useScrollLock";
import Plot from "react-plotly.js";
import { chartTheme, plotlyConfig } from "../utils/plotlyLocale";
import {
  Plus,
  Landmark,
  Trash2,
  Power,
  PowerOff,
  BarChart2,
  Pencil,
  Info,
  AlertTriangle,
  CheckCircle,
} from "lucide-react";
import { liabilitiesApi, taggingApi } from "../services/api";
import { SelectDropdown } from "../components/common/SelectDropdown";
import { Skeleton } from "../components/common/Skeleton";

interface Liability {
  id: number;
  name: string;
  lender?: string;
  category: string;
  tag: string;
  principal_amount: number;
  interest_rate: number;
  term_months: number;
  start_date: string;
  is_paid_off: number;
  paid_off_date?: string;
  notes?: string;
  created_date: string;
  monthly_payment: number;
  total_interest: number;
  remaining_balance: number;
  total_paid: number;
  percent_paid: number;
  payments_made: number;
}

interface AnalysisData {
  schedule: Array<{
    payment_number: number;
    date: string;
    payment: number;
    principal_portion: number;
    interest_portion: number;
    remaining_balance: number;
  }>;
  transactions: Array<Record<string, unknown>>;
  actual_vs_expected: Array<{
    date: string;
    expected_payment: number;
    actual_payment: number;
    difference: number;
  }>;
  summary: {
    total_receipts: number;
    total_payments: number;
    total_interest_cost: number;
    interest_paid: number;
    interest_remaining: number;
    monthly_payment: number;
    remaining_balance: number;
    percent_paid: number;
    payments_made: number;
  };
}

interface DebtPoint {
  date: string;
  balance: number;
}

interface DebtOverTimeData {
  series: Array<{ name: string; points: DebtPoint[] }>;
  total: DebtPoint[];
}

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 0,
  }).format(val);

function LiabilityCard({
  liability,
  onAnalysis,
  onEdit,
  onPayOff,
  onReopen,
  onDelete,
}: {
  liability: Liability;
  onAnalysis: (id: number) => void;
  onEdit: (l: Liability) => void;
  onPayOff: (id: number) => void;
  onReopen: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const { t } = useTranslation();
  const isPaidOff = !!liability.is_paid_off;
  const [showNotes, setShowNotes] = useState(false);

  return (
    <div
      className={`group bg-[var(--surface)] rounded-2xl border ${isPaidOff ? "border-emerald-500/10 opacity-60" : "border-[var(--surface-light)]"} p-4 md:p-6 shadow-sm hover:shadow-xl transition-all flex flex-col`}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-4">
          <div
            className={`p-3 rounded-xl ${isPaidOff ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"}`}
          >
            <Landmark size={24} />
          </div>
          <div>
            <h3 className="font-bold text-lg text-white">{liability.name}</h3>
            {liability.lender && (
              <p className="text-xs text-[var(--text-muted)] font-medium mt-0.5">
                {liability.lender}
              </p>
            )}
          </div>
        </div>
        <div
          className={`px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-tighter ${isPaidOff ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"}`}
        >
          {isPaidOff ? t("liabilities.paidOff") : t("liabilities.active")}
        </div>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-muted)] font-medium mb-4 px-1">
        <span>{t("liabilities.fixedRate")}</span>
        <span>·</span>
        <span dir="ltr">{liability.interest_rate}% {t("liabilities.interest")}</span>
        <span>·</span>
        <span>
          {liability.term_months} {t("liabilities.termMonths").toLowerCase()}
        </span>
        <span>·</span>
        <span>
          {t("liabilities.startDate")} {liability.start_date}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-5">
        <div className="flex justify-between text-xs font-bold text-[var(--text-muted)] mb-1.5">
          <span>{t("liabilities.percentPaid")}</span>
          <span dir="ltr">{liability.percent_paid.toFixed(1)}%</span>
        </div>
        <div className="w-full h-2.5 bg-[var(--surface-base)] rounded-full overflow-hidden border border-[var(--surface-light)]">
          <div
            className={`h-full rounded-full transition-all ${isPaidOff ? "bg-emerald-500" : "bg-rose-500"}`}
            style={{ width: `${Math.min(liability.percent_paid, 100)}%` }}
          />
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <div className="text-center p-3 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
            {t("liabilities.loanAmount")}
          </p>
          <p className="text-base font-bold text-white mt-1" dir="ltr">
            {formatCurrency(liability.principal_amount)}
          </p>
        </div>
        <div className="text-center p-3 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
            {t("liabilities.remainingBalance")}
          </p>
          <p className="text-base font-bold text-white mt-1" dir="ltr">
            {formatCurrency(liability.remaining_balance)}
          </p>
        </div>
        <div className="text-center p-3 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
            {t("liabilities.monthlyPayment")}
          </p>
          <p className="text-base font-bold text-white mt-1" dir="ltr">
            {formatCurrency(liability.monthly_payment)}
          </p>
        </div>
        <div className="text-center p-3 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
            {t("liabilities.totalInterestCost")}
          </p>
          <p className="text-base font-bold text-white mt-1" dir="ltr">
            {formatCurrency(liability.total_interest)}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-auto flex items-center justify-between pt-4 border-t border-[var(--surface-light)]">
        <div className="flex gap-2">
          {!isPaidOff ? (
            <button
              onClick={() => onPayOff(liability.id)}
              className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all"
              title={t("liabilities.payOff")}
            >
              <PowerOff size={16} />
            </button>
          ) : (
            <button
              onClick={() => onReopen(liability.id)}
              className="p-2 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-all"
              title={t("liabilities.reopen")}
            >
              <Power size={16} />
            </button>
          )}
          <button
            onClick={() => {
              if (window.confirm(t("liabilities.confirmDelete")))
                onDelete(liability.id);
            }}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-red-400 transition-all"
            title={t("common.delete")}
          >
            <Trash2 size={16} />
          </button>
          {liability.notes && (
            <div className="relative">
              <button
                className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] cursor-help hover:text-white transition-colors"
                onClick={() => setShowNotes(!showNotes)}
              >
                <Info size={16} />
              </button>
              {showNotes && (
                <>
                  <div className="fixed inset-0 z-[9]" onClick={() => setShowNotes(false)} />
                  <div className="absolute bottom-full start-0 mb-2 w-48 max-w-[calc(100vw-3rem)] p-2 rounded-lg bg-[var(--surface-light)] text-[10px] text-white z-10 shadow-xl border border-white/5">
                    {liability.notes}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onEdit(liability)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title={t("common.edit")}
          >
            <Pencil size={16} />
          </button>
          <button
            onClick={() => onAnalysis(liability.id)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title={t("liabilities.analysis")}
          >
            <BarChart2 size={16} />
          </button>
        </div>
      </div>

    </div>
  );
}

export function Liabilities() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [analysisModalId, setAnalysisModalId] = useState<number | null>(null);
  const [payOffForm, setPayOffForm] = useState<{
    id: number | null;
    date: string;
  }>({ id: null, date: new Date().toISOString().split("T")[0] });

  // Create form
  const [newLiability, setNewLiability] = useState({
    name: "",
    lender: "",
    tag: "",
    principal_amount: "",
    interest_rate: "",
    term_months: "",
    start_date: "",
    notes: "",
  });

  // Detection result for tag transactions
  const [tagDetection, setTagDetection] = useState<{
    has_receipt: boolean;
    receipt: { date: string; amount: number } | null;
    payments: Array<{ date: string; amount: number }>;
  } | null>(null);

  const handleTagChange = useCallback(async (tag: string) => {
    setNewLiability((prev) => ({ ...prev, tag }));
    setTagDetection(null);
    if (!tag) return;

    try {
      const res = await liabilitiesApi.detectTransactions(tag);
      const data = res.data;
      setTagDetection(data);
      if (data.has_receipt && data.receipt) {
        setNewLiability((prev) => ({
          ...prev,
          tag,
          principal_amount: String(data.receipt.amount),
          start_date: data.receipt.date,
        }));
      }
    } catch {
      // Detection is best-effort
    }
  }, []);

  // Edit form
  const [editForm, setEditForm] = useState<{
    id: number | null;
    name: string;
    lender: string;
    interest_rate: string;
    notes: string;
  }>({ id: null, name: "", lender: "", interest_rate: "", notes: "" });
  useScrollLock(isAddOpen || !!editForm.id || !!analysisModalId || !!payOffForm.id);

  // Queries
  const { data: liabilities, isLoading } = useQuery({
    queryKey: ["liabilities"],
    queryFn: () => liabilitiesApi.getAll(true).then((r) => r.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const { data: analysisData } = useQuery<AnalysisData>({
    queryKey: ["liabilities", analysisModalId, "analysis"],
    queryFn: () =>
      liabilitiesApi.getAnalysis(analysisModalId!).then((r) => r.data),
    enabled: !!analysisModalId,
  });

  // Mutations
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["liabilities"] });

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => liabilitiesApi.create(data),
    onSuccess: () => {
      invalidate();
      setIsAddOpen(false);
      setNewLiability({
        name: "",
        lender: "",
        tag: "",
        principal_amount: "",
        interest_rate: "",
        term_months: "",
        start_date: "",
        notes: "",
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      liabilitiesApi.update(id, data),
    onSuccess: () => {
      invalidate();
      setEditForm({
        id: null,
        name: "",
        lender: "",
        interest_rate: "",
        notes: "",
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => liabilitiesApi.delete(id),
    onSuccess: invalidate,
  });

  const payOffMutation = useMutation({
    mutationFn: ({ id, date }: { id: number; date: string }) =>
      liabilitiesApi.payOff(id, date),
    onSuccess: () => {
      invalidate();
      setPayOffForm({
        id: null,
        date: new Date().toISOString().split("T")[0],
      });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: (id: number) => liabilitiesApi.reopen(id),
    onSuccess: invalidate,
  });

  const generateMutation = useMutation({
    mutationFn: (id: number) => liabilitiesApi.generateTransactions(id),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["liabilities", analysisModalId, "analysis"] });
    },
  });

  // Summary calculations
  const activeLiabilities =
    liabilities?.filter((l: Liability) => !l.is_paid_off) || [];
  const paidOffLiabilities =
    liabilities?.filter((l: Liability) => !!l.is_paid_off) || [];
  const totalDebt = activeLiabilities.reduce(
    (sum: number, l: Liability) => sum + l.remaining_balance,
    0,
  );
  const totalMonthly = activeLiabilities.reduce(
    (sum: number, l: Liability) => sum + l.monthly_payment,
    0,
  );
  const totalInterest = (liabilities || []).reduce(
    (sum: number, l: Liability) => sum + l.total_interest,
    0,
  );

  // Available tags: Liabilities tags not already used by existing liabilities
  const usedTags = new Set(
    liabilities?.map((l: Liability) => l.tag) || [],
  );
  const availableTags: string[] = categories?.["Liabilities"]
    ? categories["Liabilities"].filter((tag: string) => !usedTags.has(tag))
    : [];
  const canAdd = availableTags.length > 0;

  // Debt over time chart data from actual transactions
  const { data: debtOverTimeRaw } = useQuery<DebtOverTimeData>({
    queryKey: ["liabilities", "debt-over-time"],
    queryFn: () => liabilitiesApi.getDebtOverTime().then((r) => r.data),
    enabled: activeLiabilities.length > 0,
  });
  const debtOverTimeData = debtOverTimeRaw?.series || [];
  const debtTotalLine = debtOverTimeRaw?.total || [];

  // Shared card callbacks
  const handleEdit = useCallback((l: Liability) => {
    setEditForm({
      id: l.id,
      name: l.name,
      lender: l.lender || "",
      interest_rate: String(l.interest_rate),
      notes: l.notes || "",
    });
  }, []);

  const handlePayOff = useCallback((id: number) => {
    setPayOffForm({
      id,
      date: new Date().toISOString().split("T")[0],
    });
  }, []);

  // Analysis modal tab
  const [analysisTab, setAnalysisTab] = useState<"schedule" | "actual">(
    "schedule",
  );

  if (isLoading)
    return (
      <div className="space-y-8 p-4 md:p-8">
        <Skeleton variant="text" lines={2} className="w-64" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
    <div className="space-y-6 md:space-y-8 animate-in fade-in duration-500 pb-20">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">{t("liabilities.title")}</h1>
          <p className="text-[var(--text-muted)] mt-1">
            {t("liabilities.subtitle")}
          </p>
        </div>
        <button
          onClick={() => setIsAddOpen(true)}
          disabled={!canAdd}
          className={`flex items-center gap-2 px-4 md:px-6 py-2 rounded-xl font-bold transition-all text-sm md:text-base ${canAdd ? "bg-[var(--primary)] text-white hover:bg-[var(--primary-dark)] shadow-lg shadow-[var(--primary)]/20" : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed"}`}
        >
          <Plus size={18} /> {t("liabilities.addLiability")}
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
          <p className="text-[10px] uppercase font-black tracking-widest text-rose-400 mb-1">
            {t("liabilities.totalDebt")}
          </p>
          <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
            {formatCurrency(totalDebt)}
          </p>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
          <p className="text-[10px] uppercase font-black tracking-widest text-[var(--text-muted)] mb-1">
            {t("liabilities.monthlyPayments")}
          </p>
          <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
            {formatCurrency(totalMonthly)}
          </p>
        </div>
        <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6">
          <p className="text-[10px] uppercase font-black tracking-widest text-amber-400 mb-1">
            {t("liabilities.totalInterest")}
          </p>
          <p className="text-xl md:text-2xl font-black text-white" dir="ltr">
            {formatCurrency(totalInterest)}
          </p>
        </div>
      </div>

      {/* Charts: Debt Over Time + Debt Allocation */}
      {activeLiabilities.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Debt Over Time */}
          <div className="lg:col-span-2 bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
            <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
              {t("liabilities.debtOverTime")}
            </h3>
            <div className="h-[300px]">
              <Plot
                data={[
                  ...debtOverTimeData.map(
                    (
                      s: { name: string; points: { date: string; balance: number }[] },
                      i: number,
                    ) => ({
                      x: s.points.map((p) => p.date),
                      y: s.points.map((p) => p.balance),
                      name: s.name,
                      type: "scatter" as const,
                      mode: "lines" as const,
                      line: {
                        color: [
                          "#3b82f6",
                          "#10b981",
                          "#f59e0b",
                          "#ef4444",
                          "#8b5cf6",
                          "#06b6d4",
                          "#ec4899",
                        ][i % 7],
                        width: 2,
                        shape: "hv" as const,
                      },
                    }),
                  ),
                  ...(debtOverTimeData.length > 1
                    ? [
                        {
                          x: debtTotalLine.map((p) => p.date),
                          y: debtTotalLine.map((p) => p.balance),
                          name: t("liabilities.totalDebt"),
                          type: "scatter" as const,
                          mode: "lines" as const,
                          line: { color: "#ffffff", width: 3, shape: "hv" as const },
                        },
                      ]
                    : []),
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
            </div>
          </div>

          {/* Debt Allocation Pie Chart */}
          <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
            <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
              {t("liabilities.debtAllocation")}
            </h3>
            <div className="h-[300px]">
              <Plot
                data={[
                  {
                    values: activeLiabilities.map(
                      (l: Liability) => l.remaining_balance,
                    ),
                    labels: activeLiabilities.map((l: Liability) => l.name),
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
        </div>
      )}

      {/* Active Liabilities */}
      <div>
        {activeLiabilities.length > 0 ? (
          <>
            <h2 className="text-xl font-bold mb-6 flex items-center gap-2">
              {t("liabilities.activeLiabilities")}
              <span className="text-[10px] font-black bg-[var(--primary)]/20 text-[var(--primary)] px-2 py-0.5 rounded-full">
                {activeLiabilities.length}
              </span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {activeLiabilities.map((l: Liability) => (
                <LiabilityCard
                  key={l.id}
                  liability={l}
                  onAnalysis={setAnalysisModalId}
                  onEdit={handleEdit}
                  onPayOff={handlePayOff}
                  onReopen={reopenMutation.mutate}
                  onDelete={deleteMutation.mutate}
                />
              ))}
            </div>
          </>
        ) : (
          <div className="bg-[var(--surface)] border border-dashed border-[var(--surface-light)] rounded-3xl p-16 text-center">
            <div className="p-4 bg-[var(--surface-light)] rounded-2xl w-fit mx-auto mb-6 text-[var(--text-muted)]">
              <Landmark size={32} />
            </div>
            <h2 className="text-xl font-bold mb-2">
              {t("liabilities.noLiabilities")}
            </h2>
          </div>
        )}
      </div>

      {/* Paid Off Liabilities */}
      {paidOffLiabilities.length > 0 && (
        <div className="pt-8 border-t border-[var(--surface-light)]">
          <h2 className="text-xl font-bold mb-6 flex items-center gap-2 text-[var(--text-muted)]">
            {t("liabilities.paidOffLiabilities")}
            <span className="text-[10px] font-black bg-[var(--surface-light)] px-2 py-0.5 rounded-full">
              {paidOffLiabilities.length}
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 opacity-75 grayscale-[0.5]">
            {paidOffLiabilities.map((l: Liability) => (
              <LiabilityCard
                key={l.id}
                liability={l}
                onAnalysis={setAnalysisModalId}
                onEdit={handleEdit}
                onPayOff={handlePayOff}
                onReopen={reopenMutation.mutate}
                onDelete={deleteMutation.mutate}
              />
            ))}
          </div>
        </div>
      )}

      {/* Create Modal */}
      {isAddOpen && (
        <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6 shadow-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-md animate-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto">
            <h3 className="text-lg font-bold mb-4">
              {t("liabilities.addLiability")}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.name")} *
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newLiability.name}
                  onChange={(e) =>
                    setNewLiability({ ...newLiability, name: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.lender")}
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newLiability.lender}
                  onChange={(e) =>
                    setNewLiability({ ...newLiability, lender: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.tag")} *
                </label>
                <SelectDropdown
                  options={availableTags.map((tag: string) => ({ label: tag, value: tag }))}
                  value={newLiability.tag}
                  onChange={handleTagChange}
                  placeholder={t("liabilities.selectTag")}
                />
                {tagDetection && !tagDetection.has_receipt && (
                  <div className="flex items-start gap-2 mt-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-sm">
                    <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                    <span className="text-amber-300">
                      {t("liabilities.noReceiptWarning")}
                    </span>
                  </div>
                )}
                {tagDetection?.has_receipt && (
                  <div className="flex items-start gap-2 mt-2 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-sm">
                    <CheckCircle size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                    <span className="text-emerald-300">
                      {t("liabilities.receiptDetected", {
                        amount: tagDetection.receipt?.amount.toLocaleString(),
                        date: tagDetection.receipt?.date,
                        payments: tagDetection.payments.length,
                      })}
                    </span>
                  </div>
                )}
              </div>
              {tagDetection && !tagDetection.has_receipt && (
                <>
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      {t("liabilities.principalAmount")} *
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                      value={newLiability.principal_amount}
                      onChange={(e) =>
                        setNewLiability({
                          ...newLiability,
                          principal_amount: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      {t("liabilities.startDate")} *
                    </label>
                    <input
                      type="date"
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                      value={newLiability.start_date}
                      onChange={(e) =>
                        setNewLiability({
                          ...newLiability,
                          start_date: e.target.value,
                        })
                      }
                    />
                  </div>
                </>
              )}
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.interestRate")} (%) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newLiability.interest_rate}
                  onChange={(e) =>
                    setNewLiability({
                      ...newLiability,
                      interest_rate: e.target.value,
                    })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.termMonths")} *
                </label>
                <input
                  type="number"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newLiability.term_months}
                  onChange={(e) =>
                    setNewLiability({
                      ...newLiability,
                      term_months: e.target.value,
                    })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.notes")}
                </label>
                <textarea
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium resize-none"
                  rows={3}
                  value={newLiability.notes}
                  onChange={(e) =>
                    setNewLiability({ ...newLiability, notes: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setIsAddOpen(false)}
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                disabled={
                  !newLiability.name ||
                  !newLiability.tag ||
                  !tagDetection ||
                  (!tagDetection.has_receipt &&
                    (!newLiability.principal_amount ||
                      !newLiability.start_date)) ||
                  !newLiability.interest_rate ||
                  !newLiability.term_months ||
                  createMutation.isPending
                }
                onClick={() =>
                  createMutation.mutate({
                    name: newLiability.name,
                    lender: newLiability.lender || undefined,
                    tag: newLiability.tag,
                    principal_amount: Number(newLiability.principal_amount),
                    interest_rate: Number(newLiability.interest_rate),
                    term_months: Number(newLiability.term_months),
                    start_date: newLiability.start_date,
                    notes: newLiability.notes || undefined,
                  })
                }
                className="flex-1 py-3 text-sm font-bold bg-[var(--primary)] text-white rounded-xl hover:bg-[var(--primary-dark)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {createMutation.isPending ? "..." : t("common.save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editForm.id && (
        <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6 shadow-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-md animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              {t("liabilities.editLiability")}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.name")}
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={editForm.name}
                  onChange={(e) =>
                    setEditForm({ ...editForm, name: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.lender")}
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={editForm.lender}
                  onChange={(e) =>
                    setEditForm({ ...editForm, lender: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.interestRate")} (%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={editForm.interest_rate}
                  onChange={(e) =>
                    setEditForm({ ...editForm, interest_rate: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.notes")}
                </label>
                <textarea
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium resize-none"
                  rows={3}
                  value={editForm.notes}
                  onChange={(e) =>
                    setEditForm({ ...editForm, notes: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  setEditForm({
                    id: null,
                    name: "",
                    lender: "",
                    interest_rate: "",
                    notes: "",
                  })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                disabled={!editForm.name || updateMutation.isPending}
                onClick={() =>
                  updateMutation.mutate({
                    id: editForm.id!,
                    data: {
                      name: editForm.name,
                      lender: editForm.lender || undefined,
                      interest_rate: editForm.interest_rate
                        ? Number(editForm.interest_rate)
                        : undefined,
                      notes: editForm.notes || undefined,
                    },
                  })
                }
                className="flex-1 py-3 text-sm font-bold bg-[var(--primary)] text-white rounded-xl hover:bg-[var(--primary-dark)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {updateMutation.isPending ? "..." : t("common.save")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Pay Off Modal */}
      {payOffForm.id && (
        <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6 shadow-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              {t("liabilities.payOff")}
            </h3>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                {t("liabilities.paidOffDate")}
              </label>
              <input
                type="date"
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                value={payOffForm.date}
                onChange={(e) =>
                  setPayOffForm({ ...payOffForm, date: e.target.value })
                }
              />
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  setPayOffForm({
                    id: null,
                    date: new Date().toISOString().split("T")[0],
                  })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                disabled={!payOffForm.date || payOffMutation.isPending}
                onClick={() =>
                  payOffMutation.mutate({
                    id: payOffForm.id!,
                    date: payOffForm.date,
                  })
                }
                className="flex-1 py-3 text-sm font-bold bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {payOffMutation.isPending ? "..." : t("liabilities.payOff")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Analysis Modal */}
      {analysisModalId && (
        <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-4 md:p-6 shadow-2xl w-full max-w-[calc(100vw-2rem)] md:max-w-4xl animate-in zoom-in-95 duration-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-bold">{t("liabilities.analysis")}</h3>
              <button
                onClick={() => setAnalysisModalId(null)}
                className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
              >
                &times;
              </button>
            </div>

            {analysisData ? (
              <>
                {/* Summary */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.totalReceipts")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.total_receipts)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.totalPaymentsMade")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.total_payments)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.totalInterestCost")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.total_interest_cost)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.interestPaid")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.interest_paid)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.interestRemaining")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.interest_remaining)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.monthlyPayment")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.monthly_payment)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.remainingBalance")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {formatCurrency(analysisData.summary.remaining_balance)}
                    </p>
                  </div>
                  <div className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
                    <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">
                      {t("liabilities.percentPaid")}
                    </p>
                    <p className="text-lg font-bold text-white mt-1" dir="ltr">
                      {analysisData.summary.percent_paid.toFixed(1)}%
                    </p>
                  </div>
                </div>

                {/* Tabs + Generate Button */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex gap-2">
                    <button
                      onClick={() => setAnalysisTab("schedule")}
                      className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${analysisTab === "schedule" ? "bg-[var(--primary)] text-white" : "bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
                    >
                      {t("liabilities.amortizationSchedule")}
                    </button>
                    <button
                      onClick={() => setAnalysisTab("actual")}
                      className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${analysisTab === "actual" ? "bg-[var(--primary)] text-white" : "bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"}`}
                    >
                      {t("liabilities.actualVsExpected")}
                    </button>
                  </div>
                  <button
                    onClick={() => generateMutation.mutate(analysisModalId)}
                    disabled={generateMutation.isPending}
                    className="px-4 py-2 rounded-lg text-sm font-bold bg-amber-600 text-white hover:bg-amber-700 transition-all disabled:opacity-50"
                  >
                    {generateMutation.isPending ? "..." : t("liabilities.generateMissing")}
                  </button>
                </div>

                {/* Amortization Schedule Table */}
                {analysisTab === "schedule" && (
                  <div className="overflow-x-auto max-h-96">
                    <table className="min-w-[500px] w-full text-sm">
                      <thead className="sticky top-0 bg-[var(--surface)]">
                        <tr className="text-[9px] md:text-[10px] uppercase font-black tracking-wider text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                          <th className="py-2 text-start ps-2 whitespace-nowrap">
                            {t("liabilities.paymentNumber")}
                          </th>
                          <th className="py-2 text-start whitespace-nowrap">
                            {t("common.date")}
                          </th>
                          <th className="py-2 text-end whitespace-nowrap">
                            {t("liabilities.payment")}
                          </th>
                          <th className="py-2 text-end whitespace-nowrap">
                            {t("liabilities.principalPortion")}
                          </th>
                          <th className="py-2 text-end whitespace-nowrap">
                            {t("liabilities.interestPortion")}
                          </th>
                          <th className="py-2 text-end pe-2 whitespace-nowrap">
                            {t("liabilities.remainingBalance")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysisData.schedule.map((row) => (
                          <tr
                            key={row.payment_number}
                            className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30"
                          >
                            <td className="py-2 ps-2 text-[var(--text-muted)]">
                              {row.payment_number}
                            </td>
                            <td className="py-2 whitespace-nowrap">{row.date}</td>
                            <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                              {formatCurrency(row.payment)}
                            </td>
                            <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                              {formatCurrency(row.principal_portion)}
                            </td>
                            <td className="py-2 text-end whitespace-nowrap" dir="ltr">
                              {formatCurrency(row.interest_portion)}
                            </td>
                            <td className="py-2 text-end pe-2 whitespace-nowrap" dir="ltr">
                              {formatCurrency(row.remaining_balance)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Actual vs Expected Table */}
                {analysisTab === "actual" && (
                  <div className="overflow-x-auto max-h-96">
                    <table className="min-w-[400px] w-full text-sm">
                      <thead className="sticky top-0 bg-[var(--surface)]">
                        <tr className="text-[9px] md:text-[10px] uppercase font-black tracking-wider text-[var(--text-muted)] border-b border-[var(--surface-light)]">
                          <th className="py-2 text-start ps-2 whitespace-nowrap">
                            {t("common.date")}
                          </th>
                          <th className="py-2 text-end whitespace-nowrap">
                            {t("liabilities.expectedPayment")}
                          </th>
                          <th className="py-2 text-end whitespace-nowrap">
                            {t("liabilities.actualPayment")}
                          </th>
                          <th className="py-2 text-end pe-2 whitespace-nowrap">
                            {t("liabilities.difference")}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysisData.actual_vs_expected.map((row, i) => (
                          <tr
                            key={i}
                            className={`border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30 ${row.difference !== 0 ? (row.difference > 0 ? "bg-emerald-500/5" : "bg-rose-500/5") : ""}`}
                          >
                            <td className="py-2 ps-2">{row.date}</td>
                            <td className="py-2 text-end" dir="ltr">
                              {formatCurrency(row.expected_payment)}
                            </td>
                            <td className="py-2 text-end" dir="ltr">
                              {formatCurrency(row.actual_payment)}
                            </td>
                            <td
                              className={`py-2 text-end pe-2 font-bold ${row.difference > 0 ? "text-emerald-400" : row.difference < 0 ? "text-rose-400" : ""}`}
                              dir="ltr"
                            >
                              {row.difference !== 0 &&
                                (row.difference > 0 ? "+" : "")}
                              {formatCurrency(row.difference)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Skeleton variant="card" className="h-20" />
                  <Skeleton variant="card" className="h-20" />
                  <Skeleton variant="card" className="h-20" />
                </div>
                <Skeleton variant="card" className="h-64" />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
