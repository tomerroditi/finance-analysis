import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useMemo, useEffect } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Trash2, Split, Edit2, CheckCircle2, X, ShieldCheck, RefreshCw } from 'lucide-react';
import { transactionsApi, taggingApi } from '../services/api';
import { useAppStore } from '../stores/appStore';
import { TransactionEditorModal } from '../components/modals/TransactionEditorModal';
import { SplitTransactionModal } from '../components/modals/SplitTransactionModal';
import { RuleManager } from '../components/modals/RuleManager';
import { ScrapingManager } from '../components/modals/ScrapingManager';

type SortConfig = {
    key: string;
    direction: 'asc' | 'desc' | null;
};

export function Transactions() {
    const { selectedService, setSelectedService } = useAppStore();
    const queryClient = useQueryClient();
    const [sortConfig, setSortConfig] = useState<SortConfig>({ key: 'date', direction: 'desc' });
    const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
    const [includeSplitParents, setIncludeSplitParents] = useState(false);

    // Modal state
    const [editingTransaction, setEditingTransaction] = useState<any>(null);
    const [splittingTransaction, setSplittingTransaction] = useState<any>(null);
    const [showRuleManager, setShowRuleManager] = useState(false);
    const [showScrapingManager, setShowScrapingManager] = useState(false);
    const [isBulkTagging, setIsBulkTagging] = useState(false);
    const [bulkTagData, setBulkTagData] = useState({ category: '', tag: '' });

    // Pagination state
    const [currentPage, setCurrentPage] = useState(1);
    const [rowsPerPage, setRowsPerPage] = useState(50);

    const { data: transactions, isLoading, refetch } = useQuery({
        queryKey: ['transactions', selectedService, includeSplitParents],
        queryFn: () => transactionsApi.getAll(selectedService === 'all' ? undefined : selectedService, includeSplitParents).then(res => res.data),
    });

    const { data: categories } = useQuery({
        queryKey: ['categories'],
        queryFn: () => taggingApi.getCategories().then(res => res.data),
    });

    // Bulk Tag Mutation
    const bulkTagMutation = useMutation({
        mutationFn: (data: any) => transactionsApi.bulkTag(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['transactions'] });
            setSelectedIds(new Set());
            setIsBulkTagging(false);
            setBulkTagData({ category: '', tag: '' });
        }
    });

    // 1. Compute Sorted Transactions
    const sortedTransactions = useMemo(() => {
        if (!transactions) return [];
        if (!sortConfig.key || !sortConfig.direction) return transactions;

        return [...transactions].sort((a, b) => {
            let aValue = a[sortConfig.key];
            let bValue = b[sortConfig.key];

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

    // 2. Compute Paginated Transactions
    const paginatedTransactions = useMemo(() => {
        const startIndex = (currentPage - 1) * rowsPerPage;
        return sortedTransactions.slice(startIndex, startIndex + rowsPerPage);
    }, [sortedTransactions, currentPage, rowsPerPage]);

    // 3. Selection Handlers (MUST be after paginatedTransactions)
    const toggleSelection = (id: string) => {
        const newSelection = new Set(selectedIds);
        if (newSelection.has(id)) {
            newSelection.delete(id);
        } else {
            newSelection.add(id);
        }
        setSelectedIds(newSelection);
    };

    const toggleSelectAll = () => {
        if (selectedIds.size > 0) {
            setSelectedIds(new Set());
        } else {
            const allIds = paginatedTransactions.map((tx: any) => `${tx.source}_${tx.unique_id}`);
            setSelectedIds(new Set(allIds));
        }
    };

    const isAllSelected = useMemo(() => {
        if (paginatedTransactions.length === 0) return false;
        return paginatedTransactions.every((tx: any) => selectedIds.has(`${tx.source}_${tx.unique_id}`));
    }, [paginatedTransactions, selectedIds]);

    // Reset helpers
    useEffect(() => {
        setCurrentPage(1);
        setSelectedIds(new Set());
    }, [selectedService, sortConfig]);

    const handleSort = (key: string) => {
        let direction: 'asc' | 'desc' | null = 'asc';
        if (sortConfig.key === key) {
            if (sortConfig.direction === 'asc') direction = 'desc';
            else if (sortConfig.direction === 'desc') direction = null;
        }
        setSortConfig({ key, direction });
    };

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

    const handleBulkTag = () => {
        if (!bulkTagData.category) return;
        const selectedTxs = transactions.filter((tx: any) => selectedIds.has(`${tx.source}_${tx.unique_id}`));
        const bySource = selectedTxs.reduce((acc: any, tx: any) => {
            if (!acc[tx.source]) acc[tx.source] = [];
            acc[tx.source].push(tx.unique_id);
            return acc;
        }, {});

        Object.entries(bySource).forEach(([source, ids]: [any, any]) => {
            bulkTagMutation.mutate({
                transaction_ids: ids,
                source,
                category: bulkTagData.category,
                tag: bulkTagData.tag
            });
        });
    };

    const handleDelete = async (tx: any) => {
        if (!window.confirm('Are you sure you want to delete this manual transaction?')) return;
        try {
            await transactionsApi.delete(tx.unique_id, tx.source);
            refetch();
        } catch (err) {
            alert('Failed to delete transaction.');
        }
    };

    const handleBulkDelete = async () => {
        if (!window.confirm(`Delete ${selectedIds.size} transactions? Only manual entries will be removed.`)) return;
        const selectedTxs = transactions.filter((tx: any) => selectedIds.has(`${tx.source}_${tx.unique_id}`));
        const manualTxs = selectedTxs.filter((tx: any) => tx.source === 'cash' || tx.source === 'manual_investment');

        try {
            for (const tx of manualTxs) {
                await transactionsApi.delete(tx.unique_id, tx.source);
            }
            refetch();
            setSelectedIds(new Set());
        } catch (err) {
            alert('Partial failure during bulk deletion.');
        }
    };

    const services = [
        { value: 'all', label: 'All' },
        { value: 'credit_card', label: 'Credit Card' },
        { value: 'bank', label: 'Bank' },
        { value: 'cash', label: 'Cash' },
    ] as const;

    const rowOptions = [10, 50, 100, 500, 1000];

    const headers = [
        { key: 'select', label: '', align: 'center', width: '50px', sortable: false },
        { key: 'date', label: 'Date', align: 'left', width: '120px', sortable: true },
        { key: 'description', label: 'Description', align: 'left', width: 'auto', sortable: true },
        { key: 'category', label: 'Category', align: 'left', width: '180px', sortable: true },
        { key: 'tag', label: 'Tag', align: 'left', width: '180px', sortable: true },
        { key: 'amount', label: 'Amount', align: 'right', width: '140px', sortable: true },
        { key: 'actions', label: 'Actions', align: 'center', width: '120px', sortable: false },
    ];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold">Transactions</h1>
                    <div className="flex items-center gap-4 mt-1">
                        <p className="text-[var(--text-muted)]">View and manage your transactions</p>
                        <div className="flex items-center gap-2 px-3 py-1 bg-[var(--surface-light)]/20 rounded-full border border-[var(--surface-light)]">
                            <label className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none" htmlFor="split-parents">Show Split Parents</label>
                            <input
                                id="split-parents"
                                type="checkbox"
                                checked={includeSplitParents}
                                onChange={(e) => setIncludeSplitParents(e.target.checked)}
                                className="w-3 h-3 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                            />
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setShowRuleManager(true)}
                        className="px-4 py-2 rounded-lg bg-[var(--surface)] border border-[var(--surface-light)] text-sm font-semibold hover:border-[var(--primary)] transition-all flex items-center gap-2"
                    >
                        <ShieldCheck size={16} className="text-[var(--primary)]" /> Rules
                    </button>
                    <button
                        onClick={() => setShowScrapingManager(true)}
                        className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-semibold hover:bg-[var(--primary-dark)] shadow-lg shadow-[var(--primary)]/20 transition-all flex items-center gap-2"
                    >
                        <RefreshCw size={16} /> Import Data
                    </button>

                    <div className="w-px h-8 bg-[var(--surface-light)] mx-2" />

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
            </div>

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
                                                onClick={() => header.sortable && handleSort(header.key)}
                                                style={{ width: header.width }}
                                                className={`px-4 py-3 text-sm font-medium text-[var(--text-muted)] ${header.sortable ? 'cursor-pointer group hover:text-white' : ''} transition-colors ${header.align === 'right' ? 'text-right' : header.align === 'center' ? 'text-center' : 'text-left'}`}
                                            >
                                                <div className={`flex items-center ${header.align === 'right' ? 'justify-end' : header.align === 'center' ? 'justify-center' : 'justify-start'}`}>
                                                    {header.key === 'select' ? (
                                                        <input
                                                            type="checkbox"
                                                            checked={isAllSelected}
                                                            onChange={toggleSelectAll}
                                                            className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                                                        />
                                                    ) : (
                                                        <>
                                                            <span className="truncate">{header.label}</span>
                                                            {header.sortable && <SortIcon columnKey={header.key} />}
                                                        </>
                                                    )}
                                                </div>
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-[var(--surface-light)]">
                                    {paginatedTransactions.map((tx: any) => {
                                        const id = `${tx.source}_${tx.unique_id}`;
                                        const isSelected = selectedIds.has(id);
                                        const isManual = tx.source === 'cash' || tx.source === 'manual_investment';

                                        return (
                                            <tr key={id} className={`hover:bg-[var(--surface-light)]/50 transition-colors ${isSelected ? 'bg-[var(--primary)]/5' : ''}`}>
                                                <td className="px-4 py-3 text-center">
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={() => toggleSelection(id)}
                                                        className="rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                                                    />
                                                </td>
                                                <td className="px-4 py-3 text-sm text-[var(--text-muted)] truncate">{tx.date}</td>
                                                <td className="px-4 py-3 text-sm truncate" title={tx.description}>{tx.description}</td>
                                                <td className="px-4 py-3 text-sm">
                                                    <span className="px-2 py-1 rounded-md bg-[var(--surface-light)] text-xs truncate max-w-full inline-block">
                                                        {tx.category || '-'}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-sm text-[var(--text-muted)] truncate">{tx.tag || '-'}</td>
                                                <td className={`px-4 py-3 text-sm text-right font-medium whitespace-nowrap ${tx.amount > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                                    {new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS' }).format(tx.amount)}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center justify-center gap-1">
                                                        <button className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors" title="Edit" onClick={() => setEditingTransaction(tx)}><Edit2 size={14} /></button>
                                                        <button className="p-1.5 rounded-md hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors" title="Split" onClick={() => setSplittingTransaction(tx)}><Split size={14} /></button>
                                                        {isManual && (
                                                            <button className="p-1.5 rounded-md hover:bg-red-500/10 text-red-400/70 hover:text-red-400 transition-colors" title="Delete" onClick={() => handleDelete(tx)}><Trash2 size={14} /></button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>

                        <div className="px-4 py-3 bg-[var(--surface-light)]/30 border-t border-[var(--surface-light)] flex items-center justify-between mt-auto">
                            <div className="flex items-center gap-4">
                                <span className="text-sm text-[var(--text-muted)] whitespace-nowrap">
                                    Showing <span className="text-white font-medium">{startRow}</span> to <span className="text-white font-medium">{endRow}</span> of <span className="text-white font-medium">{sortedTransactions.length}</span>
                                </span>
                                <div className="flex items-center gap-2">
                                    <span className="text-sm text-[var(--text-muted)] whitespace-nowrap">Rows:</span>
                                    <select value={rowsPerPage} onChange={(e) => setRowsPerPage(Number(e.target.value))} className="bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-sm outline-none">
                                        {rowOptions.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div className="flex items-center gap-1">
                                <button onClick={() => setCurrentPage(1)} disabled={currentPage === 1} className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30"><ChevronsLeft size={20} /></button>
                                <button onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))} disabled={currentPage === 1} className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30"><ChevronLeft size={20} /></button>
                                <span className="px-4 text-sm whitespace-nowrap">Page <span className="text-white font-medium">{currentPage}</span> of <span className="text-white font-medium">{totalPages}</span></span>
                                <button onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))} disabled={currentPage === totalPages} className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30"><ChevronRight size={20} /></button>
                                <button onClick={() => setCurrentPage(totalPages)} disabled={currentPage === totalPages} className="p-1 rounded hover:bg-[var(--surface-light)] disabled:opacity-30"><ChevronsRight size={20} /></button>
                            </div>
                        </div>
                    </>
                )}
            </div>

            {selectedIds.size > 0 && (
                <div className="fixed bottom-8 left-1/2 -translate-x-1/2 bg-[var(--surface)] border border-[var(--primary)]/50 rounded-2xl shadow-2xl px-6 py-4 flex items-center gap-6 animate-in fade-in slide-in-from-bottom-4 duration-300 z-40">
                    <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-[var(--primary)] flex items-center justify-center text-sm font-bold shadow-lg shadow-[var(--primary)]/20">{selectedIds.size}</div>
                        <span className="text-sm font-medium">Selected</span>
                    </div>
                    <div className="w-px h-8 bg-[var(--surface-light)]" />
                    <div className="flex items-center gap-3">
                        {isBulkTagging ? (
                            <div className="flex items-center gap-2">
                                <select className="bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm outline-none" value={bulkTagData.category} onChange={(e) => setBulkTagData({ ...bulkTagData, category: e.target.value, tag: '' })}>
                                    <option value="">Category</option>
                                    {categories && Object.keys(categories).map(cat => <option key={cat} value={cat}>{cat}</option>)}
                                </select>
                                <select className="bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm outline-none disabled:opacity-50" value={bulkTagData.tag} onChange={(e) => setBulkTagData({ ...bulkTagData, tag: e.target.value })} disabled={!bulkTagData.category}>
                                    <option value="">Tag</option>
                                    {bulkTagData.category && categories?.[bulkTagData.category]?.map((tag: string) => <option key={tag} value={tag}>{tag}</option>)}
                                </select>
                                <button className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30" onClick={handleBulkTag} disabled={!bulkTagData.category}><CheckCircle2 size={20} /></button>
                                <button className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)]" onClick={() => { setIsBulkTagging(false); setBulkTagData({ category: '', tag: '' }); }}><X size={20} /></button>
                            </div>
                        ) : (
                            <>
                                <button className="px-4 py-2 rounded-lg bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-medium transition-all" onClick={() => setIsBulkTagging(true)}>Tag Selection</button>
                                <button className="px-4 py-2 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-sm font-medium transition-all" onClick={handleBulkDelete}>Delete</button>
                                <button className="px-4 py-2 rounded-lg hover:bg-[var(--surface-light)] text-sm font-medium transition-all" onClick={() => setSelectedIds(new Set())}>Cancel</button>
                            </>
                        )}
                    </div>
                </div>
            )}

            {editingTransaction && <TransactionEditorModal transaction={editingTransaction} onClose={() => setEditingTransaction(null)} onSuccess={() => refetch()} />}
            {splittingTransaction && <SplitTransactionModal transaction={splittingTransaction} onClose={() => setSplittingTransaction(null)} onSuccess={() => refetch()} />}
            {showRuleManager && <RuleManager onClose={() => setShowRuleManager(false)} />}
            {showScrapingManager && <ScrapingManager onClose={() => setShowScrapingManager(false)} />}
        </div>
    );
}
