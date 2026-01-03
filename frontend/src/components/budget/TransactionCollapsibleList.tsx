import React, { useState, useMemo } from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface Transaction {
    id?: any;
    unique_id?: any;
    source?: string;
    desc: string;
    amount: number;
    date: string;
    category: string;
    tag: string;
    provider?: string;
    account_name?: string;
}

interface TransactionCollapsibleListProps {
    transactions: Transaction[];
    isOpen: boolean;
}

export const TransactionCollapsibleList: React.FC<TransactionCollapsibleListProps> = ({
    transactions,
    isOpen,
}) => {
    const [currentPage, setCurrentPage] = useState(1);
    const rowsPerPage = 10;

    // Reset page when closed or transactions change
    React.useEffect(() => {
        if (!isOpen) setCurrentPage(1);
    }, [isOpen, transactions]);

    const totalPages = Math.ceil(transactions.length / rowsPerPage);
    const paginatedTransactions = useMemo(() => {
        const startIndex = (currentPage - 1) * rowsPerPage;
        return transactions.slice(startIndex, startIndex + rowsPerPage);
    }, [transactions, currentPage, rowsPerPage]);

    if (!isOpen) return null;

    return (
        <div className="mt-4 border-t border-[var(--surface-light)] pt-4 animate-in slide-in-from-top-2 fade-in duration-200">
            <div className="overflow-x-auto rounded-lg border border-[var(--surface-light)]">
                <table className="w-full text-sm text-left">
                    <thead className="bg-[var(--surface-light)] text-[var(--text-muted)] font-medium">
                        <tr>
                            <th className="px-4 py-2">Date</th>
                            <th className="px-4 py-2">Account</th>
                            <th className="px-4 py-2">Description</th>
                            <th className="px-4 py-2">Category</th>
                            <th className="px-4 py-2 text-right">Amount</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--surface-light)] bg-[var(--surface-base)]">
                        {paginatedTransactions.map((tx, idx) => (
                            <tr key={idx} className="hover:bg-[var(--surface-light)]/50 transition-colors">
                                <td className="px-4 py-2 whitespace-nowrap text-[var(--text-muted)]">
                                    {new Date(tx.date).toLocaleDateString()}
                                </td>
                                <td className="px-4 py-2 truncate max-w-[150px]" title={`${tx.provider || 'Manual'} - ${tx.account_name}`}>
                                    <div className="flex flex-col">
                                        <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-tight leading-none mb-1">
                                            {tx.provider || (tx.source?.includes('cash') ? 'Cash' : 'Manual')}
                                        </span>
                                        <span className="truncate font-medium text-[var(--text-default)]">{tx.account_name}</span>
                                    </div>
                                </td>
                                <td className="px-4 py-2 text-[var(--text-default)] font-medium truncate max-w-[200px]" title={tx.desc}>
                                    {tx.desc}
                                </td>
                                <td className="px-4 py-2 text-[var(--text-muted)]">
                                    <span className="px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs text-[var(--text-muted)] border border-[var(--surface-light)]">
                                        {tx.category} / {tx.tag}
                                    </span>
                                </td>
                                <td className={`px-4 py-2 text-right font-bold whitespace-nowrap ${tx.amount > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                                    {Math.abs(tx.amount).toFixed(2)}
                                </td>
                            </tr>
                        ))}
                        {transactions.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-4 py-4 text-center text-[var(--text-muted)]">
                                    No transactions found.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-between mt-3 px-2">
                    <span className="text-xs text-[var(--text-muted)]">
                        Page {currentPage} of {totalPages}
                    </span>
                    <div className="flex gap-1">
                        <button
                            onClick={() => setCurrentPage(1)}
                            disabled={currentPage === 1}
                            className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
                        >
                            <ChevronsLeft size={16} />
                        </button>
                        <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                            className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
                        >
                            <ChevronLeft size={16} />
                        </button>
                        <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                            className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
                        >
                            <ChevronRight size={16} />
                        </button>
                        <button
                            onClick={() => setCurrentPage(totalPages)}
                            disabled={currentPage === totalPages}
                            className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
                        >
                            <ChevronsRight size={16} />
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};
