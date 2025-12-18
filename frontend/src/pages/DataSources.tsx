import { useQuery } from '@tanstack/react-query';
import { credentialsApi } from '../services/api';

export function DataSources() {
    const { data: accounts, isLoading } = useQuery({
        queryKey: ['credentials-accounts'],
        queryFn: () => credentialsApi.getAccounts().then(res => res.data),
    });

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold">Data Sources</h1>
                <p className="text-[var(--text-muted)] mt-1">
                    Manage your connected financial accounts
                </p>
            </div>

            {isLoading ? (
                <div className="text-center text-[var(--text-muted)]">Loading...</div>
            ) : accounts?.length === 0 ? (
                <div className="text-center text-[var(--text-muted)]">
                    No accounts configured. Add credentials to connect your accounts.
                </div>
            ) : (
                <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden">
                    <table className="w-full">
                        <thead className="bg-[var(--surface-light)]">
                            <tr>
                                <th className="px-6 py-4 text-left text-sm font-medium text-[var(--text-muted)]">Service</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-[var(--text-muted)]">Provider</th>
                                <th className="px-6 py-4 text-left text-sm font-medium text-[var(--text-muted)]">Account</th>
                                <th className="px-6 py-4 text-right text-sm font-medium text-[var(--text-muted)]">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-[var(--surface-light)]">
                            {accounts?.map((acc: any, idx: number) => (
                                <tr key={idx} className="hover:bg-[var(--surface-light)]/50">
                                    <td className="px-6 py-4 capitalize">{acc.service}</td>
                                    <td className="px-6 py-4">{acc.provider}</td>
                                    <td className="px-6 py-4">{acc.account_name}</td>
                                    <td className="px-6 py-4 text-right">
                                        <button className="text-red-400 hover:text-red-300 text-sm">
                                            Remove
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
