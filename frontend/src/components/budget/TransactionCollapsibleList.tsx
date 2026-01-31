import React from "react";
import { TransactionsTable, type Transaction } from "../TransactionsTable";

interface TransactionCollapsibleListProps {
  transactions: Transaction[];
  isOpen: boolean;
  showActions?: boolean;
  onTransactionUpdated?: () => void;
  pendingRefundsMap?: Map<string, any>;
  refundLinksMap?: Map<string, number>;
}

/**
 * Collapsible transaction list for budget views.
 * Wraps TransactionsTable with show/hide logic and styling.
 */
export const TransactionCollapsibleList: React.FC<
  TransactionCollapsibleListProps
> = ({ transactions, isOpen, showActions = false, onTransactionUpdated, pendingRefundsMap, refundLinksMap }) => {
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
      />
    </div>
  );
};
