import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { transactionsApi, cashBalancesApi, type PendingRefund, type RefundLink } from "../services/api";
import { useCashBalances } from "../hooks/useCashBalances";
import { useAppStore } from "../stores/appStore";
import { TransactionsTable } from "../components/TransactionsTable";
import RefundsView from "../components/transactions/RefundsView";
import { pendingRefundsApi } from "../services/api";
import { Plus, Trash2, DollarSign, X } from "lucide-react";
import { Skeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";

import { TransactionFormModal } from "../components/modals/TransactionFormModal";
import { formatCurrency } from "../utils/numberFormatting";
import { useConfirm } from "../context/DialogContext";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";

function CashBalancesCard({ queryClient }: { queryClient: ReturnType<typeof useQueryClient> }) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [newAccountName, setNewAccountName] = useState("");
  const [newBalance, setNewBalance] = useState("");

  const { data: balances = [], isLoading } = useCashBalances();

  // Run migration on first load
  const migrationMutation = useMutation({
    mutationFn: () => cashBalancesApi.migrate().then((res) => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.cashBalances });
    },
  });

  useEffect(() => {
    migrationMutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Set balance mutation
  const setBalanceMutation = useMutation({
    mutationFn: (data: { account_name: string; balance: number }) =>
      cashBalancesApi.setBalance(data).then((res) => res.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.cashBalances });
      setEditingId(null);
    },
  });

  // Delete balance mutation
  const deleteMutation = useMutation({
    mutationFn: (accountName: string) =>
      cashBalancesApi.delete(accountName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.cashBalances });
    },
  });

  const handleEdit = (accountName: string, currentBalance: number) => {
    setEditingId(accountName);
    setEditValue(currentBalance.toString());
  };

  const handleSaveBalance = (accountName: string) => {
    const balanceNum = parseFloat(editValue);
    if (!isNaN(balanceNum) && balanceNum >= 0) {
      setBalanceMutation.mutate({
        account_name: accountName,
        balance: balanceNum,
      });
    }
  };

  const handleAddAccount = () => {
    const balanceNum = parseFloat(newBalance);
    if (newAccountName.trim() && !isNaN(balanceNum) && balanceNum >= 0) {
      setBalanceMutation.mutate({
        account_name: newAccountName.trim(),
        balance: balanceNum,
      });
      setNewAccountName("");
      setNewBalance("");
      setShowAddForm(false);
    }
  };


  return (
    <div className="bg-[var(--surface)] rounded-xl p-4 md:p-6 border border-[var(--surface-light)] mb-4 md:mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[var(--text)] font-semibold flex items-center gap-2">
          <span className="text-xl">💵</span> {t("dashboard.cashBalances")}
        </h3>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors"
          title={t("tooltips.addCashEnvelope")}
        >
          <Plus size={20} />
        </button>
      </div>

      {isLoading ? (
        <Skeleton variant="text" lines={3} className="py-2" />
      ) : balances.length === 0 ? (
        <div className="text-center py-8">
          <p className="text-[var(--text-muted)] text-sm">
            {t("transactions.noCashAccounts")}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {balances.map((balance) => (
            <div
              key={balance.id}
              className="flex items-center justify-between bg-[var(--surface-light)] rounded-lg p-3 hover:bg-opacity-80 transition-colors"
            >
              <span className="text-[var(--text)] font-medium">
                {balance.account_name}
              </span>
              <div className="flex items-center gap-3">
                {editingId === balance.account_name ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="w-32 px-2 py-1 bg-[var(--input-bg)] border border-[var(--input-border)] rounded text-[var(--text)] text-end"
                      placeholder="0"
                      min="0"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveBalance(balance.account_name)}
                      className="px-2 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-sm transition-colors"
                    >
                      {t("common.save")}
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="px-2 py-1 bg-[var(--surface)] hover:bg-[var(--surface-light)] text-[var(--text)] rounded text-sm transition-colors"
                    >
                      {t("common.cancel")}
                    </button>
                  </div>
                ) : (
                  <>
                    <span className="text-[var(--text-muted)] text-sm min-w-24 text-end">
                      {formatCurrency(balance.balance)}
                    </span>
                    <button
                      onClick={() =>
                        handleEdit(balance.account_name, balance.balance)
                      }
                      className="p-1.5 hover:bg-[var(--surface)] rounded transition-colors"
                      title={t("tooltips.editBalance")}
                    >
                      <DollarSign size={16} className="text-amber-500" />
                    </button>
                    <button
                      onClick={async () => {
                        const ok = await confirm({
                          title: t("tooltips.deleteEnvelope"),
                          message: t("transactions.confirmDeleteEnvelope", { name: balance.account_name }),
                          confirmLabel: t("common.delete"),
                          isDestructive: true,
                        });
                        if (ok) deleteMutation.mutate(balance.account_name);
                      }}
                      className="p-1.5 hover:bg-[var(--surface)] rounded transition-colors"
                      title={t("tooltips.deleteEnvelope")}
                    >
                      <Trash2 size={16} className="text-red-500" />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showAddForm && (
        <div className="mt-4 bg-[var(--surface-light)] rounded-lg p-4 space-y-3">
          <div>
            <label className="block text-[var(--text-muted)] text-xs font-bold mb-1">
              {t("transactions.envelopeName")}
            </label>
            <input
              type="text"
              value={newAccountName}
              onChange={(e) => setNewAccountName(e.target.value)}
              placeholder={t("transactions.envelopeNamePlaceholder")}
              className="w-full px-3 py-2 bg-[var(--input-bg)] border border-[var(--input-border)] rounded text-[var(--text)]"
              onKeyPress={(e) => {
                if (e.key === "Enter") handleAddAccount();
              }}
            />
          </div>
          <div>
            <label className="block text-[var(--text-muted)] text-xs font-bold mb-1">
              {t("transactions.currentBalance")}
            </label>
            <input
              type="number"
              value={newBalance}
              onChange={(e) => setNewBalance(e.target.value)}
              placeholder="0"
              className="w-full px-3 py-2 bg-[var(--input-bg)] border border-[var(--input-border)] rounded text-[var(--text)]"
              min="0"
              onKeyPress={(e) => {
                if (e.key === "Enter") handleAddAccount();
              }}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleAddAccount}
              className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-medium transition-colors"
            >
              {t("transactions.addEnvelope")}
            </button>
            <button
              onClick={() => setShowAddForm(false)}
              className="px-4 py-2 bg-[var(--surface)] hover:bg-[var(--surface-light)] text-[var(--text)] rounded transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function Transactions() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { selectedService, setSelectedService } = useAppStore();
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [filterOnlyUntagged, setFilterOnlyUntagged] = useState(false);
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const qk = useQueryKeys();

  const {
    data: transactions,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: qk.transactions.list(
      selectedService === "all" ? undefined : selectedService,
      includeSplitParents,
    ),
    queryFn: () =>
      transactionsApi
        .getAll(
          selectedService === "all" ? undefined : selectedService,
          includeSplitParents,
        )
        .then((res) => res.data),
    enabled: selectedService !== "refunds",
  });

  // Fetch pending refunds to know which transactions are already marked
  const { data: pendingRefunds, refetch: refetchPending } = useQuery({
    queryKey: qk.pendingRefunds.all(),
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  // Create a map of pending refunds by source ID for quick lookup
  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, PendingRefund>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: PendingRefund) => {
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  // A refund transaction may fund multiple pending refunds — collect every
  // link per transaction key.
  const refundLinksMap = useMemo(() => {
    const map = new Map<string, RefundLink[]>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: PendingRefund) => {
      if (pr.links) {
        pr.links.forEach((link: RefundLink) => {
          const key = `${link.refund_source}_${link.refund_transaction_id}`;
          const existing = map.get(key);
          if (existing) {
            existing.push(link);
          } else {
            map.set(key, [link]);
          }
        });
      }
    });
    return map;
  }, [pendingRefunds]);

  // Refetch both when actions happen
  const refreshAll = () => {
    refetch();
    refetchPending();
    // Invalidate cash balances when transactions change (they recalculate on backend)
    queryClient.invalidateQueries({ queryKey: qkPrefix.cashBalances });
  };

  const services = [
    { value: "all", label: t("common.all") },
    { value: "credit_cards", label: t("services.creditCard") },
    { value: "banks", label: t("services.bank") },
    { value: "cash", label: t("services.cash") },
    { value: "manual_investments", label: t("services.investment") },
    { value: "refunds", label: t("dashboard.refunds") },
  ] as const;

  return (
    <div className="relative">
      <div className="space-y-4 md:space-y-6 min-w-0">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="flex items-center gap-2 md:gap-4 overflow-x-auto scrollbar-auto-hide pb-1">
            <div className="flex gap-1.5 md:gap-2 items-center">
              {services.map(({ value, label }) => (
                <div key={value} className="flex items-center gap-1 md:gap-2">
                  {value === "refunds" && (
                    <div className="w-px h-6 bg-[var(--surface-light)] mx-0.5 md:mx-1" />
                  )}
                  <button
                    onClick={() => setSelectedService(value as "all" | "credit_cards" | "banks" | "cash" | "manual_investments" | "refunds")}
                    className={`px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-colors text-sm whitespace-nowrap ${selectedService === value
                      ? "bg-[var(--primary)] text-white"
                      : "bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-light)]"
                      }`}
                  >
                    {label}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden p-2 md:p-4">
          {selectedService === "refunds" ? (
            <RefundsView />
          ) : isLoading ? (
            <div className="p-8 space-y-4">
              <Skeleton variant="text" lines={1} className="w-48" />
              <Skeleton variant="card" className="h-64" />
            </div>
          ) : selectedService === "all" && (transactions?.length ?? 0) === 0 ? (
            <EmptyState
              title={t("emptyStates.transactions.title")}
              description={t("emptyStates.transactions.description")}
              steps={[
                {
                  title: t("emptyStates.connectStep.title"),
                  description: t("emptyStates.connectStep.description"),
                },
                {
                  title: t("emptyStates.scrapeStep.title"),
                  description: t("emptyStates.scrapeStep.description"),
                },
                {
                  title: t("emptyStates.analyseStep.title"),
                  description: t("emptyStates.analyseStep.description"),
                },
              ]}
              cta={{
                label: t("emptyStates.connectAccounts"),
                onClick: () => navigate("/data-sources"),
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
          ) : (
            <>
              {selectedService === "cash" && <CashBalancesCard queryClient={queryClient} />}
              {(() => {
                const uncategorizedCount = transactions?.filter(
                  (t: { category?: string }) => !t.category || t.category === "Uncategorized"
                ).length ?? 0;
                return uncategorizedCount > 0 && (
                  <button
                    onClick={() => setFilterOnlyUntagged(true)}
                    className="w-full bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-2.5 text-sm text-amber-400 hover:bg-amber-500/20 transition-colors text-start mb-4"
                  >
                    <strong>{t("transactions.uncategorizedCount", { count: uncategorizedCount })}</strong> — {t("transactions.clickToFilter")}
                  </button>
                );
              })()}
              <TransactionsTable
                transactions={transactions || []}
                showSelection
                showBulkActions
                showActions
                showDelete
                showFilter
                showSplitParentsFilter
                includeSplitParents={includeSplitParents}
                onIncludeSplitParentsChange={setIncludeSplitParents}
                rowsPerPage={100}
                rowsPerPageOptions={[10, 50, 100, 500, 1000]}
                onTransactionUpdated={refreshAll}
                pendingRefundsMap={pendingRefundsMap}
                refundLinksMap={refundLinksMap}
                onlyUntagged={filterOnlyUntagged}
                onAddTransaction={
                  (selectedService === "cash" || selectedService === "manual_investments")
                    ? () => setIsCreateModalOpen(true)
                    : undefined
                }
              />
            </>
          )}
        </div>
      </div>

      <TransactionFormModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        service={
          (selectedService === "cash" || selectedService === "manual_investments")
            ? (selectedService as "cash" | "manual_investments")
            : undefined
        }
        onSuccess={refreshAll}
      />
    </div>
  );
}
