import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, TrendingUp } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { investmentsApi, ratesApi, type Investment } from "../services/api";
import { Modal } from "../components/common/Modal";
import { SelectDropdown } from "../components/common/SelectDropdown";
import { Skeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
import { PortfolioOverview } from "../components/investments/PortfolioOverview";
import { InvestmentAnalysisModal } from "../components/investments/InvestmentAnalysisModal";
import { InvestmentCard, type AllocationItem } from "../components/investments/InvestmentCard";
import { useCategories } from "../hooks/useCategories";
import { useCategoryTagCreate } from "../hooks/useCategoryTagCreate";
import { todayISO } from "../utils/dateFormatting";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";

const RATE_TYPES = new Set(["bonds", "pension", "p2p_lending"]);

export function Investments() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const navigate = useNavigate();
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
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
    interest_rate_type: "fixed",
    rate_spread: 0,
    notes: "",
  });

  const [editForm, setEditForm] = useState<{
    investmentId: number | null;
    name: string;
    type: string;
    interest_rate: number;
    interest_rate_type: string;
    rate_spread: number;
    notes: string;
  }>({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", rate_spread: 0, notes: "" });

  const [balanceForm, setBalanceForm] = useState<{
    investmentId: number | null;
    date: string;
    balance: string;
  }>({ investmentId: null, date: todayISO(), balance: "" });

  const [closeForm, setCloseForm] = useState<{
    investmentId: number | null;
    date: string;
    mode: "close" | "edit";
  }>({ investmentId: null, date: todayISO(), mode: "close" });

  // Queries
  const {
    data: investments,
    isLoading,
    error,
  } = useQuery({
    queryKey: qk.investments.list(true),
    queryFn: () => investmentsApi.getAll(true).then((res) => res.data),
  });

  const { data: categories } = useCategories();
  const { createTag } = useCategoryTagCreate();

  const { data: currentRates } = useQuery({
    queryKey: qk.rates.current(),
    queryFn: () => ratesApi.getCurrent().then((res) => res.data),
    enabled: isAddOpen || editForm.investmentId != null,
  });

  const { data: portfolioAnalysis } = useQuery({
    queryKey: qk.investments.portfolio(),
    queryFn: () =>
      investmentsApi.getPortfolioAnalysis().then((res) => res.data),
  });


  // Mutations
  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: object }) =>
      investmentsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      queryClient.invalidateQueries({ queryKey: qkPrefix.insuranceAccounts });
      setEditForm({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", rate_spread: 0, notes: "" });
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => investmentsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      setIsAddOpen(false);
      setNewInvestment({
        name: "",
        category: "",
        tag: "",
        type: "stocks",
        interest_rate: 0,
        interest_rate_type: "fixed",
        rate_spread: 0,
        notes: "",
      });
    },
  });

  const closeMutation = useMutation({
    mutationFn: ({ id, closedDate }: { id: number; closedDate: string }) =>
      investmentsApi.close(id, closedDate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      setCloseForm({ investmentId: null, date: todayISO(), mode: "close" });
    },
  });

  const updateCloseDateMutation = useMutation({
    mutationFn: ({ id, closedDate }: { id: number; closedDate: string }) =>
      investmentsApi.update(id, { closed_date: closedDate }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      setCloseForm({ investmentId: null, date: todayISO(), mode: "close" });
    },
  });

  const reopenMutation = useMutation({
    mutationFn: (id: number) => investmentsApi.reopen(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => investmentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
    },
  });

  const balanceSnapshotMutation = useMutation({
    mutationFn: (data: { investmentId: number; date: string; balance: number }) =>
      investmentsApi.createBalanceSnapshot(data.investmentId, {
        date: data.date,
        balance: data.balance,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      setBalanceForm({ investmentId: null, date: todayISO(), balance: "" });
    },
  });


  // Filtering logic for New Investment dropdowns
  const usedTagsSet = new Set(
    investments?.map((inv: Investment) => `${inv.category}:${inv.tag}`),
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
        }, {} as Record<string, string[]>)
    : {};

  const activeInvestments =
    investments?.filter((inv: Investment) => !inv.is_closed) || [];
  const closedInvestments =
    investments?.filter((inv: Investment) => inv.is_closed) || [];

  const allocationById = useMemo(() => {
    const map = new Map<number, AllocationItem>();
    for (const a of (portfolioAnalysis?.allocation ?? []) as AllocationItem[]) {
      map.set(a.id, a);
    }
    return map;
  }, [portfolioAnalysis]);

  const getAllocationData = (invId: number) => allocationById.get(invId);

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-8 p-4 md:p-8">
        <Skeleton variant="text" lines={2} className="w-48 md:w-64" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
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
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500 pb-20">
      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-medium">
          {t("investments.failedToLoad")}
        </div>
      )}

      {/* Portfolio Overview */}
      {portfolioAnalysis && (
        <PortfolioOverview portfolioAnalysis={portfolioAnalysis} />
      )}

      {/* Active Investments */}
      <div>
        {activeInvestments.length > 0 ? (
          <>
            <div className="flex items-center justify-between mb-4 md:mb-6">
              <h2 className="text-lg md:text-xl font-bold flex items-center gap-2">
                {t("investments.activeInvestments")}
                <span className="text-[10px] font-black bg-[var(--primary)]/20 text-[var(--primary)] px-2 py-0.5 rounded-full">
                  {activeInvestments.length}
                </span>
              </h2>
              <button
                onClick={() => setIsAddOpen(true)}
                disabled={Object.keys(filteredCategories).length === 0}
                className="flex items-center gap-2 px-4 md:px-6 py-2 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:grayscale text-sm md:text-base"
                title={
                  Object.keys(filteredCategories).length === 0
                    ? t("investments.allTagsInUse")
                    : ""
                }
              >
                <Plus size={18} /> {t("investments.newInvestment")}
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-6">
              {activeInvestments.map((inv: Investment) => (
                <InvestmentCard
                  key={inv.id}
                  inv={inv}
                  onViewAnalysis={setSelectedAnalysisId}
                  onClose={(id: number) =>
                    setCloseForm({ investmentId: id, date: todayISO(), mode: "close" })
                  }
                  onReopen={reopenMutation.mutate}
                  onDelete={deleteMutation.mutate}
                  onUpdateBalance={(id: number) =>
                    setBalanceForm({
                      investmentId: id,
                      date: todayISO(),
                      balance: "",
                    })
                  }
                  onEditCloseDate={() => {}}
                  onEdit={(inv: Investment) => setEditForm({
                    investmentId: inv.id,
                    name: inv.name,
                    type: inv.type || "",
                    interest_rate: inv.interest_rate || 0,
                    interest_rate_type: inv.interest_rate_type || "variable",
                    rate_spread: inv.rate_spread ?? 0,
                    notes: inv.notes || "",
                  })}
                  analysisData={getAllocationData(inv.id)}
                />
              ))}
            </div>
          </>
        ) : (
          <EmptyState
            title={
              Object.keys(filteredCategories).length === 0
                ? t("investments.noActiveInvestments")
                : t("emptyStates.investments.title")
            }
            description={
              Object.keys(filteredCategories).length === 0
                ? t("investments.noTagsAvailable")
                : t("emptyStates.investments.description")
            }
            cta={
              Object.keys(filteredCategories).length === 0
                ? {
                    label: t("sidebar.categories"),
                    onClick: () => navigate("/categories"),
                  }
                : {
                    label: t("investments.addFirstInvestment"),
                    onClick: () => setIsAddOpen(true),
                  }
            }
            secondary={
              Object.keys(filteredCategories).length > 0
                ? {
                    label: t("emptyStates.tryDemoMode"),
                    onClick: () => setShowDemoConfirm(true),
                  }
                : undefined
            }
            footer={
              showDemoConfirm ? (
                <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
              ) : undefined
            }
          />
        )}
      </div>

      {/* Closed Investments */}
      {closedInvestments.length > 0 && (
        <div className="pt-8 border-t border-[var(--surface-light)]">
          <h2 className="text-lg md:text-xl font-bold mb-4 md:mb-6 flex items-center gap-2 text-[var(--text-muted)]">
            {t("investments.closedInvestments")}
            <span className="text-[10px] font-black bg-[var(--surface-light)] px-2 py-0.5 rounded-full">
              {closedInvestments.length}
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-6 opacity-75 grayscale-[0.5]">
            {closedInvestments.map((inv: Investment) => (
              <InvestmentCard
                key={inv.id}
                inv={inv}
                onViewAnalysis={setSelectedAnalysisId}
                onClose={(id: number) =>
                  setCloseForm({ investmentId: id, date: todayISO(), mode: "close" })
                }
                onReopen={reopenMutation.mutate}
                onDelete={deleteMutation.mutate}
                onUpdateBalance={(id: number) =>
                  setBalanceForm({
                    investmentId: id,
                    date: todayISO(),
                    balance: "",
                  })
                }
                onEditCloseDate={(id: number, closedDate?: string) =>
                  setCloseForm({ investmentId: id, date: closedDate || "", mode: "edit" })
                }
                onEdit={(inv: Investment) => setEditForm({
                  investmentId: inv.id,
                  name: inv.name,
                  type: inv.type || "",
                  interest_rate: inv.interest_rate || 0,
                  interest_rate_type: inv.interest_rate_type || "variable",
                  rate_spread: inv.rate_spread ?? 0,
                  notes: inv.notes || "",
                })}
                analysisData={getAllocationData(inv.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Analysis Modal */}
      {selectedAnalysisId != null && (
        <InvestmentAnalysisModal
          investmentId={selectedAnalysisId}
          investment={investments?.find((i: Investment) => i.id === selectedAnalysisId)}
          onClose={() => setSelectedAnalysisId(null)}
        />
      )}

      {/* Update Balance Modal */}
      <Modal
        isOpen={balanceForm.investmentId != null}
        onClose={() =>
          setBalanceForm({ investmentId: null, date: todayISO(), balance: "" })
        }
        title={t("investments.updateBalance")}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6 overflow-y-auto">
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("common.date")}
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
                  {t("investments.currentMarketValue")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder={t("investments.currentMarketValuePlaceholder")}
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
                    date: todayISO(),
                    balance: "",
                  })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
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
                {balanceSnapshotMutation.isPending ? t("investments.saving") : t("common.save")}
              </button>
            </div>
        </div>
      </Modal>

      {/* Close / Edit Close Date Modal */}
      <Modal
        isOpen={closeForm.investmentId != null}
        onClose={() =>
          setCloseForm({ investmentId: null, date: todayISO(), mode: "close" })
        }
        title={
          closeForm.mode === "close"
            ? t("investments.closeInvestment")
            : t("investments.editCloseDate")
        }
        maxWidth="sm"
      >
        <div className="p-4 md:p-6 overflow-y-auto">
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                {t("investments.closeDate")}
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
                  setCloseForm({ investmentId: null, date: todayISO(), mode: "close" })
                }
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
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
                  ? t("investments.saving")
                  : closeForm.mode === "close"
                    ? t("investments.closeInvestment")
                    : t("investments.updateDate")}
              </button>
            </div>
        </div>
      </Modal>

      {/* Edit Investment Modal */}
      <Modal
        isOpen={editForm.investmentId != null}
        onClose={() =>
          setEditForm({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", rate_spread: 0, notes: "" })
        }
        title={t("investments.editInvestment")}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6 overflow-y-auto">
            <div className="space-y-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.name")}
                </label>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>
              {RATE_TYPES.has(editForm.type) && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    {editForm.interest_rate_type === "prime_linked" ? (
                      <div>
                        <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                          {t("investments.spreadVsPrime")}
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          placeholder={t("investments.spreadPlaceholder")}
                          className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                          value={editForm.rate_spread}
                          onChange={(e) => setEditForm({ ...editForm, rate_spread: parseFloat(e.target.value) || 0 })}
                        />
                      </div>
                    ) : (
                      <div>
                        <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                          {t("investments.interestRatePct")}
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                          value={editForm.interest_rate}
                          onChange={(e) => setEditForm({ ...editForm, interest_rate: parseFloat(e.target.value) || 0 })}
                        />
                      </div>
                    )}
                    <div>
                      <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                        {t("investments.rateType")}
                      </label>
                      <select
                        className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                        value={editForm.interest_rate_type}
                        onChange={(e) => setEditForm({ ...editForm, interest_rate_type: e.target.value })}
                      >
                        <option value="variable">{t("investments.variableRate")}</option>
                        <option value="fixed">{t("investments.fixedRate")}</option>
                        <option value="prime_linked">{t("investments.primeLinkedRate")}</option>
                      </select>
                    </div>
                  </div>
                  {editForm.interest_rate_type === "prime_linked" && !!currentRates?.prime && (
                    <p className="text-xs text-sky-400 font-medium">
                      {t("investments.currentPrimeHint", { prime: currentRates.prime })}
                    </p>
                  )}
                </>
              )}
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.notes")}
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
                onClick={() => setEditForm({ investmentId: null, name: "", type: "", interest_rate: 0, interest_rate_type: "variable", rate_spread: 0, notes: "" })}
                className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
              >
                {t("common.cancel")}
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
                      rate_spread: editForm.rate_spread,
                      notes: editForm.notes,
                    },
                  })
                }
                className="flex-[2] py-3 bg-[var(--primary)] rounded-xl text-white font-bold hover:opacity-90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {editMutation.isPending ? t("investments.saving") : t("common.save")}
              </button>
            </div>
        </div>
      </Modal>

      {/* Add Modal */}
      <Modal
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        title={t("investments.newInvestment")}
        titleIcon={<TrendingUp size={20} />}
        maxWidth="lg"
      >
        <div className="p-4 md:p-8 overflow-y-auto">
            {createMutation.isError && (
              <div className="mb-4 md:mb-6 p-3 md:p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-medium animate-in slide-in-from-top-2">
                {(createMutation.error as unknown as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
                  t("investments.failedToCreate")}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 md:gap-4 mb-4 md:mb-6">
              <div className="sm:col-span-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.investmentName")}
                </label>
                <input
                  type="text"
                  placeholder={t("investments.investmentNamePlaceholder")}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newInvestment.name}
                  onChange={(e) =>
                    setNewInvestment({ ...newInvestment, name: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("common.category")}
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
                  placeholder={t("investments.selectCategory")}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("common.tag")}
                </label>
                <SelectDropdown
                  options={newInvestment.category && filteredCategories[newInvestment.category] ? filteredCategories[newInvestment.category].map((tag: string) => ({ label: tag, value: tag })) : []}
                  value={newInvestment.tag}
                  onChange={(val) =>
                    setNewInvestment({ ...newInvestment, tag: val })
                  }
                  placeholder={t("investments.selectTag")}
                  disabled={!newInvestment.category}
                  onCreateNew={async (name) => {
                    const formatted = await createTag(newInvestment.category, name);
                    setNewInvestment({ ...newInvestment, tag: formatted });
                  }}
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.type")}
                </label>
                <SelectDropdown
                  options={[
                    { label: t("investments.types.stocks"), value: "stocks" },
                    { label: t("investments.types.crypto"), value: "crypto" },
                    { label: t("investments.types.bonds"), value: "bonds" },
                    { label: t("investments.types.realEstate"), value: "real_estate" },
                    { label: t("investments.types.pension"), value: "pension" },
                    { label: t("investments.types.brokerageAccount"), value: "brokerage_account" },
                    { label: t("investments.types.other"), value: "other" },
                  ]}
                  value={newInvestment.type}
                  onChange={(val) =>
                    setNewInvestment({ ...newInvestment, type: val })
                  }
                  placeholder={t("investments.selectType")}
                />
              </div>
              {RATE_TYPES.has(newInvestment.type) && (
              <>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.rateType")}
                </label>
                <select
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={newInvestment.interest_rate_type}
                  onChange={(e) =>
                    setNewInvestment({
                      ...newInvestment,
                      interest_rate_type: e.target.value,
                    })
                  }
                >
                  <option value="fixed">{t("investments.fixedRate")}</option>
                  <option value="variable">{t("investments.variableRate")}</option>
                  <option value="prime_linked">{t("investments.primeLinkedRate")}</option>
                </select>
              </div>
              {newInvestment.interest_rate_type === "prime_linked" ? (
                <div>
                  <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                    {t("investments.spreadVsPrime")}
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    placeholder={t("investments.spreadPlaceholder")}
                    className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium"
                    value={newInvestment.rate_spread}
                    onChange={(e) =>
                      setNewInvestment({
                        ...newInvestment,
                        rate_spread:
                          e.target.value === "" ? 0 : parseFloat(e.target.value),
                      })
                    }
                  />
                  {!!currentRates?.prime && (
                    <p className="mt-2 text-xs text-sky-400 font-medium">
                      {t("investments.currentPrimeHint", { prime: currentRates.prime })}
                    </p>
                  )}
                </div>
              ) : (
                <div>
                  <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                    {t("investments.intRate")}
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
              </>
              )}
              <div className="sm:col-span-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("investments.notes")}
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
                {t("common.cancel")}
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
                {createMutation.isPending ? t("investments.creating") : t("investments.createInvestment")}
              </button>
            </div>
        </div>
      </Modal>
    </div>
  );
}
