import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Link2, X } from "lucide-react";
import { pendingRefundsApi, type PendingRefund } from "../../services/api";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";
import { LinkRefundModal } from "../modals/LinkRefundModal";

interface PendingRefundsSectionProps {
  pendingRefunds: {
    items: PendingRefund[];
    total_expected: number;
  };
}

export const PendingRefundsSection: React.FC<PendingRefundsSectionProps> = ({
  pendingRefunds,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { items, total_expected } = pendingRefunds;
  const [linkingRefund, setLinkingRefund] = useState<PendingRefund | null>(null);

  if (!items || items.length === 0) {
    return null;
  }

  const handleCancel = async (id: number) => {
    if (!window.confirm(t("budget.confirmCancelRefund"))) return;
    try {
      await pendingRefundsApi.cancel(id);
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
    } catch {
      alert(t("budget.failedCancelRefund"));
    }
  };

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(amount);

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-amber-500/30 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 flex items-center justify-between bg-amber-500/5 border-b border-amber-500/20">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
            <RefreshCw className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">{t("budget.pendingRefunds")}</h3>
            <p className="text-sm text-amber-400">
              {t("budget.expectedBack", { amount: formatCurrency(total_expected) })}
            </p>
          </div>
        </div>
        <span className="px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-sm font-medium">
          {t("budget.pendingCount", { count: items.length })}
        </span>
      </div>

      {/* Items list */}
      <div className="divide-y divide-[var(--surface-light)]">
        {items.map((item) => (
          <div
            key={item.id}
            className="px-5 py-3 flex items-center justify-between hover:bg-[var(--surface-light)]/50 transition-colors"
          >
            <div className="flex flex-col gap-1">
              {/* Top row: Date & Description */}
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-[var(--text-muted)] bg-[var(--surface-light)] px-1.5 py-0.5 rounded">
                  {item.date || "NO DATE"}
                </span>
                <span className="font-medium text-[var(--text-primary)]">
                  {item.description || t("budget.unknownTransaction")}
                </span>
              </div>

              {/* Bottom row: Account, Source info, Notes */}
              <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
                {item.account_name && (
                  <>
                    <span>{item.account_name}</span>
                    <span>•</span>
                  </>
                )}
                <span>
                  {item.provider ? humanizeProvider(item.provider) : humanizeService(item.source_table)}
                </span>
                {item.category && (
                  <>
                    <span>•</span>
                    <span>{item.category}{item.tag ? ` / ${item.tag}` : ""}</span>
                  </>
                )}
                {item.notes && (
                  <>
                    <span>•</span>
                    <span className="italic text-amber-500/80">
                      "{item.notes}"
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-amber-400 font-semibold">
                {formatCurrency(item.expected_amount)}
              </span>
              <button
                className="p-1.5 rounded-md hover:bg-emerald-500/10 text-emerald-400/70 hover:text-emerald-400 transition-colors"
                title={t("budget.linkRefund")}
                onClick={() => setLinkingRefund(item)}
              >
                <Link2 size={16} />
              </button>
              <button
                className="p-1.5 rounded-md hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-colors"
                title={t("common.cancel")}
                onClick={() => handleCancel(item.id)}
              >
                <X size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer note */}
      <div className="px-5 py-3 bg-amber-500/5 border-t border-amber-500/20 text-xs text-[var(--text-muted)]">
        {t("budget.pendingRefundsFooter")}
      </div>

      {linkingRefund && (
        <LinkRefundModal
          isOpen={!!linkingRefund}
          onClose={() => setLinkingRefund(null)}
          pendingRefund={linkingRefund}
        />
      )}
    </div>
  );
};
