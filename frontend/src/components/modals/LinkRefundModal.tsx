import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Link2, Search, Check } from "lucide-react";
import { pendingRefundsApi, transactionsApi, type PendingRefund } from "../../services/api";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { useScrollLock } from "../../hooks/useScrollLock";

interface RefundTransactionInfo {
  id: string | number;
  source: string;
  amount: number;
  description: string;
}

interface LinkRefundModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Mode 1: Linking a refund transaction TO a pending refund (from TransactionsTable)
  refundTransaction?: RefundTransactionInfo;
  // Mode 2: Linking a pending refund TO a refund transaction (from Budget page)
  pendingRefund?: PendingRefund;
}

interface Transaction {
  unique_id?: string;
  id?: number;
  source?: string;
  amount: number;
  description?: string;
  desc?: string;
  date?: string;
  account_name?: string;
  provider?: string;
}

export const LinkRefundModal: React.FC<LinkRefundModalProps> = ({
  isOpen,
  onClose,
  refundTransaction,
  pendingRefund,
}) => {
  const { t } = useTranslation();
  useScrollLock(isOpen);
  const queryClient = useQueryClient();
  const [selectedPendingId, setSelectedPendingId] = useState<number | null>(
    null,
  );
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [linkAmount, setLinkAmount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");

  const isReverseMode = !!pendingRefund && !refundTransaction;

  // Mode 1: Fetch pending refunds if we're linking FROM a refund transaction
  const { data: pendingRefunds, isLoading: isLoadingPending } = useQuery({
    queryKey: ["pendingRefunds"],
    queryFn: async () => {
      const [pending, partial] = await Promise.all([
        pendingRefundsApi.getAll("pending").then((res) => res.data),
        pendingRefundsApi.getAll("partial").then((res) => res.data),
      ]);
      return [...pending, ...partial];
    },
    enabled: isOpen && !!refundTransaction,
  });

  // Mode 2: Fetch transactions if we're linking FROM a pending refund (reverse mode)
  const { data: allTransactions, isLoading: isLoadingTransactions } = useQuery({
    queryKey: ["transactions", "refunds"],
    queryFn: () => transactionsApi.getAll().then((res) => res.data),
    enabled: isOpen && isReverseMode,
    select: (data: Transaction[]) =>
      data
        .filter((txn) => txn.amount > 0)
        .sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "")),
  });

  const isLoading = isReverseMode ? isLoadingTransactions : isLoadingPending;

  const linkMutation = useMutation({
    mutationFn: (params: { pendingId: number; refundId: string | number; refundSource: string; amount: number }) =>
      pendingRefundsApi.linkRefund(params.pendingId, {
        refund_transaction_id: params.refundId,
        refund_source: params.refundSource,
        amount: params.amount,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      onClose();
    },
  });

  if (!isOpen) return null;


  const filteredPending =
    pendingRefunds?.filter((p: PendingRefund) => {
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      return (
        p.description?.toLowerCase().includes(query) ||
        p.notes?.toLowerCase().includes(query) ||
        p.account_name?.toLowerCase().includes(query) ||
        p.provider?.toLowerCase().includes(query) ||
        p.source_table.toLowerCase().includes(query)
      );
    }) || [];

  const filteredTransactions =
    allTransactions?.filter((txn: Transaction) => {
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      const desc = txn.description || txn.desc || "";
      return (
        desc.toLowerCase().includes(query) ||
        txn.account_name?.toLowerCase().includes(query) ||
        txn.provider?.toLowerCase().includes(query) ||
        txn.source?.toLowerCase().includes(query)
      );
    }) || [];

  const handleLink = () => {
    if (isReverseMode) {
      if (!selectedTransaction || !pendingRefund || linkAmount <= 0) return;
      linkMutation.mutate({
        pendingId: pendingRefund.id,
        refundId: selectedTransaction.unique_id || selectedTransaction.id || 0,
        refundSource: selectedTransaction.source || "unknown",
        amount: linkAmount,
      });
    } else {
      if (!selectedPendingId || !refundTransaction || linkAmount <= 0) return;
      linkMutation.mutate({
        pendingId: selectedPendingId,
        refundId: refundTransaction.id,
        refundSource: refundTransaction.source,
        amount: linkAmount,
      });
    }
  };

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div role="dialog" aria-modal="true" aria-labelledby="link-refund-title" className="relative z-10 w-full max-w-[calc(100vw-2rem)] sm:max-w-lg bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-2xl">
        {/* Header */}
        <div className="px-4 md:px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center shrink-0">
              <Link2 className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="min-w-0">
              <h2 id="link-refund-title" className="text-base md:text-lg font-semibold text-white">{t("modals.linkRefund.title")}</h2>
              {refundTransaction && (
                <p className="text-sm text-[var(--text-muted)]">
                  {formatCurrency(refundTransaction.amount)} {t("modals.linkRefund.refundLabel")}
                </p>
              )}
              {pendingRefund && (
                <p className="text-sm text-[var(--text-muted)]">
                  {formatCurrency(pendingRefund.expected_amount)} {t("modals.linkRefund.expectedRefund")}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label={t("common.close")}
            className="p-2 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="px-4 md:px-6 py-4 max-h-[60vh] overflow-y-auto">
          {/* Search */}
          <div className="relative mb-4">
            <Search
              size={16}
              className="absolute start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="text"
              placeholder={isReverseMode ? t("modals.linkRefund.searchTransactions") : t("modals.linkRefund.searchPending")}
              aria-label={isReverseMode ? t("modals.linkRefund.searchTransactions") : t("modals.linkRefund.searchPending")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full ps-10 pe-4 py-2.5 bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
            />
          </div>

          {/* List */}
          {isLoading ? (
            <div className="text-center py-8 text-[var(--text-muted)]">
              {t("modals.linkRefund.loading")}
            </div>
          ) : isReverseMode ? (
            /* Reverse mode: show refund transactions to pick from */
            filteredTransactions.length === 0 ? (
              <div className="text-center py-8 text-[var(--text-muted)]">
                {t("modals.linkRefund.noTransactions")}
              </div>
            ) : (
              <div className="space-y-2">
                {filteredTransactions.map((txn: Transaction) => {
                  const txnKey = txn.unique_id || txn.id || 0;
                  const isSelected = selectedTransaction?.unique_id === txn.unique_id && selectedTransaction?.id === txn.id;
                  return (
                    <button
                      key={txnKey}
                      onClick={() => {
                        setSelectedTransaction(txn);
                        setLinkAmount(
                          Math.min(
                            txn.amount,
                            pendingRefund!.remaining ?? pendingRefund!.expected_amount,
                          ),
                        );
                      }}
                      className={`relative w-full p-4 rounded-xl border text-start transition-all ${
                        isSelected
                          ? "border-emerald-500 bg-emerald-500/10"
                          : "border-[var(--surface-light)] hover:border-[var(--text-muted)] bg-[var(--surface-base)]"
                      }`}
                    >
                      <div className={`flex items-start justify-between gap-4 ${isSelected ? "pe-7" : ""}`}>
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-white truncate mb-0.5">
                            {txn.description || txn.desc || t("modals.linkRefund.unknownExpense")}
                          </div>
                          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                            <span>
                              {txn.provider ? humanizeProvider(txn.provider) : humanizeService(txn.source || "")}
                            </span>
                            <span>•</span>
                            <span>{txn.date || t("modals.linkRefund.noDate")}</span>
                            {txn.account_name && (
                              <>
                                <span>•</span>
                                <span>{txn.account_name}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <div className="text-end shrink-0">
                          <div className="font-bold text-emerald-400">
                            {formatCurrency(txn.amount)}
                          </div>
                        </div>
                      </div>
                      {isSelected && (
                        <div className="absolute end-4 top-1/2 -translate-y-1/2">
                          <Check className="w-5 h-5 text-emerald-400" />
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )
          ) : (
            /* Normal mode: show pending refunds to pick from */
            filteredPending.length === 0 ? (
              <div className="text-center py-8 text-[var(--text-muted)]">
                {t("modals.linkRefund.noPending")}
              </div>
            ) : (
              <div className="space-y-2">
                {filteredPending.map((pending: PendingRefund) => (
                  <button
                    key={pending.id}
                    onClick={() => {
                      setSelectedPendingId(pending.id);
                      setLinkAmount(
                        Math.min(
                          refundTransaction?.amount || 0,
                          pending.remaining || pending.expected_amount,
                        ),
                      );
                    }}
                    className={`relative w-full p-4 rounded-xl border text-start transition-all ${
                      selectedPendingId === pending.id
                        ? "border-emerald-500 bg-emerald-500/10"
                        : "border-[var(--surface-light)] hover:border-[var(--text-muted)] bg-[var(--surface-base)]"
                    }`}
                  >
                    <div className={`flex items-start justify-between gap-4 ${selectedPendingId === pending.id ? "pe-7" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-white truncate mb-0.5">
                          {pending.description || t("modals.linkRefund.unknownExpense")}
                        </div>
                        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                          <span>
                            {pending.provider ? humanizeProvider(pending.provider) : humanizeService(pending.source_table)}
                          </span>
                          <span>•</span>
                          <span>{pending.date || t("modals.linkRefund.noDate")}</span>
                          {pending.account_name && (
                            <>
                              <span>•</span>
                              <span>{pending.account_name}</span>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="text-end shrink-0">
                        <div className="font-bold text-amber-400">
                          {formatCurrency(pending.expected_amount)}
                        </div>
                        {pending.status === "partial" && pending.remaining !== undefined && (
                          <div className="text-xs text-emerald-400">
                            {t("budget.remaining")}: {formatCurrency(pending.remaining)}
                          </div>
                        )}
                      </div>
                    </div>
                    {pending.notes && (
                      <p className="text-sm text-[var(--text-muted)] mt-1 truncate">
                        {pending.notes}
                      </p>
                    )}
                    {selectedPendingId === pending.id && (
                      <div className="absolute end-4 top-1/2 -translate-y-1/2">
                        <Check className="w-5 h-5 text-emerald-400" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            )
          )}

          {/* Link amount input */}
          {(isReverseMode ? selectedTransaction : selectedPendingId) && (
            <div className="mt-4 p-4 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)]">
              <label className="block text-sm font-medium text-[var(--text-muted)] mb-2">
                {t("modals.linkRefund.amountToLink")}
              </label>
              <input
                type="number"
                value={linkAmount}
                onChange={(e) => setLinkAmount(Number(e.target.value))}
                min={0}
                max={isReverseMode
                  ? Math.min(selectedTransaction?.amount || 0, pendingRefund?.remaining ?? pendingRefund?.expected_amount ?? 0)
                  : (() => { const sel = (pendingRefunds || []).find((p: PendingRefund) => p.id === selectedPendingId); return Math.min(refundTransaction?.amount || 0, sel?.remaining ?? sel?.expected_amount ?? Infinity); })()
                }
                step={0.01}
                className="w-full px-4 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-sm text-end font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 md:px-6 py-4 border-t border-[var(--surface-light)] flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleLink}
            disabled={
              (isReverseMode ? !selectedTransaction : !selectedPendingId) || linkAmount <= 0 || linkMutation.isPending
            }
            className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {linkMutation.isPending ? t("modals.linkRefund.linking") : t("modals.linkRefund.title")}
          </button>
        </div>
      </div>
    </div>
  );
};
