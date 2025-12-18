import { useQuery } from '@tanstack/react-query';
import { budgetApi } from '../services/api';
import { useAppStore } from '../stores/appStore';

export function Budget() {
    const { selectedYear, selectedMonth, setSelectedYear, setSelectedMonth } = useAppStore();

    const { data: rules, isLoading } = useQuery({
        queryKey: ['budget-rules', selectedYear, selectedMonth],
        queryFn: () => budgetApi.getRulesByMonth(selectedYear, selectedMonth).then(res => res.data),
    });

    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold">Budget Management</h1>
                    <p className="text-[var(--text-muted)] mt-1">
                        Set and track your monthly budgets
                    </p>
                </div>

                {/* Month/Year selector */}
                <div className="flex gap-4">
                    <select
                        value={selectedMonth}
                        onChange={(e) => setSelectedMonth(Number(e.target.value))}
                        className="px-4 py-2 rounded-lg bg-[var(--surface)] border border-[var(--surface-light)] text-white"
                    >
                        {months.map((month, idx) => (
                            <option key={idx} value={idx + 1}>{month}</option>
                        ))}
                    </select>
                    <select
                        value={selectedYear}
                        onChange={(e) => setSelectedYear(Number(e.target.value))}
                        className="px-4 py-2 rounded-lg bg-[var(--surface)] border border-[var(--surface-light)] text-white"
                    >
                        {[2023, 2024, 2025].map(year => (
                            <option key={year} value={year}>{year}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Budget Rules */}
            <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] p-6">
                {isLoading ? (
                    <div className="text-center text-[var(--text-muted)]">Loading...</div>
                ) : rules?.length === 0 ? (
                    <div className="text-center text-[var(--text-muted)]">
                        No budget rules for this month. Click "Add Rule" to create one.
                    </div>
                ) : (
                    <div className="space-y-4">
                        {rules?.map((rule: any) => (
                            <div
                                key={rule.id}
                                className="flex items-center justify-between p-4 bg-[var(--surface-light)] rounded-lg"
                            >
                                <div>
                                    <p className="font-medium">{rule.name}</p>
                                    <p className="text-sm text-[var(--text-muted)]">{rule.category}</p>
                                </div>
                                <div className="text-right">
                                    <p className="font-bold text-lg">
                                        {new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS' }).format(rule.amount)}
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
