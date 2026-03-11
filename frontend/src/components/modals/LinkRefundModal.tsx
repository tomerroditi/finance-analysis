import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Link2, Search, Check } from "lucide-react";
import { pendingRefundsApi, type PendingRefund } from "../../services/api";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";

interface LinkRefundModalProps {
  isOpen: boolean;
  onClose: () => void;
  // Linking a refund transaction TO a pending refund
  refundTransaction?: {
    id: string | number;
    source: string;
    amount: number;
    description: string;
  };
}

export const LinkRefundModal: React.FC<LinkRefundModalProps> = ({
  isOpen,
  onClose,
  refundTransaction,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedPendingId, setSelectedPendingId] = useState<number | null>(
    null,
  );
  const [linkAmount, setLinkAmount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");

  // Fetch pending refunds if we're linking FROM a refund transaction
  const { data: pendingRefunds, isLoading } = useQuery({
    queryKey: ["pendingRefunds"],
    queryFn: () => pendingRefundsApi.getAll("pending").then((res) => res.data),
    enabled: isOpen && !!refundTransaction,
  });

  const linkMutation = useMutation({
    mutationFn: (pendingId: number) =>
      pendingRefundsApi.linkRefund(pendingId, {
        refund_transaction_id: refundTransaction!.id,
        refund_source: refundTransaction!.source,
        amount: linkAmount,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      queryClient.invalidateQueries({ queryKey: ["pendingRefunds"] });
      onClose();
    },
  });

  if (!isOpen) return null;

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(amount);

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

  const handleLink = () => {
    if (!selectedPendingId || !refundTransaction || linkAmount <= 0) return;
    linkMutation.mutate(selectedPendingId);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
              <Link2 className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-white">{t("modals.linkRefund.title")}</h2>
              {refundTransaction && (
                <p className="text-sm text-[var(--text-muted)]">
                  {formatCurrency(refundTransaction.amount)} refund
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4 max-h-[60vh] overflow-y-auto">
          {/* Search */}
          <div className="relative mb-4">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="text"
              placeholder={t("modals.linkRefund.searchPending")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
            />
          </div>

          {/* Pending refunds list */}
          {isLoading ? (
            <div className="text-center py-8 text-[var(--text-muted)]">
              {t("modals.linkRefund.loading")}
            </div>
          ) : filteredPending.length === 0 ? (
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
                  className={`w-full p-4 rounded-xl border text-start transition-all ${
                    selectedPendingId === pending.id
                      ? "border-emerald-500 bg-emerald-500/10"
                      : "border-[var(--surface-light)] hover:border-[var(--text-muted)] bg-[var(--surface-base)]"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
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
                    <div className="text-right shrink-0">
                      <div className="font-bold text-amber-400">
                        {formatCurrency(pending.expected_amount)}
                      </div>
                    </div>
                  </div>
                  {pending.notes && (
                    <p className="text-sm text-[var(--text-muted)] mt-1 truncate">
                      {pending.notes}
                    </p>
                  )}
                  {(pending.remaining ?? pending.expected_amount) !==
                    pending.expected_amount && (
                    <p className="text-xs text-emerald-400 mt-1">
                      {formatCurrency(pending.remaining ?? 0)} {t("modals.split.remaining").toLowerCase()}
                    </p>
                  )}
                  {selectedPendingId === pending.id && (
                    <div className="absolute right-4 top-1/2 -translate-y-1/2">
                      <Check className="w-5 h-5 text-emerald-400" />
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* Link amount input */}
          {selectedPendingId && (
            <div className="mt-4 p-4 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)]">
              <label className="block text-sm font-medium text-[var(--text-muted)] mb-2">
                {t("modals.linkRefund.amountToLink")}
              </label>
              <input
                type="number"
                value={linkAmount}
                onChange={(e) => setLinkAmount(Number(e.target.value))}
                min={0}
                max={refundTransaction?.amount}
                step={0.01}
                className="w-full px-4 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg text-sm text-right font-mono focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-[var(--surface-light)] flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={handleLink}
            disabled={
              !selectedPendingId || linkAmount <= 0 || linkMutation.isPending
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
