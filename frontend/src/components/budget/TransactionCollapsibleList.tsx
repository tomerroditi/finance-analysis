import React from "react";
import { TransactionsTable } from "../TransactionsTable";
import type { Transaction } from "../../types/transaction";
import { type PendingRefund, type BudgetMonthOverride } from "../../services/api";

interface TransactionCollapsibleListProps {
  transactions: Transaction[];
  isOpen: boolean;
  showActions?: boolean;
  onTransactionUpdated?: () => void;
  pendingRefundsMap?: Map<string, PendingRefund>;
  refundLinksMap?: Map<string, number>;
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
 * Wraps TransactionsTable with show/hide logic and styling.
 */
export const TransactionCollapsibleList: React.FC<
  TransactionCollapsibleListProps
> = ({
  transactions,
  isOpen,
  showActions = false,
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
    if (!isOpen) return null;

    return (
      <div className="mt-4 border-t border-[var(--surface-light)] pt-4 animate-in slide-in-from-top-2 fade-in duration-200">
        <TransactionsTable
          transactions={transactions}
          showSelection={showActions}
          showBulkActions={showActions}
          showActions={showActions}
          showFilter
          compact
          rowsPerPage={10}
          onTransactionUpdated={onTransactionUpdated}
          pendingRefundsMap={pendingRefundsMap}
          refundLinksMap={refundLinksMap}
          budgetMonthOverridesMap={budgetMonthOverridesMap}
          budgetViewYear={budgetViewYear}
          budgetViewMonth={budgetViewMonth}
          showSplitParentsFilter={showSplitParentsFilter}
          includeSplitParents={includeSplitParents}
          onIncludeSplitParentsChange={onIncludeSplitParentsChange}
        />
      </div>
    );
  };
