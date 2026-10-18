import React, { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Tags, X } from "lucide-react";
import { pendingRefundsApi, type PendingRefund } from "../../services/api";
import { Modal } from "../common/Modal";
import { useDialog } from "../../context/DialogContext";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { formatCurrency } from "../../utils/numberFormatting";

const DISMISS_KEY = "fad_refund_tag_mismatch_dismissed";

const tagLabel = (category: string | null, tag: string | null) =>
  [category, tag].filter(Boolean).join(" / ") || "—";

const readDismissed = (): string | null => {
  try {
    return localStorage.getItem(DISMISS_KEY);
  } catch {
    return null;
  }
};

/**
 * Surfaces refunds linked to a purchase under a different category or tag —
 * links made before linking required matching tags — and offers to move each
 * one under its purchase's tag after previewing the change.
 *
 * Dismissing hides the chip until the set of mismatched links changes.
 */
export const RefundTagMismatchNotice: React.FC<{ refunds: PendingRefund[] | undefined }> = ({
  refunds,
}) => {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const { notifySuccess } = useDialog();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [dismissed, setDismissed] = useState<string | null>(readDismissed);

  const { data: mismatches } = useQuery({
    queryKey: qk.pendingRefunds.tagMismatches(),
    queryFn: () => pendingRefundsApi.getTagMismatches().then((res) => res.data),
    // Any tag write on a linked refund can open a mismatch, and those writes
    // invalidate the transactions cache, not this one — re-ask on every visit.
    staleTime: 0,
  });

  const signature = useMemo(
    () => (mismatches ?? []).map((m) => m.link_id).sort((a, b) => a - b).join(","),
    [mismatches],
  );

  const descriptions = useMemo(() => {
    const map = new Map<number, string>();
    refunds?.forEach((r) => map.set(r.id, r.description ?? ""));
    return map;
  }, [refunds]);

  const fixMutation = useMutation({
    mutationFn: () => pendingRefundsApi.fixTagMismatches().then((res) => res.data),
    onSuccess: ({ fixed }) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds });
      queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setPreviewOpen(false);
      notifySuccess(t("transactions.refunds.tagMismatch.fixed", { count: fixed }));
    },
  });

  if (!mismatches?.length || dismissed === signature) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, signature);
    } catch {
      /* per-browser convenience only */
    }
    setDismissed(signature);
  };

  return (
    <>
      <div
        data-testid="refund-tag-mismatch-chip"
        className="mt-2 inline-flex items-center gap-1 rounded-full border border-amber-500/50 bg-amber-500/10 ps-2.5 pe-1 py-0.5 text-[11px] text-amber-300"
      >
        <Tags size={12} className="shrink-0" />
        <button className="hover:underline" onClick={() => setPreviewOpen(true)}>
          {t("transactions.refunds.tagMismatch.chip", { count: mismatches.length })}
        </button>
        <button
          onClick={dismiss}
          aria-label={t("transactions.refunds.tagMismatch.dismiss")}
          className="p-0.5 rounded-full hover:bg-amber-500/20"
        >
          <X size={12} />
        </button>
      </div>
      <Modal
        isOpen={previewOpen}
        onClose={() => setPreviewOpen(false)}
        title={t("transactions.refunds.tagMismatch.title")}
        titleIcon={<Tags className="w-5 h-5 text-amber-400" />}
        maxWidth="lg"
      >
        <p className="text-sm text-[var(--text-muted)] mb-3">
          {t("transactions.refunds.tagMismatch.explain")}
        </p>
        <ul className="space-y-2" data-testid="refund-tag-mismatch-list">
          {mismatches.map((m) => (
            <li
              key={m.link_id}
              className="p-3 rounded-xl border border-[var(--surface-light)] bg-[var(--surface-base)] text-xs"
            >
              <div className="flex justify-between gap-3">
                <span className="font-semibold truncate" dir="auto">
                  {descriptions.get(m.pending_refund_id) ||
                    t("modals.linkRefund.unknownExpense")}
                </span>
                <span className="font-semibold text-emerald-400 shrink-0" dir="ltr">
                  {formatCurrency(m.amount)}
                </span>
              </div>
              <div className="mt-1 text-[var(--text-muted)]" dir="auto">
                {t("transactions.refunds.tagMismatch.move", {
                  from: tagLabel(m.refund_category, m.refund_tag),
                  to: tagLabel(m.purchase_category, m.purchase_tag),
                })}
              </div>
            </li>
          ))}
        </ul>
        {fixMutation.isError && (
          <p role="alert" className="text-xs text-red-400 mt-3">
            {t("transactions.refunds.tagMismatch.failed")}
          </p>
        )}
        <div className="flex justify-end gap-3 mt-4">
          <button
            onClick={() => setPreviewOpen(false)}
            className="px-4 py-2 rounded-lg text-sm font-medium hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={() => fixMutation.mutate()}
            disabled={fixMutation.isPending}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 transition-colors"
          >
            {t("transactions.refunds.tagMismatch.fixAll", { count: mismatches.length })}
          </button>
        </div>
      </Modal>
    </>
  );
};
