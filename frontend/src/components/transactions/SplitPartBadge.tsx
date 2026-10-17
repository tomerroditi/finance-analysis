import { useState } from "react";
import { Split } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Modal } from "../common/Modal";
import { formatCurrency } from "../../utils/numberFormatting";
import { parentTagLabel, splitSiblings } from "../../utils/splitParts";
import type { Transaction } from "../../types/transaction";

/**
 * The mark on a split part's category: a split moves money onto another tag,
 * and the row alone no longer says what the transaction it was carved from was
 * tagged as. The mark opens that — the parent's tag and amount, and every part
 * of the split this view holds.
 */
export function SplitPartBadge({
  transaction,
  transactions,
}: {
  transaction: Transaction;
  /** The rows the table holds, searched for the other parts of the split. */
  transactions: Transaction[];
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const parentLabel = parentTagLabel(transaction) ?? t("transactions.splitPart.untagged");
  const parts = open ? splitSiblings(transactions, transaction) : [];

  return (
    <>
      <button
        type="button"
        data-testid="split-part-badge"
        onClick={() => setOpen(true)}
        title={t("transactions.splitPart.badgeTitle", { parent: parentLabel })}
        aria-label={t("transactions.splitPart.badgeTitle", { parent: parentLabel })}
        className="shrink-0 inline-flex items-center justify-center rounded-full p-1 text-[var(--primary)] hover:bg-[var(--surface-light)] transition-colors"
      >
        <Split size={12} />
      </button>
      <Modal
        isOpen={open}
        onClose={() => setOpen(false)}
        title={t("transactions.splitPart.title")}
        titleIcon={<Split className="w-5 h-5 text-[var(--primary)]" />}
        maxWidth="md"
      >
        <div data-testid="split-part-details" className="space-y-4 text-sm">
          <div className="rounded-xl border border-[var(--surface-light)] p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">{t("transactions.splitPart.parent")}</div>
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium truncate" dir="auto">
                {parentLabel}
              </span>
              {transaction.parent_amount != null && (
                <span className="font-bold tabular-nums whitespace-nowrap" dir="ltr">
                  {formatCurrency(transaction.parent_amount, 2)}
                </span>
              )}
            </div>
          </div>
          <div>
            <div className="text-xs text-[var(--text-muted)] mb-1">
              {t("transactions.splitPart.parts", { count: parts.length })}
            </div>
            <ul className="divide-y divide-[var(--surface-light)] rounded-xl border border-[var(--surface-light)]">
              {parts.map((part) => (
                <li
                  key={part.unique_id}
                  data-testid="split-part-row"
                  className={`flex items-center justify-between gap-3 px-3 py-2 ${
                    part.unique_id === transaction.unique_id ? "bg-[var(--primary)]/10" : ""
                  }`}
                >
                  <span className="truncate" dir="auto">
                    {part.category || "-"}
                    {part.tag && <span className="text-[var(--text-muted)]"> / {part.tag}</span>}
                  </span>
                  <span className="font-bold tabular-nums whitespace-nowrap" dir="ltr">
                    {formatCurrency(part.amount, 2)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Modal>
    </>
  );
}
