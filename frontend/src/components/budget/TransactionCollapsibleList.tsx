import React, { useState, useMemo } from 'react';
import {
    ChevronLeft,
    ChevronRight,
    ChevronsLeft,
    ChevronsRight,
    ChevronUp,
    ChevronDown,
    Search,
    X,
} from 'lucide-react';

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

type SortKey = 'date' | 'account' | 'desc' | 'category' | 'amount';
type SortDirection = 'asc' | 'desc';

interface SortConfig {
    key: SortKey;
    direction: SortDirection;
}

export const TransactionCollapsibleList: React.FC<TransactionCollapsibleListProps> = ({
    transactions,
    isOpen,
}) => {
    const [currentPage, setCurrentPage] = useState(1);
    const [sortConfig, setSortConfig] = useState<SortConfig>({ key: 'date', direction: 'desc' });
    const [filterText, setFilterText] = useState('');
    const rowsPerPage = 10;

    // Reset page when closed or transactions change
    React.useEffect(() => {
        if (!isOpen) {
            setCurrentPage(1);
            setFilterText('');
        }
    }, [isOpen, transactions]);

    // Reset page when filter changes
    React.useEffect(() => {
        setCurrentPage(1);
    }, [filterText]);

    // Filter transactions
    const filteredTransactions = useMemo(() => {
        if (!filterText.trim()) return transactions;
        const lowerFilter = filterText.toLowerCase();
        return transactions.filter(tx =>
            (tx.desc ?? '').toLowerCase().includes(lowerFilter) ||
            (tx.category ?? '').toLowerCase().includes(lowerFilter) ||
            (tx.tag ?? '').toLowerCase().includes(lowerFilter) ||
            (tx.provider ?? '').toLowerCase().includes(lowerFilter) ||
            (tx.account_name ?? '').toLowerCase().includes(lowerFilter)
        );
    }, [transactions, filterText]);

    // Sort transactions
    const sortedTransactions = useMemo(() => {
        const sorted = [...filteredTransactions];
        sorted.sort((a, b) => {
            let aVal: string | number;
            let bVal: string | number;

            switch (sortConfig.key) {
                case 'date':
                    aVal = new Date(a.date).getTime();
                    bVal = new Date(b.date).getTime();
                    break;
                case 'account':
                    aVal = `${a.provider || ''} ${a.account_name || ''}`.toLowerCase();
                    bVal = `${b.provider || ''} ${b.account_name || ''}`.toLowerCase();
                    break;
                case 'desc':
                    aVal = a.desc.toLowerCase();
                    bVal = b.desc.toLowerCase();
                    break;
                case 'category':
                    aVal = `${a.category} ${a.tag}`.toLowerCase();
                    bVal = `${b.category} ${b.tag}`.toLowerCase();
                    break;
                case 'amount':
                    aVal = Math.abs(a.amount);
                    bVal = Math.abs(b.amount);
                    break;
                default:
                    return 0;
            }

            if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });
        return sorted;
    }, [filteredTransactions, sortConfig]);

    const totalPages = Math.ceil(sortedTransactions.length / rowsPerPage);
    const paginatedTransactions = useMemo(() => {
        const startIndex = (currentPage - 1) * rowsPerPage;
        return sortedTransactions.slice(startIndex, startIndex + rowsPerPage);
    }, [sortedTransactions, currentPage, rowsPerPage]);

    const handleSort = (key: SortKey) => {
        setSortConfig(prev => ({
            key,
            direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
        }));
    };

    const SortableHeader: React.FC<{ label: string; sortKey: SortKey; className?: string }> = ({
        label,
        sortKey,
        className = '',
    }) => {
        const isActive = sortConfig.key === sortKey;
        return (
            <th
                className={`px-4 py-2 cursor-pointer select-none hover:bg-[var(--surface)]/50 transition-colors ${className}`}
                onClick={() => handleSort(sortKey)}
            >
                <div className={`flex items-center gap-1 ${className.includes('text-right') ? 'justify-end' : ''}`}>
                    <span>{label}</span>
                    <span className={`transition-opacity ${isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                        {isActive && sortConfig.direction === 'asc' ? (
                            <ChevronUp size={14} />
                        ) : (
                            <ChevronDown size={14} />
                        )}
                    </span>
                </div>
            </th>
        );
    };

    if (!isOpen) return null;

    return (
        <div className="mt-4 border-t border-[var(--surface-light)] pt-4 animate-in slide-in-from-top-2 fade-in duration-200">
            {/* Filter Input */}
            <div className="mb-3 flex items-center gap-2">
                <div className="relative flex-1 max-w-xs">
                    <Search
                        size={14}
                        className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                    />
                    <input
                        type="text"
                        value={filterText}
                        onChange={e => setFilterText(e.target.value)}
                        placeholder="Filter transactions..."
                        className="w-full pl-8 pr-8 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg focus:outline-none focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
                    />
                    {filterText && (
                        <button
                            onClick={() => setFilterText('')}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
                        >
                            <X size={14} />
                        </button>
                    )}
                </div>
                {filterText && (
                    <span className="text-xs text-[var(--text-muted)]">
                        {filteredTransactions.length} of {transactions.length} transactions
                    </span>
                )}
            </div>

            <div className="overflow-x-auto rounded-lg border border-[var(--surface-light)]">
                <table className="w-full text-sm text-left">
                    <thead className="bg-[var(--surface-light)] text-[var(--text-muted)] font-medium">
                        <tr className="group">
                            <SortableHeader label="Date" sortKey="date" />
                            <SortableHeader label="Account" sortKey="account" />
                            <SortableHeader label="Description" sortKey="desc" />
                            <SortableHeader label="Category" sortKey="category" />
                            <SortableHeader label="Amount" sortKey="amount" className="text-right" />
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--surface-light)] bg-[var(--surface-base)]">
                        {paginatedTransactions.map((tx, idx) => (
                            <tr key={tx.unique_id || tx.id || idx} className="hover:bg-[var(--surface-light)]/50 transition-colors">
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
                        {sortedTransactions.length === 0 && (
                            <tr>
                                <td colSpan={5} className="px-4 py-4 text-center text-[var(--text-muted)]">
                                    {filterText ? 'No matching transactions.' : 'No transactions found.'}
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
