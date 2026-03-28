import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../../hooks/useScrollLock";
import {
    Plus,
    Play,
    ShieldCheck,
    Edit2,
    Trash2,
    AlertTriangle,
    Search,
    ChevronLeft,
    ChevronRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { taggingApi } from "../../services/api";
import type { TaggingRule } from "../../services/api";
import { RuleEditorModal } from "./RuleEditorModal";
import { useAppStore } from "../../stores/appStore";

export function AutoTaggingPanel() {
    const { t } = useTranslation();
    const { autoTaggingPanelOpen, toggleAutoTaggingPanel } = useAppStore();
    const queryClient = useQueryClient();
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");

    // Modal state
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingRule, setEditingRule] = useState<TaggingRule | null>(null);
    useScrollLock(autoTaggingPanelOpen);

    const { data: rules, isLoading: rulesLoading } = useQuery({
        queryKey: ["tagging-rules"],
        queryFn: () => taggingApi.getRules().then(res => res.data)
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => taggingApi.deleteRule(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tagging-rules"] })
    });

    const applyMutation = useMutation({
        mutationFn: () => taggingApi.applyRules(),
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            setSuccess(`Applied rules! ${res.data.tagged_count} tagged.`);
            setTimeout(() => setSuccess(null), 3000);
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || "Failed to apply rules");
        }
    });

    const applySingleMutation = useMutation({
        mutationFn: ({ id, overwrite }: { id: number, overwrite: boolean }) => taggingApi.applyRule(id, overwrite),
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            setSuccess(`Applied rule! ${res.data.tagged_count} tagged.`);
            setTimeout(() => setSuccess(null), 3000);
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || "Failed to apply rule");
        }
    });

    const filteredRules = rules?.filter(rule => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
            rule.name.toLowerCase().includes(q) ||
            rule.category.toLowerCase().includes(q) ||
            (rule.tag && rule.tag.toLowerCase().includes(q))
        );
    });

    const openCreate = () => {
        setEditingRule(null);
        setIsModalOpen(true);
    };

    const openEdit = (rule: TaggingRule) => {
        setEditingRule(rule);
        setIsModalOpen(true);
    };

    const handleModalSaved = () => {
        setSuccess("Rule saved successfully");
        setTimeout(() => setSuccess(null), 3000);
    };

    return (
        <>
            <div className={`shrink-0 z-40 h-[calc(100vh-2rem)] sticky top-4 ms-4 flex-col transition-all duration-300 overflow-hidden hidden md:flex ${
                autoTaggingPanelOpen ? "w-[400px]" : "w-12"
            }`}>
                {autoTaggingPanelOpen ? (
                    <div className="w-[400px] h-full flex flex-col bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl overflow-hidden">
                        {/* Header */}
                        <div className="p-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/10">
                            <div className="flex items-center gap-2">
                                <ShieldCheck className="text-[var(--primary)]" size={20} />
                                <h2 className="font-bold text-lg">{t("transactions.autoTagging.title")}</h2>
                            </div>
                            <button
                                onClick={toggleAutoTaggingPanel}
                                className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
                                title="Collapse panel"
                            >
                                <ChevronRight size={18} />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            {/* Actions */}
                            <div className="space-y-4 mb-4">
                                <div className="flex gap-2">
                                    <button
                                        onClick={openCreate}
                                        className="flex-1 py-2 flex items-center justify-center gap-2 bg-[var(--primary)]/10 text-[var(--primary)] rounded-xl border border-[var(--primary)]/20 hover:bg-[var(--primary)]/20 font-bold transition-all"
                                    >
                                        <Plus size={18} /> {t("transactions.autoTagging.newRule")}
                                    </button>
                                    <button
                                        onClick={() => applyMutation.mutate()}
                                        disabled={applyMutation.isPending}
                                        className="flex-1 py-2 flex items-center justify-center gap-2 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 font-bold transition-all disabled:opacity-50"
                                    >
                                        <Play size={18} /> {t("transactions.autoTagging.applyRules")}
                                    </button>
                                </div>

                                {/* Search */}
                                <div className="relative">
                                    <Search size={16} className="absolute start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                                    <input
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        placeholder={t("transactions.autoTagging.searchRules")}
                                        className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl py-2 ps-9 pe-4 text-sm outline-none focus:border-[var(--primary)] transition-colors placeholder:text-[var(--text-muted)]"
                                    />
                                </div>
                            </div>

                            {/* Messages */}
                            {error && (
                                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl flex items-start gap-3 text-red-400 text-xs">
                                    <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                                    <span>{error}</span>
                                </div>
                            )}
                            {success && (
                                <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-400 text-xs font-bold text-center">
                                    {success}
                                </div>
                            )}

                            {/* Rules List */}
                            <div className="space-y-2">
                                {rulesLoading ? (
                                    <div className="text-center text-[var(--text-muted)] py-8">{t("transactions.autoTagging.loadingRules")}</div>
                                ) : filteredRules?.length === 0 ? (
                                    <div className="text-center p-8 border border-dashed border-[var(--surface-light)] rounded-xl text-[var(--text-muted)]">
                                        {searchQuery ? t("transactions.autoTagging.noMatchingRules") : t("transactions.autoTagging.noRules")}
                                    </div>
                                ) : (
                                    filteredRules?.map((rule: TaggingRule) => (
                                        <div key={rule.id} className="group p-3 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)] hover:border-[var(--primary)]/30 transition-all">
                                            <div className="flex justify-between items-start mb-2">
                                                <h4 className="font-bold text-sm">{rule.name}</h4>
                                                <div className="flex gap-1 opacity-100 md:opacity-0 group-hover:opacity-100 transition-opacity">
                                                    <button
                                                        onClick={() => applySingleMutation.mutate({ id: rule.id, overwrite: false })}
                                                        className="p-1 hover:bg-emerald-500/10 text-emerald-400 rounded"
                                                        title="Apply Rule"
                                                    >
                                                        <Play size={14} />
                                                    </button>
                                                    <button
                                                        onClick={() => openEdit(rule)}
                                                        className="p-1 hover:bg-blue-500/10 text-blue-400 rounded"
                                                    >
                                                        <Edit2 size={14} />
                                                    </button>
                                                    <button
                                                        onClick={() => {
                                                            if (confirm("Delete rule?")) deleteMutation.mutate(rule.id);
                                                        }}
                                                        className="p-1 hover:bg-red-500/10 text-red-400 rounded"
                                                    >
                                                        <Trash2 size={14} />
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 text-xs">
                                                <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium">
                                                    {rule.category}
                                                </span>
                                                {rule.tag && (
                                                    <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 font-medium">
                                                        {rule.tag}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                ) : (
                    /* Collapsed strip */
                    <button
                        onClick={toggleAutoTaggingPanel}
                        className="w-12 h-full flex flex-col items-center justify-center gap-3 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl hover:border-[var(--primary)]/30 transition-colors cursor-pointer group"
                        title="Expand Auto Tagging panel"
                    >
                        <ChevronLeft size={18} className="text-[var(--text-muted)] group-hover:text-[var(--primary)] transition-colors" />
                        <ShieldCheck size={20} className="text-[var(--primary)]" />
                        <span className="text-xs font-bold text-[var(--text-muted)] [writing-mode:vertical-lr] rotate-180 tracking-wider uppercase">
                            {t("transactions.autoTagging.title")}
                        </span>
                    </button>
                )}
            </div>

            {/* Mobile: floating button + full-screen overlay */}
            {!autoTaggingPanelOpen && (
                <button
                    onClick={toggleAutoTaggingPanel}
                    className="md:hidden fixed bottom-20 end-4 z-40 w-12 h-12 rounded-full bg-[var(--primary)] text-white shadow-lg flex items-center justify-center hover:bg-[var(--primary-hover)] transition-colors"
                    title={t("transactions.autoTagging.title")}
                >
                    <ShieldCheck size={22} />
                </button>
            )}
            {autoTaggingPanelOpen && (
                <div className="modal-overlay md:hidden fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200" onClick={toggleAutoTaggingPanel}>
                    <div
                        className="fixed inset-x-0 bottom-0 top-14 bg-[var(--surface)] rounded-t-2xl shadow-xl flex flex-col overflow-hidden animate-in slide-in-from-bottom duration-200"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <div className="p-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/10">
                            <div className="flex items-center gap-2">
                                <ShieldCheck className="text-[var(--primary)]" size={20} />
                                <h2 className="font-bold text-lg">{t("transactions.autoTagging.title")}</h2>
                            </div>
                            <button
                                onClick={toggleAutoTaggingPanel}
                                className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"
                            >
                                <ChevronRight size={18} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 space-y-4">
                            <div className="space-y-4 mb-4">
                                <div className="flex gap-2">
                                    <button onClick={() => { setEditingRule(null); setIsModalOpen(true); }} className="flex-1 py-2 flex items-center justify-center gap-2 bg-[var(--primary)]/10 text-[var(--primary)] rounded-xl border border-[var(--primary)]/20 hover:bg-[var(--primary)]/20 font-bold transition-all">
                                        <Plus size={18} /> {t("transactions.autoTagging.newRule")}
                                    </button>
                                    <button onClick={() => applyMutation.mutate()} disabled={applyMutation.isPending} className="flex-1 py-2 flex items-center justify-center gap-2 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 font-bold transition-all disabled:opacity-50">
                                        <Play size={18} /> {t("transactions.autoTagging.applyAll")}
                                    </button>
                                </div>
                            </div>
                            {rulesLoading ? (
                                <p className="text-center text-[var(--text-muted)] py-8">{t("common.loading")}</p>
                            ) : (rules || []).filter(r => !searchQuery || r.name.toLowerCase().includes(searchQuery.toLowerCase())).map((rule) => (
                                <div key={rule.id} className="bg-[var(--surface-light)]/30 rounded-xl p-3 border border-[var(--surface-light)]">
                                    <div className="flex items-center justify-between mb-1">
                                        <span className="font-semibold text-sm truncate">{rule.name}</span>
                                        <div className="flex items-center gap-1">
                                            <button onClick={() => applySingleMutation.mutate({ id: rule.id!, overwrite: false })} className="p-1 rounded hover:bg-emerald-500/20 text-emerald-400/60 hover:text-emerald-400 transition-colors"><Play size={14} /></button>
                                            <button onClick={() => { setEditingRule(rule); setIsModalOpen(true); }} className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-colors"><Edit2 size={14} /></button>
                                            <button onClick={() => { if (confirm(`Delete rule "${rule.name}"?`)) deleteMutation.mutate(rule.id!); }} className="p-1 rounded hover:bg-rose-500/20 text-rose-400/60 hover:text-rose-400 transition-colors"><Trash2 size={14} /></button>
                                        </div>
                                    </div>
                                    <div className="text-xs text-[var(--text-muted)]">
                                        {rule.category}{rule.tag ? ` / ${rule.tag}` : ""}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Modal */}
            <RuleEditorModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                editingRule={editingRule}
                onSaved={handleModalSaved}
            />
        </>
    );
}
