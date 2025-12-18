import { useState, useEffect } from 'react';
import { X, RefreshCw, Smartphone, CheckCircle2, AlertCircle, PlayCircle } from 'lucide-react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { scrapingApi } from '../../services/api';

interface ScrapingManagerProps {
    onClose: () => void;
}

export function ScrapingManager({ onClose }: ScrapingManagerProps) {
    const [tfaCode, setTfaCode] = useState('');
    const [activeTfaService, setActiveTfaService] = useState<string | null>(null);

    const { data: status, refetch: refetchStatus } = useQuery({
        queryKey: ['scraping-status'],
        queryFn: () => scrapingApi.getStatus().then(res => res.data),
        refetchInterval: (query) => {
            const data = query.state.data;
            if (data && (data.is_running || data.waiting_for_2fa?.length > 0)) return 2000;
            return false;
        }
    });

    const startMutation = useMutation({
        mutationFn: (service?: string) => scrapingApi.start(service),
        onSuccess: () => refetchStatus(),
    });

    const tfaMutation = useMutation({
        mutationFn: ({ service, code }: { service: string, code: string }) => scrapingApi.submit2fa(service, code),
        onSuccess: () => {
            setTfaCode('');
            setActiveTfaService(null);
            refetchStatus();
        }
    });

    const clearMutation = useMutation({
        mutationFn: () => scrapingApi.clearStatus(),
        onSuccess: () => refetchStatus(),
    });

    const services = [
        { id: 'max', name: 'MAX (Leumi Card)', color: 'bg-blue-500' },
        { id: 'hapoalim', name: 'Bank Hapoalim', color: 'bg-red-500' },
        { id: 'visa_cal', name: 'Visa CAL', color: 'bg-emerald-500' },
        { id: 'mizrahi', name: 'Bank Mizrahi', color: 'bg-orange-500' },
        { id: 'discount', name: 'Bank Discount', color: 'bg-lime-500' },
    ];

    useEffect(() => {
        if (status?.waiting_for_2fa?.length > 0 && !activeTfaService) {
            setActiveTfaService(status.waiting_for_2fa[0]);
        }
    }, [status, activeTfaService]);

    const isRunning = status?.is_running;
    const isWaiting = status?.waiting_for_2fa?.length > 0;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col">
                <div className="px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/20">
                    <div className="flex items-center gap-3">
                        <RefreshCw className={`text-[var(--primary)] ${isRunning ? 'animate-spin' : ''}`} size={24} />
                        <div>
                            <h2 className="text-xl font-bold text-white">Data Scraper</h2>
                            <p className="text-sm text-[var(--text-muted)]">Import transactions from your financial institutions</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-1 hover:bg-[var(--surface-light)] rounded-lg transition-colors">
                        <X size={20} />
                    </button>
                </div>

                <div className="p-8 space-y-8">
                    {/* Status Section */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className={`p-4 rounded-xl border flex items-center gap-4 ${isRunning ? 'bg-blue-500/10 border-blue-500/30 text-blue-400' : 'bg-slate-500/10 border-slate-500/30 text-slate-400'}`}>
                            <div className={`w-3 h-3 rounded-full ${isRunning ? 'bg-blue-400 animate-pulse' : 'bg-slate-400'}`} />
                            <span className="font-bold text-sm uppercase tracking-wider">{isRunning ? 'Running' : 'Idle'}</span>
                        </div>
                        <div className={`p-4 rounded-xl border flex items-center gap-4 ${isWaiting ? 'bg-amber-500/10 border-amber-500/30 text-amber-400' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'}`}>
                            {isWaiting ? <Smartphone className="animate-bounce" size={18} /> : <CheckCircle2 size={18} />}
                            <span className="font-bold text-sm uppercase tracking-wider">{isWaiting ? '2FA Required' : 'Ready'}</span>
                        </div>
                    </div>

                    {/* 2FA Input Area */}
                    {isWaiting && activeTfaService && (
                        <div className="p-6 rounded-2xl bg-amber-500/10 border border-amber-500/30 animate-in zoom-in-95 duration-300">
                            <div className="flex items-start gap-4 mb-6">
                                <div className="p-3 rounded-xl bg-amber-500/20 text-amber-400">
                                    <Smartphone size={24} />
                                </div>
                                <div className="flex-1">
                                    <h3 className="text-lg font-bold text-white">2FA Verification Needed</h3>
                                    <p className="text-sm text-amber-100/70">A security code has been sent to your device by <span className="text-white font-bold uppercase">{activeTfaService}</span></p>
                                </div>
                            </div>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Enter 6-digit code"
                                    maxLength={10}
                                    className="flex-1 bg-black/40 border border-amber-500/30 rounded-xl px-4 py-3 text-lg font-mono tracking-widest text-center outline-none focus:border-amber-400 text-white"
                                    value={tfaCode}
                                    onChange={(e) => setTfaCode(e.target.value)}
                                />
                                <button
                                    onClick={() => tfaMutation.mutate({ service: activeTfaService, code: tfaCode })}
                                    disabled={!tfaCode || tfaMutation.isPending}
                                    className="px-8 py-3 rounded-xl bg-amber-500 text-black font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
                                >
                                    Verify
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Service Selection */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)]">Available Services</h3>
                            <button
                                onClick={() => startMutation.mutate(undefined)}
                                disabled={isRunning || startMutation.isPending}
                                className="text-xs font-bold text-[var(--primary)] hover:underline flex items-center gap-1 disabled:opacity-50"
                            >
                                <PlayCircle size={14} /> Start All
                            </button>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {services.map(service => (
                                <button
                                    key={service.id}
                                    onClick={() => startMutation.mutate(service.id)}
                                    disabled={isRunning || startMutation.isPending}
                                    className={`flex items-center justify-between p-4 rounded-xl border border-[var(--surface-light)] bg-[var(--surface-base)]/50 hover:border-[var(--primary)]/30 hover:bg-[var(--surface-light)]/20 transition-all group disabled:opacity-50 disabled:cursor-not-allowed`}
                                >
                                    <div className="flex items-center gap-3">
                                        <div className={`w-2 h-8 rounded-full ${service.color}`} />
                                        <span className="font-semibold text-sm">{service.name}</span>
                                    </div>
                                    <PlayCircle size={18} className="text-[var(--text-muted)] group-hover:text-[var(--primary)] opacity-0 group-hover:opacity-100 transition-all" />
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Logs/Status Summary */}
                    {status?.results && Object.keys(status.results).length > 0 && (
                        <div className="space-y-3 pt-6 border-t border-[var(--surface-light)]">
                            <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)]">Recent Results</h3>
                            <div className="space-y-2">
                                {Object.entries(status.results).map(([service, res]: [string, any]) => (
                                    <div key={service} className="flex items-center justify-between p-3 rounded-lg bg-black/20 text-xs">
                                        <span className="font-bold uppercase tracking-tight">{service}</span>
                                        <div className="flex items-center gap-2">
                                            {res.success ? (
                                                <span className="text-emerald-400 font-medium">Successfully fetched {res.count} items</span>
                                            ) : (
                                                <div className="flex items-center gap-1 text-red-400">
                                                    <AlertCircle size={12} />
                                                    <span>{res.error || 'Failed'}</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="p-6 border-t border-[var(--surface-light)] bg-[var(--surface-light)]/10 flex justify-between items-center">
                    <button
                        onClick={() => clearMutation.mutate()}
                        className="text-xs text-[var(--text-danger)] hover:underline"
                    >
                        Clear Status
                    </button>
                    <button
                        onClick={onClose}
                        className="px-8 py-2.5 rounded-xl bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-bold transition-all"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
