import { useState, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { AXIS_DEFAULTS, CHART_COLORS, formatAxisNumber } from "../utils/chartStyle";
import { ChartTooltip } from "../components/charts/ChartTooltip";
import { ChartLegend } from "../components/charts/ChartLegend";
import { DonutChart } from "../components/charts/DonutChart";
import {
  Plus,
  Landmark,
  Trash2,
  Power,
  PowerOff,
  BarChart2,
  Pencil,
  Info,
} from "lucide-react";
import { liabilitiesApi, type Liability } from "../services/api";
import { Skeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
import { formatCurrency } from "../utils/numberFormatting";
import { formatDate, formatShortDate, todayISO } from "../utils/dateFormatting";
import { useCategories } from "../hooks/useCategories";
import { useCategoryTagCreate } from "../hooks/useCategoryTagCreate";
import { useConfirm } from "../context/DialogContext";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";
import {
  LiabilityCreateModal,
  type TagDetection,
} from "../components/liabilities/LiabilityCreateModal";
import { LiabilityEditModal } from "../components/liabilities/LiabilityEditModal";
import { LiabilityPayOffModal } from "../components/liabilities/LiabilityPayOffModal";
import {
  LiabilityAnalysisModal,
  type AnalysisData,
} from "../components/liabilities/LiabilityAnalysisModal";

interface DebtPoint {
  date: string;
  balance: number;
}

interface DebtOverTimeData {
  series: Array<{ name: string; points: DebtPoint[] }>;
  total: DebtPoint[];
}

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
  const confirm = useConfirm();
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
          {t("liabilities.termMonthsCount", { count: liability.term_months })}
        </span>
        <span>·</span>
        <span>
          {t("liabilities.startDate")} <span dir="ltr">{formatDate(liability.start_date)}</span>
        </span>
      </div>

      {/* Progress bar */}
      <div className="mb-5">
        <div className="flex justify-between text-xs font-bold text-[var(--text-muted)] mb-1.5">
          <span>{t("liabilities.percentPaid")}</span>
          {isPaidOff ? (
            <span className="text-emerald-400">{t("liabilities.closed")}</span>
          ) : (
            <span dir="ltr">{liability.percent_paid.toFixed(1)}%</span>
          )}
        </div>
        <div className="w-full h-2.5 bg-[var(--surface-base)] rounded-full overflow-hidden border border-[var(--surface-light)]">
          <div
            className={`h-full rounded-full transition-all ${isPaidOff ? "bg-emerald-500" : "bg-rose-500"}`}
            style={{ width: `${isPaidOff ? 100 : Math.min(liability.percent_paid, 100)}%` }}
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
            {formatCurrency(isPaidOff ? 0 : liability.remaining_balance)}
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
            onClick={async () => {
              const ok = await confirm({
                title: t("common.deleteTitle"),
                message: t("liabilities.confirmDelete"),
                confirmLabel: t("common.delete"),
                isDestructive: true,
              });
              if (ok) onDelete(liability.id);
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
  const qk = useQueryKeys();

  const [isAddOpen, setIsAddOpen] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const [analysisModalId, setAnalysisModalId] = useState<number | null>(null);
  const [payOffForm, setPayOffForm] = useState<{
    id: number | null;
    date: string;
  }>({ id: null, date: todayISO() });

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
  const [tagDetection, setTagDetection] = useState<TagDetection | null>(null);

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

  // Queries
  const { data: liabilities, isLoading } = useQuery({
    queryKey: qk.liabilities.list(true),
    queryFn: () => liabilitiesApi.getAll(true).then((r) => r.data),
  });

  const { data: categories } = useCategories();
  const { createTag } = useCategoryTagCreate();

  const { data: analysisData } = useQuery<AnalysisData>({
    queryKey: qk.liabilities.analysis(analysisModalId ?? 0),
    queryFn: () =>
      liabilitiesApi.getAnalysis(analysisModalId!).then((r) => r.data),
    enabled: !!analysisModalId,
  });

  // Mutations
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: qkPrefix.liabilities });

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
        date: todayISO(),
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
      queryClient.invalidateQueries({ queryKey: qk.liabilities.analysis(analysisModalId ?? 0) });
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
    queryKey: qk.liabilities.debtOverTime(),
    queryFn: () => liabilitiesApi.getDebtOverTime().then((r) => r.data),
    enabled: activeLiabilities.length > 0,
  });
  const debtOverTimeData = debtOverTimeRaw?.series || [];

  // Unified rows keyed by date: one key per liability series + "__total",
  // so every line renders on a single shared x-axis.
  const debtRows = useMemo(() => {
    const byDate = new Map<string, Record<string, number | string>>();
    const ensure = (date: string) => {
      let row = byDate.get(date);
      if (!row) {
        row = { date };
        byDate.set(date, row);
      }
      return row;
    };
    for (const s of debtOverTimeRaw?.series ?? []) {
      for (const p of s.points) ensure(p.date)[s.name] = p.balance;
    }
    for (const p of debtOverTimeRaw?.total ?? []) {
      ensure(p.date).__total = p.balance;
    }
    return [...byDate.values()].sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    );
  }, [debtOverTimeRaw]);

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
      date: todayISO(),
    });
  }, []);

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
      <div className="flex items-center justify-end gap-3">
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
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={debtRows} margin={{ top: 8, bottom: 4, left: 0, right: 8 }}>
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
                  {debtOverTimeData.map((s, i) => (
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
                  {debtOverTimeData.length > 1 && (
                    <Line
                      dataKey="__total"
                      name={t("liabilities.totalDebt")}
                      type="monotone"
                      stroke="#f8fafc"
                      strokeWidth={3}
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Debt Allocation Pie Chart */}
          <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)]">
            <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
              {t("liabilities.debtAllocation")}
            </h3>
            <div className="h-[300px]">
              <DonutChart
                data={activeLiabilities.map((l: Liability) => ({
                  name: l.name,
                  value: l.remaining_balance,
                }))}
                sorted
                showLegend
                labelMode="percent"
                centerLabel={
                  <span className="text-base font-semibold text-[#f8fafc]">
                    {formatCurrency(totalDebt)}
                  </span>
                }
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
          <EmptyState
            title={t("emptyStates.liabilities.title")}
            description={t("emptyStates.liabilities.description")}
            cta={{
              label: t("liabilities.addFirstLiability"),
              onClick: () => setIsAddOpen(true),
            }}
            secondary={{
              label: t("emptyStates.tryDemoMode"),
              onClick: () => setShowDemoConfirm(true),
            }}
            footer={
              showDemoConfirm ? (
                <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
              ) : undefined
            }
          />
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

      <LiabilityCreateModal
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        form={newLiability}
        setForm={setNewLiability}
        tagDetection={tagDetection}
        availableTags={availableTags}
        onTagChange={handleTagChange}
        onCreateTag={async (name) => {
          const formatted = await createTag("Liabilities", name);
          await handleTagChange(formatted);
        }}
        isPending={createMutation.isPending}
        onSubmit={() =>
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
      />

      <LiabilityEditModal
        form={editForm}
        setForm={setEditForm}
        onClose={() =>
          setEditForm({
            id: null,
            name: "",
            lender: "",
            interest_rate: "",
            notes: "",
          })
        }
        isPending={updateMutation.isPending}
        onSubmit={() =>
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
      />

      <LiabilityPayOffModal
        form={payOffForm}
        setForm={setPayOffForm}
        onClose={() => setPayOffForm({ id: null, date: todayISO() })}
        isPending={payOffMutation.isPending}
        onSubmit={() =>
          payOffMutation.mutate({ id: payOffForm.id!, date: payOffForm.date })
        }
      />

      <LiabilityAnalysisModal
        isOpen={analysisModalId != null}
        onClose={() => setAnalysisModalId(null)}
        analysisData={analysisData}
        onGenerate={() => generateMutation.mutate(analysisModalId!)}
        isGenerating={generateMutation.isPending}
      />
    </div>
  );
}
