import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Split } from "lucide-react";
import { RecentTransactionsFeed } from "../dashboard/RecentTransactionsSection";
import type { Transaction } from "../../types/transaction";
import {
  taggingApi,
  type PendingRefund,
  type RefundLink,
  type BudgetMonthOverride,
} from "../../services/api";
import { useQueryKeys } from "../../hooks/useQueryKeys";

interface TransactionCollapsibleListProps {
  transactions: Transaction[];
  isOpen: boolean;
  onTransactionUpdated?: () => void;
  pendingRefundsMap?: Map<string, PendingRefund>;
  refundLinksMap?: Map<string, RefundLink[]>;
  // Monthly-budget month override props
  budgetMonthOverridesMap?: Map<string, BudgetMonthOverride>;
  budgetViewYear?: number;
  budgetViewMonth?: number;
  // Split parents filter props
  showSplitParentsFilter?: boolean;
  includeSplitParents?: boolean;
  onIncludeSplitParentsChange?: (value: boolean) => void;
}

/**
 * Collapsible transaction list for budget views.
 * Renders the dashboard's recent-transactions feed (date-grouped rows that
 * mount in batches as the list scrolls) instead of a paginated table.
 */
export const TransactionCollapsibleList: React.FC<
  TransactionCollapsibleListProps
> = ({
  transactions,
  isOpen,
  onTransactionUpdated,
  pendingRefundsMap,
  refundLinksMap,
  budgetMonthOverridesMap,
  budgetViewYear,
  budgetViewMonth,
  showSplitParentsFilter = false,
  includeSplitParents = false,
  onIncludeSplitParentsChange,
}) => {
    const { t } = useTranslation();
    const qk = useQueryKeys();
    const { data: categoryIcons } = useQuery({
      queryKey: qk.tagging.icons(),
      queryFn: () => taggingApi.getIcons().then((res) => res.data),
      enabled: isOpen,
    });

    if (!isOpen) return null;

    return (
      <div data-testid="budget-tx-list" className="mt-4 border-t border-[var(--surface-light)] pt-4 animate-in slide-in-from-top-2 fade-in duration-200">
        <RecentTransactionsFeed
          embedded
          transactions={transactions}
          categoryIcons={categoryIcons}
          isLoading={false}
          onTransactionUpdated={onTransactionUpdated}
          pendingRefundsMap={pendingRefundsMap}
          refundLinksMap={refundLinksMap}
          budgetMonth={
            budgetViewYear != null && budgetViewMonth != null
              ? { overrides: budgetMonthOverridesMap }
              : undefined
          }
          filterExtras={
            showSplitParentsFilter && (
              <button
                type="button"
                onClick={() => onIncludeSplitParentsChange?.(!includeSplitParents)}
                aria-pressed={includeSplitParents}
                aria-label={t("transactions.filters.showSplitParents")}
                title={t("transactions.filters.showSplitParents")}
                className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
                  includeSplitParents
                    ? "bg-[var(--primary)]/20 text-[var(--primary)]"
                    : "text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)]"
                }`}
              >
                <Split size={13} className="shrink-0" />
                <span className="hidden sm:inline">{t("transactions.filters.showSplitParents")}</span>
              </button>
            )
          }
        />
      </div>
    );
  };
