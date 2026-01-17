import { useQuery } from '@tanstack/react-query';
import { useState, useMemo, useEffect } from 'react';
import { ShieldCheck } from 'lucide-react';
import { transactionsApi } from '../services/api';
import { useAppStore } from '../stores/appStore';
import { TransactionsTable } from '../components/TransactionsTable';
import { RuleManager } from '../components/modals/RuleManager';

export function Transactions() {
    const { selectedService, setSelectedService } = useAppStore();
    const [includeSplitParents, setIncludeSplitParents] = useState(false);
    const [onlyUntagged, setOnlyUntagged] = useState(false);
    const [showRuleManager, setShowRuleManager] = useState(false);

    const { data: transactions, isLoading, refetch } = useQuery({
        queryKey: ['transactions', selectedService, includeSplitParents],
        queryFn: () => transactionsApi.getAll(selectedService === 'all' ? undefined : selectedService, includeSplitParents).then(res => res.data),
    });

    // Filter for untagged only
    const filteredTransactions = useMemo(() => {
        if (!transactions) return [];
        if (!onlyUntagged) return transactions;
        return transactions.filter((tx: any) => !tx.tag || tx.tag === '-');
    }, [transactions, onlyUntagged]);

    // Reset when filters change
    useEffect(() => {
        // Handled by TransactionsTable internally
    }, [selectedService, onlyUntagged]);

    const services = [
        { value: 'all', label: 'All' },
        { value: 'credit_cards', label: 'Credit Card' },
        { value: 'banks', label: 'Bank' },
        { value: 'cash', label: 'Cash' },
    ] as const;

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
                        <div className="flex items-center gap-2 px-3 py-1 bg-[var(--surface-light)]/20 rounded-full border border-[var(--surface-light)]">
                            <label className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none" htmlFor="untagged-only">Only Untagged</label>
                            <input
                                id="untagged-only"
                                type="checkbox"
                                checked={onlyUntagged}
                                onChange={(e) => setOnlyUntagged(e.target.checked)}
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

            <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden p-4">
                {isLoading ? (
                    <div className="p-8 text-center text-[var(--text-muted)]">Loading...</div>
                ) : (
                    <TransactionsTable
                        transactions={filteredTransactions}
                        showSelection
                        showBulkActions
                        showActions
                        showDelete
                        showFilter
                        rowsPerPage={50}
                        rowsPerPageOptions={[10, 50, 100, 500, 1000]}
                        onTransactionUpdated={() => refetch()}
                    />
                )}
            </div>

            {showRuleManager && <RuleManager onClose={() => setShowRuleManager(false)} />}
        </div>
    );
}
