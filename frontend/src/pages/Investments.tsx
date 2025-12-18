import { useQuery } from '@tanstack/react-query';
import { investmentsApi } from '../services/api';

export function Investments() {
    const { data: investments, isLoading } = useQuery({
        queryKey: ['investments'],
        queryFn: () => investmentsApi.getAll().then(res => res.data),
    });

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold">Investments</h1>
                <p className="text-[var(--text-muted)] mt-1">
                    Track your investments and returns
                </p>
            </div>

            {isLoading ? (
                <div className="text-center text-[var(--text-muted)]">Loading...</div>
            ) : investments?.length === 0 ? (
                <div className="text-center text-[var(--text-muted)]">
                    No investments tracked. Add your first investment to get started.
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {investments?.map((inv: any) => (
                        <div
                            key={inv.id}
                            className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] p-6"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div>
                                    <h3 className="font-semibold text-lg">{inv.name}</h3>
                                    <p className="text-sm text-[var(--text-muted)]">{inv.type}</p>
                                </div>
                                <span className={`px-2 py-1 rounded text-xs ${inv.is_closed ? 'bg-red-500/20 text-red-400' : 'bg-emerald-500/20 text-emerald-400'
                                    }`}>
                                    {inv.is_closed ? 'Closed' : 'Active'}
                                </span>
                            </div>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-[var(--text-muted)]">Category</span>
                                    <span>{inv.category}</span>
                                </div>
                                {inv.interest_rate && (
                                    <div className="flex justify-between">
                                        <span className="text-[var(--text-muted)]">Interest Rate</span>
                                        <span>{inv.interest_rate}%</span>
                                    </div>
                                )}
                                <div className="flex justify-between">
                                    <span className="text-[var(--text-muted)]">Created</span>
                                    <span>{inv.created_date}</span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
