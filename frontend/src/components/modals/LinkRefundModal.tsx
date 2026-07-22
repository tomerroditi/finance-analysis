import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Link2, Search, Check } from "lucide-react";
import {
  pendingRefundsApi,
  transactionsApi,
  type PendingRefund,
  type RefundSource,
} from "../../services/api";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { useScrollLock } from "../../hooks/useScrollLock";
import type { Transaction } from "../../types/transaction";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";

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

const txKey = (source: string | undefined, id: string | number | undefined) =>
  `${source ?? ""}_${id ?? ""}`;

export const LinkRefundModal: React.FC<LinkRefundModalProps> = ({
  isOpen,
  onClose,
  refundTransaction,
  pendingRefund,
}) => {
  const { t } = useTranslation();
  useScrollLock(isOpen);
  const queryClient = useQueryClient();
  const qk = useQueryKeys();
  const [selectedPendingId, setSelectedPendingId] = useState<number | null>(
    null,
  );
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [linkAmount, setLinkAmount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");

  const isReverseMode = !!pendingRefund && !refundTransaction;

  // Mode 1: Fetch pending refunds if we're linking FROM a refund transaction
  const { data: pendingRefunds, isLoading: isLoadingPending } = useQuery({
    queryKey: qk.pendingRefunds.active(),
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
    queryKey: qk.transactions.list(undefined, false),
    queryFn: () => transactionsApi.getAll().then((res) => res.data),
    enabled: isOpen && isReverseMode,
    select: (data: Transaction[]) =>
      data
        .filter((txn) => txn.amount > 0)
        .sort((a, b) => (b.date ?? "").localeCompare(a.date ?? "")),
  });

  // Both modes: allocation state of every refund transaction already in use,
  // so the same transaction can fund several refunds without over-allocating.
  const { data: refundSources } = useQuery({
    queryKey: qk.pendingRefunds.sources(),
    queryFn: () => pendingRefundsApi.getRefundSources().then((res) => res.data),
    enabled: isOpen,
  });

  const allocatedMap = useMemo(() => {
    const map = new Map<string, number>();
    refundSources?.forEach((src: RefundSource) => {
      map.set(
        txKey(src.refund_source, src.refund_transaction_id),
        src.total_allocated,
      );
    });
    return map;
  }, [refundSources]);

  const availableFor = (source: string | undefined, id: string | number | undefined, amount: number) =>
    Math.max(0, amount - (allocatedMap.get(txKey(source, id)) ?? 0));

  // Mode 1: how much of the given refund transaction is still unallocated
  const givenTxnAvailable = refundTransaction
    ? availableFor(refundTransaction.source, refundTransaction.id, refundTransaction.amount)
    : 0;

  const pendingRemaining = (p: PendingRefund | undefined | null) =>
    p ? (p.remaining ?? p.expected_amount) : 0;

  const isLoading = isReverseMode ? isLoadingTransactions : isLoadingPending;

  const linkMutation = useMutation({
    mutationFn: (params: { pendingId: number; refundId: string | number; refundSource: string; amount: number }) =>
      pendingRefundsApi.linkRefund(params.pendingId, {
        refund_transaction_id: params.refundId,
        refund_source: params.refundSource,
        amount: params.amount,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds });
      onClose();
    },
  });

  if (!isOpen) return null;

  const EPS = 0.005;

  /** Amount-match suggestion: a pending refund is suggested for the given
   *  transaction when its remaining expectation equals what's available. */
  const isPendingSuggested = (p: PendingRefund) =>
    !!refundTransaction && Math.abs(pendingRemaining(p) - givenTxnAvailable) < EPS;

  const filteredPending = (
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
    }) || []
  ).sort(
    (a, b) => Number(isPendingSuggested(b)) - Number(isPendingSuggested(a)),
  );

  /** Amount-match suggestion: a transaction is suggested for the pending
   *  refund when its available (or full) amount equals the remaining
   *  expectation, and it isn't dated before the marked expense. */
  const isTxnSuggested = (txn: Transaction) => {
    if (!pendingRefund) return false;
    const rem = pendingRemaining(pendingRefund);
    const avail = availableFor(txn.source, txn.unique_id ?? txn.id, txn.amount);
    const amountMatches =
      Math.abs(avail - rem) < EPS || Math.abs(txn.amount - rem) < EPS;
    if (!amountMatches) return false;
    if (pendingRefund.date && txn.date && txn.date < pendingRefund.date) {
      return false;
    }
    return true;
  };

  const filteredTransactions = (
    allTransactions?.filter((txn: Transaction) => {
      // Skip transactions whose refund money is fully allocated already
      if (availableFor(txn.source, txn.unique_id ?? txn.id, txn.amount) <= EPS) {
        return false;
      }
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      const desc = txn.description || txn.desc || "";
      return (
        desc.toLowerCase().includes(query) ||
        txn.account_name?.toLowerCase().includes(query) ||
        txn.provider?.toLowerCase().includes(query) ||
        txn.source?.toLowerCase().includes(query)
      );
    }) || []
  ).sort((a, b) => Number(isTxnSuggested(b)) - Number(isTxnSuggested(a)));

  const suggestedTxnCount = filteredTransactions.filter(isTxnSuggested).length;
  const suggestedPendingCount = filteredPending.filter(isPendingSuggested).length;

  const groupHeader = (text: string, starred: boolean) => (
    <div className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)] mt-3 first:mt-0 mb-1.5 px-0.5">
      {starred && <span className="text-emerald-400">★ </span>}
      {text}
    </div>
  );

  const selectedTxnAvailable = selectedTransaction
    ? availableFor(
        selectedTransaction.source,
        selectedTransaction.unique_id ?? selectedTransaction.id,
        selectedTransaction.amount,
      )
    : 0;

  const maxLinkAmount = isReverseMode
    ? Math.min(selectedTxnAvailable, pendingRemaining(pendingRefund))
    : (() => {
        const sel = (pendingRefunds || []).find(
          (p: PendingRefund) => p.id === selectedPendingId,
        );
        return sel ? Math.min(givenTxnAvailable, pendingRemaining(sel)) : givenTxnAvailable;
      })();

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
                  {givenTxnAvailable < refundTransaction.amount
                    ? t("modals.linkRefund.availableOf", {
                        available: formatCurrency(givenTxnAvailable),
                        total: formatCurrency(refundTransaction.amount),
                      })
                    : `${formatCurrency(refundTransaction.amount)} ${t("modals.linkRefund.refundLabel")}`}
                </p>
              )}
              {pendingRefund && (
                <p className="text-sm text-[var(--text-muted)]">
                  {formatCurrency(pendingRemaining(pendingRefund))} {t("modals.linkRefund.expectedRefund")}
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
                {filteredTransactions.map((txn: Transaction, idx: number) => {
                  const key = txKey(txn.source, txn.unique_id ?? txn.id);
                  const available = availableFor(txn.source, txn.unique_id ?? txn.id, txn.amount);
                  const partiallyUsed = available < txn.amount;
                  const suggested = isTxnSuggested(txn);
                  const isSelected = selectedTransaction?.unique_id === txn.unique_id && selectedTransaction?.id === txn.id;
                  return (
                    <React.Fragment key={key}>
                      {idx === 0 && suggested &&
                        groupHeader(
                          t("modals.linkRefund.suggestedHeader", {
                            amount: formatCurrency(pendingRemaining(pendingRefund)),
                          }),
                          true,
                        )}
                      {suggestedTxnCount > 0 && idx === suggestedTxnCount &&
                        groupHeader(t("modals.linkRefund.allIncoming"), false)}
                    <button
                      data-testid={suggested ? "suggested-candidate" : "candidate"}
                      onClick={() => {
                        setSelectedTransaction(txn);
                        setLinkAmount(
                          Math.round(
                            Math.min(available, pendingRemaining(pendingRefund)) * 100,
                          ) / 100,
                        );
                      }}
                      className={`relative w-full p-4 rounded-xl border text-start transition-all ${
                        isSelected
                          ? "border-emerald-500 bg-emerald-500/10"
                          : suggested
                            ? "border-emerald-500/45 hover:border-emerald-400 bg-[var(--surface-base)]"
                            : "border-[var(--surface-light)] hover:border-[var(--text-muted)] bg-[var(--surface-base)]"
                      }`}
                    >
                      <div className={`flex items-start justify-between gap-4 ${isSelected ? "pe-7" : ""}`}>
                        <div className="flex-1 min-w-0">
                          <div className="font-semibold text-white truncate mb-0.5" dir="auto">
                            {txn.description || txn.desc || t("modals.linkRefund.unknownExpense")}
                            {suggested && (
                              <span className="ms-2 align-middle inline-block text-[9px] font-bold uppercase tracking-wide text-emerald-400 border border-emerald-500/55 bg-emerald-500/10 rounded-full px-1.5 py-px">
                                {t("modals.linkRefund.suggestedBadge")}
                              </span>
                            )}
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
                          {partiallyUsed && (
                            <div className="text-xs text-amber-400">
                              {t("modals.linkRefund.availableShort", {
                                amount: formatCurrency(available),
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                      {isSelected && (
                        <div className="absolute end-4 top-1/2 -translate-y-1/2">
                          <Check className="w-5 h-5 text-emerald-400" />
                        </div>
                      )}
                    </button>
                    </React.Fragment>
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
                {filteredPending.map((pending: PendingRefund, idx: number) => (
                  <React.Fragment key={pending.id}>
                    {idx === 0 && isPendingSuggested(pending) &&
                      groupHeader(t("modals.linkRefund.suggestedPendingHeader"), true)}
                    {suggestedPendingCount > 0 && idx === suggestedPendingCount &&
                      groupHeader(t("modals.linkRefund.allPending"), false)}
                  <button
                    data-testid={isPendingSuggested(pending) ? "suggested-candidate" : "candidate"}
                    onClick={() => {
                      setSelectedPendingId(pending.id);
                      setLinkAmount(
                        Math.round(
                          Math.min(givenTxnAvailable, pendingRemaining(pending)) * 100,
                        ) / 100,
                      );
                    }}
                    className={`relative w-full p-4 rounded-xl border text-start transition-all ${
                      selectedPendingId === pending.id
                        ? "border-emerald-500 bg-emerald-500/10"
                        : isPendingSuggested(pending)
                          ? "border-emerald-500/45 hover:border-emerald-400 bg-[var(--surface-base)]"
                          : "border-[var(--surface-light)] hover:border-[var(--text-muted)] bg-[var(--surface-base)]"
                    }`}
                  >
                    <div className={`flex items-start justify-between gap-4 ${selectedPendingId === pending.id ? "pe-7" : ""}`}>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-white truncate mb-0.5" dir="auto">
                          {pending.description || t("modals.linkRefund.unknownExpense")}
                          {isPendingSuggested(pending) && (
                            <span className="ms-2 align-middle inline-block text-[9px] font-bold uppercase tracking-wide text-emerald-400 border border-emerald-500/55 bg-emerald-500/10 rounded-full px-1.5 py-px">
                              {t("modals.linkRefund.suggestedBadge")}
                            </span>
                          )}
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
                      <p className="text-sm text-[var(--text-muted)] mt-1 truncate" dir="auto">
                        {pending.notes}
                      </p>
                    )}
                    {selectedPendingId === pending.id && (
                      <div className="absolute end-4 top-1/2 -translate-y-1/2">
                        <Check className="w-5 h-5 text-emerald-400" />
                      </div>
                    )}
                  </button>
                  </React.Fragment>
                ))}
              </div>
            )
          )}

          {/* Link amount input */}
          {(isReverseMode ? selectedTransaction : selectedPendingId) && (
            <div className="mt-4 p-4 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)]">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-[var(--text-muted)]">
                  {t("modals.linkRefund.amountToLink")}
                </label>
                <span className="text-xs text-[var(--text-muted)]">
                  {t("modals.linkRefund.maxAmount", {
                    amount: formatCurrency(maxLinkAmount),
                  })}
                </span>
              </div>
              <input
                type="number"
                value={linkAmount}
                onChange={(e) => setLinkAmount(Number(e.target.value))}
                min={0}
                max={maxLinkAmount}
                step={0.01}
                className="w-full px-4 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-sm text-end font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
              {linkAmount > maxLinkAmount + 0.005 && (
                <p className="text-xs text-red-400 mt-1.5">
                  {t("modals.linkRefund.amountTooHigh", {
                    amount: formatCurrency(maxLinkAmount),
                  })}
                </p>
              )}
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
              (isReverseMode ? !selectedTransaction : !selectedPendingId) ||
              linkAmount <= 0 ||
              linkAmount > maxLinkAmount + 0.005 ||
              linkMutation.isPending
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
