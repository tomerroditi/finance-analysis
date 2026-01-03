import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Wallet, PiggyBank } from 'lucide-react';
import Plot from 'react-plotly.js';
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

    const { data: categoryData } = useQuery({
        queryKey: ['analytics-category'],
        queryFn: () => analyticsApi.getByCategory().then(res => res.data),
    });

    const { data: trendData } = useQuery({
        queryKey: ['analytics-trend'],
        queryFn: () => analyticsApi.getMonthlyTrend().then(res => res.data),
    });

    const formatCurrency = (val: number) =>
        new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS' }).format(val);

    const chartTheme = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8', family: 'Inter, sans-serif' },
        margin: { t: 40, b: 40, l: 40, r: 20 },
    };

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
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
                    value={overviewLoading ? '...' : (overview?.total_transactions || 0)}
                    icon={PiggyBank}
                    color="bg-purple-500/20 text-purple-400"
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* Monthly Trend Chart */}
                <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
                    <h3 className="text-lg font-bold mb-4">Monthly Income vs Expenses</h3>
                    <div className="h-[350px]">
                        <Plot
                            data={[
                                {
                                    x: trendData?.map((d: any) => d.month),
                                    y: trendData?.map((d: any) => d.salary),
                                    name: 'Salary',
                                    type: 'bar',
                                    marker: { color: '#059669' },
                                },
                                {
                                    x: trendData?.map((d: any) => d.month),
                                    y: trendData?.map((d: any) => d.other_income),
                                    name: 'Other Income',
                                    type: 'bar',
                                    marker: { color: '#34d399' },
                                },
                                {
                                    x: trendData?.map((d: any) => d.month),
                                    y: trendData?.map((d: any) => d.outcome),
                                    name: 'Expenses',
                                    type: 'bar',
                                    marker: { color: '#f43f5e' },
                                },
                            ]}
                            layout={{
                                ...chartTheme,
                                barmode: 'group',
                                autosize: true,
                                height: 350,
                            }}
                            style={{ width: '100%', height: '100%' }}
                            config={{ displayModeBar: false, responsive: true }}
                        />
                    </div>
                </div>

                {/* Category Pie Chart */}
                <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl overflow-hidden">
                    <h3 className="text-lg font-bold mb-4">Expenses by Category</h3>
                    <div className="h-[350px]">
                        <Plot
                            data={[
                                {
                                    values: categoryData?.map((d: any) => d.amount),
                                    labels: categoryData?.map((d: any) => d.category),
                                    type: 'pie',
                                    hole: 0.4,
                                    marker: {
                                        colors: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6366f1']
                                    },
                                },
                            ]}
                            layout={{
                                ...chartTheme,
                                autosize: true,
                                height: 350,
                                showlegend: true,
                                legend: { orientation: 'h', y: -0.2 }
                            }}
                            style={{ width: '100%', height: '100%' }}
                            config={{ displayModeBar: false, responsive: true }}
                        />
                    </div>
                </div>
            </div>

            {/* Latest Data Info */}
            <div className="bg-[var(--surface)] rounded-xl p-6 border border-[var(--surface-light)] flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-semibold mb-1">Data Status</h2>
                    <p className="text-[var(--text-muted)] text-sm">
                        Latest transaction date: {overview?.latest_data_date || 'No data available'}
                    </p>
                </div>
                <div className="text-[var(--primary)] font-bold text-xs uppercase tracking-widest px-3 py-1 bg-[var(--primary)]/10 rounded-full border border-[var(--primary)]/20">
                    Live Updates Active
                </div>
            </div>
        </div>
    );
}
