import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { formatCurrency } from "../../utils/numberFormatting";
import type { Transaction } from "../../types/transaction";

/** One category's share of the "Other Expenses" catch-all, as the backend sums it. */
export interface OtherExpensesCategory {
  /** `null` groups the uncategorized rows. */
  category: string | null;
  /** Net spend (refunds netted), positive = expense. */
  amount: number;
  count: number;
}

interface Props {
  breakdown: OtherExpensesCategory[];
  transactions: Transaction[];
  /** Renders the transaction list a category row expands to. */
  renderTransactions: (transactions: Transaction[]) => React.ReactNode;
}

const sameCategory = (tx: Transaction, category: string | null) =>
  (tx.category || null) === category;

/**
 * The spend no rule claimed, split by category.
 *
 * The catch-all row only says how much went unbudgeted; this says where it
 * went, so a category that keeps showing up here can be given its own rule.
 * Each bar is the category's share of the catch-all, not of a budget — the
 * catch-all's headroom belongs to all of them together.
 */
export const OtherExpensesBreakdown: React.FC<Props> = ({
  breakdown,
  transactions,
  renderTransactions,
}) => {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<string | null>(null);
  const total = breakdown.reduce((sum, entry) => sum + Math.max(entry.amount, 0), 0);

  if (breakdown.length === 0) return null;

  return (
    <div
      data-testid="other-expenses-breakdown"
      className="border-t border-[var(--surface-light)] px-2 md:px-3 py-1.5 space-y-0.5"
    >
      {breakdown.map((entry) => {
        const key = entry.category ?? "";
        const isOpen = expanded === key;
        const share = total > 0 ? (Math.max(entry.amount, 0) / total) * 100 : 0;
        return (
          <div key={key} data-testid="other-expenses-category">
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setExpanded(isOpen ? null : key)}
              className="w-full grid items-center gap-2 md:gap-3 grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_96px_44px_56px_16px] rounded-lg px-1.5 py-1.5 text-start hover:bg-[var(--surface-light)]/40 transition-colors"
            >
              <span
                className="text-xs font-medium text-[var(--text-default)] truncate"
                dir="auto"
              >
                {entry.category ?? t("common.uncategorized")}
              </span>
              <span className="hidden md:block relative h-1.5 w-full rounded-full bg-[var(--surface-light)] overflow-hidden">
                <span
                  className="absolute inset-y-0 start-0 rounded-full bg-sky-500"
                  style={{ width: `${share}%` }}
                />
              </span>
              <span
                className="text-end font-mono text-xs font-bold whitespace-nowrap"
                dir="ltr"
              >
                {formatCurrency(entry.amount)}
                <span className="md:hidden text-[var(--text-muted)] font-normal">
                  {" · "}
                  {Math.round(share)}%
                </span>
              </span>
              <span
                className="hidden md:block text-end font-mono text-xs text-[var(--text-muted)]"
                dir="ltr"
              >
                {Math.round(share)}%
              </span>
              <span className="hidden md:block text-end text-[10px] text-[var(--text-muted)] whitespace-nowrap">
                {t("budget.otherBreakdown.count", { count: entry.count })}
              </span>
              <ChevronDown
                size={14}
                className={`hidden md:block text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`}
              />
            </button>
            {isOpen &&
              renderTransactions(
                transactions.filter((tx) => sameCategory(tx, entry.category)),
              )}
          </div>
        );
      })}
    </div>
  );
};
