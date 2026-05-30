import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Plus,
    Play,
    ShieldCheck,
    Edit2,
    Trash2,
    AlertTriangle,
    Search,
    ChevronDown,
    ChevronUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { taggingApi } from "../../services/api";
import type { TaggingRule } from "../../services/api";
import { RuleEditorModal } from "../transactions/RuleEditorModal";
import { useTaggingRules } from "../../hooks/useTaggingRules";
import { useConfirm } from "../../context/DialogContext";

/**
 * Auto-tagging rules management, shown as a section on the Categories page.
 * Lists every rule with per-rule apply / edit / delete actions, a search box,
 * and "New Rule" / "Apply Rules" controls. Rule creation / editing reuses
 * {@link RuleEditorModal}.
 */
export function RulesSection() {
    const { t } = useTranslation();
    const queryClient = useQueryClient();
    const confirm = useConfirm();

    const [collapsed, setCollapsed] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingRule, setEditingRule] = useState<TaggingRule | null>(null);

    const { data: rules, isLoading: rulesLoading } = useTaggingRules();

    const flash = (msg: string) => {
        setSuccess(msg);
        setTimeout(() => setSuccess(null), 3000);
    };

    const deleteMutation = useMutation({
        mutationFn: (id: number) => taggingApi.deleteRule(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tagging-rules"] }),
    });

    const askDeleteRule = async (rule: TaggingRule) => {
        const ok = await confirm({
            title: t("common.deleteTitle"),
            message: rule.name
                ? t("transactions.autoTagging.confirmDeleteNamedRule", { name: rule.name })
                : t("transactions.autoTagging.confirmDeleteRule"),
            confirmLabel: t("common.delete"),
            isDestructive: true,
        });
        if (ok && rule.id != null) deleteMutation.mutate(rule.id);
    };

    const applyMutation = useMutation({
        mutationFn: () => taggingApi.applyRules(),
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            flash(t("transactions.autoTagging.appliedRules", { count: res.data.tagged_count }));
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || t("transactions.autoTagging.applyRulesFailed"));
        },
    });

    const applySingleMutation = useMutation({
        mutationFn: ({ id, overwrite }: { id: number; overwrite: boolean }) => taggingApi.applyRule(id, overwrite),
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            flash(t("transactions.autoTagging.appliedRule", { count: res.data.tagged_count }));
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || t("transactions.autoTagging.applyRuleFailed"));
        },
    });

    const filteredRules = rules?.filter((rule) => {
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

    return (
        <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden">
            {/* Header */}
            <div className="p-4 flex items-center justify-between gap-3 border-b border-[var(--surface-light)] bg-[var(--surface-light)]/10">
                <button
                    onClick={() => setCollapsed((v) => !v)}
                    className="flex items-center gap-2 min-w-0 text-start"
                    aria-expanded={!collapsed}
                >
                    <ShieldCheck className="text-[var(--primary)] shrink-0" size={20} />
                    <div className="min-w-0">
                        <h2 className="font-bold text-base md:text-lg truncate">{t("categories.rules.title")}</h2>
                        <p className="text-xs text-[var(--text-muted)] truncate">{t("categories.rules.subtitle")}</p>
                    </div>
                    {collapsed ? (
                        <ChevronDown size={18} className="text-[var(--text-muted)] shrink-0" />
                    ) : (
                        <ChevronUp size={18} className="text-[var(--text-muted)] shrink-0" />
                    )}
                </button>
                <div className="flex items-center gap-2 shrink-0">
                    <button
                        onClick={openCreate}
                        className="px-3 py-2 flex items-center justify-center gap-2 bg-[var(--primary)]/10 text-[var(--primary)] rounded-xl border border-[var(--primary)]/20 hover:bg-[var(--primary)]/20 font-bold transition-all text-sm"
                    >
                        <Plus size={16} /> <span className="hidden sm:inline">{t("transactions.autoTagging.newRule")}</span>
                    </button>
                    <button
                        onClick={() => applyMutation.mutate()}
                        disabled={applyMutation.isPending}
                        className="px-3 py-2 flex items-center justify-center gap-2 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 font-bold transition-all disabled:opacity-50 text-sm"
                    >
                        <Play size={16} /> <span className="hidden sm:inline">{t("transactions.autoTagging.applyRules")}</span>
                    </button>
                </div>
            </div>

            {!collapsed && (
                <div className="p-4 space-y-4">
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

                    {/* Rules list */}
                    {rulesLoading ? (
                        <div className="text-center text-[var(--text-muted)] py-8">{t("transactions.autoTagging.loadingRules")}</div>
                    ) : filteredRules?.length === 0 ? (
                        <div className="text-center p-8 border border-dashed border-[var(--surface-light)] rounded-xl text-[var(--text-muted)]">
                            {searchQuery ? t("transactions.autoTagging.noMatchingRules") : t("transactions.autoTagging.noRules")}
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                            {filteredRules?.map((rule) => (
                                <div
                                    key={rule.id}
                                    className="group p-3 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)] hover:border-[var(--primary)]/30 transition-all"
                                >
                                    <div className="flex justify-between items-start gap-2 mb-2">
                                        <h4 className="font-bold text-sm truncate" dir="auto">{rule.name}</h4>
                                        <div className="flex gap-1 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity shrink-0">
                                            <button
                                                onClick={() => applySingleMutation.mutate({ id: rule.id, overwrite: false })}
                                                className="p-2 hover:bg-emerald-500/10 text-emerald-400 rounded"
                                                title={t("transactions.autoTagging.applyRuleTitle")}
                                            >
                                                <Play size={16} />
                                            </button>
                                            <button
                                                onClick={() => openEdit(rule)}
                                                className="p-2 hover:bg-blue-500/10 text-blue-400 rounded"
                                                title={t("transactions.autoTagging.editRule")}
                                            >
                                                <Edit2 size={16} />
                                            </button>
                                            <button
                                                onClick={() => askDeleteRule(rule)}
                                                className="p-2 hover:bg-red-500/10 text-red-400 rounded"
                                                title={t("common.delete")}
                                            >
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs flex-wrap">
                                        <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-medium" dir="auto">
                                            {rule.category}
                                        </span>
                                        {rule.tag && (
                                            <span className="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 font-medium" dir="auto">
                                                {rule.tag}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            <RuleEditorModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                editingRule={editingRule}
                onSaved={() => flash(t("transactions.autoTagging.ruleSaved"))}
            />
        </div>
    );
}
