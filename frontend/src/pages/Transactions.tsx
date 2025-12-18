import { useQuery } from '@tanstack/react-query';
import { useState, useMemo, useEffect } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';
import { transactionsApi } from '../services/api';
import { useAppStore } from '../stores/appStore';

type SortConfig = {
    key: string;
    direction: 'asc' | 'desc' | null;
};

export function Transactions() {
    const { selectedService, setSelectedService } = useAppStore();
    const [sortConfig, setSortConfig] = useState<SortConfig>({ key: 'date', direction: 'desc' });

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [rowsPerPage, setRowsPerPage] = useState(50);

    const { data: transactions, isLoading } = useQuery({
        queryKey: ['transactions', selectedService],
        queryFn: () => transactionsApi.getAll(selectedService === 'all' ? undefined : selectedService).then(res => res.data),
    });

    // Reset to page 1 when filter or sort changes
    useEffect(() => {
        setCurrentPage(1);
    }, [selectedService, sortConfig]);

    const handleSort = (key: string) => {
        let direction: 'asc' | 'desc' | null = 'asc';
        if (sortConfig.key === key) {
            if (sortConfig.direction === 'asc') direction = 'desc';
            else if (sortConfig.direction === 'desc') direction = null;
        }
        setSortConfig({ key, direction });
    };

    const sortedTransactions = useMemo(() => {
        if (!transactions) return [];
        if (!sortConfig.key || !sortConfig.direction) return transactions;

        return [...transactions].sort((a, b) => {
            let aValue = a[sortConfig.key];
            let bValue = b[sortConfig.key];

            // Special handling for amount (numeric)
            if (sortConfig.key === 'amount') {
                aValue = Number(aValue);
                bValue = Number(bValue);
            }

            if (aValue === bValue) return 0;
            if (aValue === null || aValue === undefined) return 1;
            if (bValue === null || bValue === undefined) return -1;

            const comparison = aValue < bValue ? -1 : 1;
            return sortConfig.direction === 'asc' ? comparison : -comparison;
        });
    }, [transactions, sortConfig]);

    // Paginated transactions
    const paginatedTransactions = useMemo(() => {
        const startIndex = (currentPage - 1) * rowsPerPage;
        return sortedTransactions.slice(startIndex, startIndex + rowsPerPage);
    }, [sortedTransactions, currentPage, rowsPerPage]);

    const totalPages = Math.ceil(sortedTransactions.length / rowsPerPage);
    const startRow = (currentPage - 1) * rowsPerPage + 1;
    const endRow = Math.min(currentPage * rowsPerPage, sortedTransactions.length);

    const SortIcon = ({ columnKey }: { columnKey: string }) => {
        if (sortConfig.key !== columnKey || !sortConfig.direction) {
            return <ArrowUpDown size={14} className="ml-1 opacity-20 group-hover:opacity-50" />;
        }
        return sortConfig.direction === 'asc' ?
            <ArrowUp size={14} className="ml-1 text-[var(--primary)]" /> :
            <ArrowDown size={14} className="ml-1 text-[var(--primary)]" />;
    };

    const services = [
        { value: 'all', label: 'All' },
        { value: 'credit_card', label: 'Credit Card' },
        { value: 'bank', label: 'Bank' },
        { value: 'cash', label: 'Cash' },
    ] as const;

    const rowOptions = [10, 50, 100, 500, 1000];

    const headers = [
        { key: 'date', label: 'Date', align: 'left', width: '140px' },
        { key: 'description', label: 'Description', align: 'left', width: 'auto' },
        { key: 'category', label: 'Category', align: 'left', width: '200px' },
        { key: 'tag', label: 'Tag', align: 'left', width: '200px' },
        { key: 'amount', label: 'Amount', align: 'right', width: '160px' },
    ];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold">Transactions</h1>
                    <p className="text-[var(--text-muted)] mt-1">
                        View and manage your transactions
                    </p>
                </div>

                {/* Service filter */}
                <div className="flex gap-2">
                    {services.map(({ value, label }) => (
                        <button
                            key={value}
                            onClick={() => setSelectedService(value)}
                            className={`px-4 py-2 rounded-lg transition-colors ${selectedService === value
                                ? 'bg-[var(--primary)] text-white'
                                : 'bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-light)]'
                                }`}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Transactions Table */}
            <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
                {isLoading ? (
                    <div className="p-8 text-center text-[var(--text-muted)]">Loading...</div>
                ) : sortedTransactions?.length === 0 ? (
                    <div className="p-8 text-center text-[var(--text-muted)]">No transactions found</div>
                ) : (
                    <>
                        <div className="overflow-x-auto">
                            <table className="w-full table-fixed min-w-[800px]">
                                <thead className="bg-[var(--surface-light)]">
                                    <tr>
                                        {headers.map((header) => (
                                            <th
                                                key={header.key}
                                                onClick={() => handleSort(header.key)}
                                                style={{ width: header.width }}
                                                className={`px-4 py-3 text-sm font-medium text-[var(--text-muted)] cursor-pointer group hover:text-white transition-colors ${header.align === 'right' ? 'text-right' : 'text-left'
                                                    }`}
                                            >
                                                <div className={`flex items-center ${header.align === 'right' ? 'justify-end' : 'justify-start'}`}>
                                                    <span className="truncate">{header.label}</span>
                                                    <SortIcon columnKey={header.key} />
                                                </div>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[var(--surface-light)]">
                                    {paginatedTransactions.map((tx: any) => (
                                        <tr key={`${tx.source}_${tx.unique_id}`} className="hover:bg-[var(--surface-light)]/50">
                                            <td className="px-4 py-3 text-sm truncate">{tx.date}</td>
                                            <td className="px-4 py-3 text-sm truncate" title={tx.description}>{tx.description}</td>
                                            <td className="px-4 py-3 text-sm">
                                                <span className="px-2 py-1 rounded-md bg-[var(--surface-light)] text-xs truncate max-w-full inline-block">
                                                    {tx.category || '-'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3 text-sm text-[var(--text-muted)] truncate">{tx.tag || '-'}</td>
                                            <td className={`px-4 py-3 text-sm text-right font-medium whitespace-nowrap ${tx.amount > 0 ? 'text-emerald-400' : 'text-red-400'
                                                }`}>
                                                {new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS' }).format(tx.amount)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {/* Pagination Controls */}
                        <div className="px-4 py-3 bg-[var(--surface-light)]/30 border-t border-[var(--surface-light)] flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <span className="text-sm text-[var(--text-muted)]">
                                    Showing <span className="text-white font-medium">{startRow}</span> to <span className="text-white font-medium">{endRow}</span> of <span className="text-white font-medium">{sortedTransactions.length}</span>
                                </span>

                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-[var(--text-muted)]">Rows per page:</span>
                                    <select
                                        value={rowsPerPage}
                                        onChange={(e) => setRowsPerPage(Number(e.target.value))}
                                        className="bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-sm outline-none focus:border-[var(--primary)]"
                                    >
                                        {rowOptions.map(opt => (
                                            <option key={opt} value={opt}>{opt}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div className="flex items-center gap-1">
                                <button
                                    onClick={() => setCurrentPage(1)}
                                    disabled={currentPage === 1}
                                    className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title="First Page"
                                >
                                    <ChevronsLeft size={20} />
                                </button>
                                <button
                                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                                    disabled={currentPage === 1}
                                    className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title="Previous Page"
                                >
                                    <ChevronLeft size={20} />
                                </button>

                                <span className="px-4 text-sm">
                                    Page <span className="text-white font-medium">{currentPage}</span> of <span className="text-white font-medium">{totalPages}</span>
                                </span>

                                <button
                                    onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                                    disabled={currentPage === totalPages}
                                    className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title="Next Page"
                                >
                                    <ChevronRight size={20} />
                                </button>
                                <button
                                    onClick={() => setCurrentPage(totalPages)}
                                    disabled={currentPage === totalPages}
                                    className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                                    title="Last Page"
                                >
                                    <ChevronsRight size={20} />
                                </button>
                            </div>
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
