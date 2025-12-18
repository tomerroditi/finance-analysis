import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Wallet, PiggyBank } from 'lucide-react';
import { analyticsApi } from '../services/api';

function StatCard({
    title,
    value,
    icon: Icon,
    color
}: {
    title: string;
    value: string | number;
    icon: React.ElementType;
    color: string;
}) {
    return (
        <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)]">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-[var(--text-muted)] text-sm">{title}</p>
                    <p className="text-2xl font-bold mt-1">{value}</p>
                </div>
                <div className={`p-3 rounded-lg ${color}`}>
                    <Icon size={24} />
                </div>
            </div>
        </div>
    );
}

export function Dashboard() {
    const { data: overview, isLoading: overviewLoading } = useQuery({
        queryKey: ['overview'],
        queryFn: () => analyticsApi.getOverview().then(res => res.data),
    });

    const { data: incomeOutcome, isLoading: ioLoading } = useQuery({
        queryKey: ['income-outcome'],
        queryFn: () => analyticsApi.getIncomeOutcome().then(res => res.data),
    });

    const formatCurrency = (val: number) =>
        new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS' }).format(val);

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-3xl font-bold">Dashboard</h1>
                <p className="text-[var(--text-muted)] mt-1">
                    Overview of your financial data
                </p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    title="Total Income"
                    value={ioLoading ? '...' : formatCurrency(incomeOutcome?.total_income || 0)}
                    icon={TrendingUp}
                    color="bg-emerald-500/20 text-emerald-400"
                />
                <StatCard
                    title="Total Expenses"
                    value={ioLoading ? '...' : formatCurrency(incomeOutcome?.total_outcome || 0)}
                    icon={TrendingDown}
                    color="bg-red-500/20 text-red-400"
                />
                <StatCard
                    title="Net Balance"
                    value={ioLoading ? '...' : formatCurrency(incomeOutcome?.net || 0)}
                    icon={Wallet}
                    color="bg-blue-500/20 text-blue-400"
                />
                <StatCard
                    title="Transactions"
                    value={overviewLoading ? '...' : overview?.total_transactions || 0}
                    icon={PiggyBank}
                    color="bg-purple-500/20 text-purple-400"
                />
            </div>

            {/* Latest Data Info */}
            <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)]">
                <h2 className="text-xl font-semibold mb-4">Data Status</h2>
                <p className="text-[var(--text-muted)]">
                    Latest data: {overview?.latest_data_date || 'No data available'}
                </p>
            </div>
        </div>
    );
}
