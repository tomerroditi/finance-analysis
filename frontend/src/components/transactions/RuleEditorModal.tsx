import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../../hooks/useScrollLock";
import { X, Save, Loader2, AlertTriangle } from "lucide-react";
import { taggingApi } from "../../services/api";
import type { TaggingRule, ConditionNode } from "../../services/api";
import { useTranslation } from "react-i18next";
import { RuleBuilder } from "./RuleBuilder";
import { ResizableSplitPane } from "../common/ResizableSplitPane";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { useTaggingRules } from "../../hooks/useTaggingRules";

interface RuleEditorModalProps {
    isOpen: boolean;
    onClose: () => void;
    editingRule?: TaggingRule | null;
    onSaved?: () => void;
}

const EMPTY_CONDITIONS: ConditionNode = {
    type: "AND",
    subconditions: [
        { type: "CONDITION", field: "description", operator: "contains", value: "" }
    ]
};

export function RuleEditorModal({ isOpen, onClose, editingRule, onSaved }: RuleEditorModalProps) {
    const { t } = useTranslation();
    const queryClient = useQueryClient();
    useScrollLock(isOpen);
    const { createCategory, createTag } = useCategoryTagCreate();

    // Form state
    const [category, setCategory] = useState("");
    const [tag, setTag] = useState("");
    const [conditions, setConditions] = useState<ConditionNode>(EMPTY_CONDITIONS);
    const [error, setError] = useState<string | null>(null);
    const [mobileTab, setMobileTab] = useState<"rule" | "matches">("rule");

    const { data: categories } = useCategories() as { data: Record<string, string[]> | undefined };
    const { data: existingRules } = useTaggingRules();

    // Build set of tags that already have rules (excluding the rule being edited)
    const takenTags = new Set(
        (existingRules || [])
            .filter(r => !editingRule || r.id !== editingRule.id)
            .map(r => `${r.category}::${r.tag}`)
    );

    // Filter categories to only those with at least one available (unruled) tag
    const availableCategories = categories
        ? Object.keys(categories).filter(cat =>
            (categories[cat] || []).some(t => !takenTags.has(`${cat}::${t}`))
        )
        : [];

    // Filter tags to only those without an existing rule
    const availableTags = category && categories
        ? (categories[category] || []).filter(t => !takenTags.has(`${category}::${t}`))
        : [];

    const name = tag ? `Auto: ${category} - ${tag}` : "";

    // Initialize form when editing
     
    useEffect(() => {
        if (editingRule) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setCategory(editingRule.category);
             
            setTag(editingRule.tag);
             
            setConditions(editingRule.conditions);
        } else {
             
            setCategory("");
             
            setTag("");
             
            setConditions(EMPTY_CONDITIONS);
        }

        setError(null);

        setMobileTab("rule");
    }, [editingRule, isOpen]);

    // Debounced conditions for preview
    const [debouncedConditions, setDebouncedConditions] = useState<ConditionNode>(conditions);
    useEffect(() => {
        const timeout = setTimeout(() => setDebouncedConditions(conditions), 300);
        return () => clearTimeout(timeout);
    }, [conditions]);

    // Preview query
    const { data: preview, isLoading: previewLoading } = useQuery({
        queryKey: ["rule-preview", debouncedConditions],
        queryFn: () => taggingApi.previewRule(debouncedConditions, 50).then(res => res.data),
        enabled: isOpen && hasValidCondition(debouncedConditions),
        staleTime: 5000,
    });

    // Mutations
    const createMutation = useMutation({
        mutationFn: (payload: Omit<TaggingRule, "id">) => taggingApi.createRule(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            onSaved?.();
            onClose();
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || "Failed to create rule");
        }
    });

    const updateMutation = useMutation({
        mutationFn: (payload: { id: number; data: Partial<TaggingRule> }) =>
            taggingApi.updateRule(payload.id, payload.data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            onSaved?.();
            onClose();
        },
        onError: (err: unknown) => {
            const axiosErr = err as { response?: { data?: { detail?: string } } };
            setError(axiosErr.response?.data?.detail || "Failed to update rule");
        }
    });

    const handleSave = () => {
        setError(null);
        if (!category || !tag) {
            setError("Category and tag are required");
            return;
        }

        const payload = { name, category, tag, conditions };

        if (editingRule) {
            updateMutation.mutate({ id: editingRule.id, data: payload });
        } else {
            createMutation.mutate(payload);
        }
    };

    const isSaving = createMutation.isPending || updateMutation.isPending;

    if (!isOpen) return null;

    const ruleForm = (
        <RuleForm
            name={name}
            category={category}
            setCategory={(c) => { setCategory(c); setTag(""); }}
            tag={tag}
            setTag={setTag}
            conditions={conditions}
            setConditions={setConditions}
            availableCategories={availableCategories}
            availableTags={availableTags}
            onCreateCategory={async (name) => {
                const formatted = await createCategory(name);
                setCategory(formatted);
                setTag("");
            }}
            onCreateTag={async (name) => {
                const formatted = await createTag(category, name);
                setTag(formatted);
            }}
        />
    );

    const previewCount = preview?.count ?? 0;
    const showPreviewBadge = !previewLoading && hasValidCondition(debouncedConditions);

    return (
        <div className="modal-overlay fixed inset-0 z-50 flex items-stretch sm:items-center justify-center">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

            {/* Modal */}
            <div role="dialog" aria-modal="true" aria-labelledby="rule-editor-title" className="relative w-full h-dvh sm:w-[95vw] sm:h-[90vh] bg-[var(--surface-base)] sm:rounded-2xl shadow-2xl sm:border sm:border-[var(--surface-light)] flex flex-col overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-4 md:px-6 py-3 md:py-4 border-b border-[var(--surface-light)] bg-[var(--surface)]">
                    <h2 id="rule-editor-title" className="text-lg md:text-xl font-bold truncate">
                        {editingRule ? t("transactions.autoTagging.editRule") : t("transactions.autoTagging.createRule")}
                    </h2>
                    <button
                        onClick={onClose}
                        aria-label={t("common.close")}
                        className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors shrink-0"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Mobile tabs */}
                <div className="md:hidden flex border-b border-[var(--surface-light)] bg-[var(--surface)]">
                    <button
                        onClick={() => setMobileTab("rule")}
                        className={`flex-1 px-4 py-3 text-sm font-bold transition-colors border-b-2 ${
                            mobileTab === "rule"
                                ? "border-[var(--primary)] text-[var(--primary)]"
                                : "border-transparent text-[var(--text-muted)]"
                        }`}
                    >
                        {t("transactions.autoTagging.tabRule")}
                    </button>
                    <button
                        onClick={() => setMobileTab("matches")}
                        className={`flex-1 px-4 py-3 text-sm font-bold transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
                            mobileTab === "matches"
                                ? "border-[var(--primary)] text-[var(--primary)]"
                                : "border-transparent text-[var(--text-muted)]"
                        }`}
                    >
                        {t("transactions.autoTagging.tabMatches")}
                        {showPreviewBadge && (
                            <span className={`text-xs px-1.5 py-0.5 rounded-full ${
                                mobileTab === "matches"
                                    ? "bg-[var(--primary)]/20 text-[var(--primary)]"
                                    : "bg-[var(--surface-light)] text-[var(--text-muted)]"
                            }`} dir="ltr">{previewCount}</span>
                        )}
                    </button>
                </div>

                {/* Content - mobile (single panel based on tab) */}
                <div className="md:hidden flex-1 overflow-hidden">
                    {mobileTab === "rule" ? (
                        <div className="h-full overflow-y-auto p-4">
                            {ruleForm}
                        </div>
                    ) : (
                        <TransactionPreview matches={(preview?.matches || []) as PreviewTransaction[]} loading={previewLoading} count={previewCount} showHeader={false} />
                    )}
                </div>

                {/* Content - desktop (split pane) */}
                <div className="hidden md:block flex-1 overflow-hidden">
                    <ResizableSplitPane
                        storageKey="rule-editor-split"
                        defaultLeftWidth={55}
                        minLeftWidth={30}
                        minRightWidth={25}
                        left={<TransactionPreview matches={(preview?.matches || []) as PreviewTransaction[]} loading={previewLoading} count={previewCount} />}
                        right={
                            <div className="h-full overflow-y-auto p-4 md:p-6">
                                {ruleForm}
                            </div>
                        }
                    />
                </div>

                {/* Footer */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 md:px-6 py-3 md:py-4 border-t border-[var(--surface-light)] bg-[var(--surface)]">
                    {error && (
                        <div className="flex-1 flex items-center gap-2 p-2.5 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm animate-in slide-in-from-left-2 duration-200">
                            <AlertTriangle size={16} className="shrink-0" />
                            <span className="line-clamp-2">{error}</span>
                        </div>
                    )}
                    <div className="flex items-center gap-3 sm:ms-auto">
                        <button
                            onClick={onClose}
                            className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl font-medium hover:bg-[var(--surface-light)] transition-colors"
                        >
                            {t("common.cancel")}
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={!category || !tag || isSaving}
                            className={`flex-1 sm:flex-initial px-6 py-2.5 text-white rounded-xl font-bold transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:pointer-events-none ${
                                error ? "bg-red-500 hover:bg-red-600 animate-[shake_0.3s_ease-in-out]" : "bg-[var(--primary)] hover:bg-[var(--primary-dark)]"
                            }`}
                        >
                            {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                            {t("transactions.autoTagging.saveRule")}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

// Helper to check if conditions have any value
function hasValidCondition(node: ConditionNode): boolean {
    if (node.type === "CONDITION") {
        return !!node.value;
    }
    if (node.subconditions) {
        return node.subconditions.some(hasValidCondition);
    }
    return false;
}

// Transaction Preview Component
interface PreviewTransaction {
    unique_id?: string;
    date?: string;
    description?: string;
    amount?: number;
    category?: string;
    tag?: string;
    [key: string]: unknown;
}

function TransactionPreview({ matches, loading, count, showHeader = true }: { matches: PreviewTransaction[]; loading: boolean; count: number; showHeader?: boolean }) {
    const { t } = useTranslation();
    const formatAmount = (amount: number) => {
        const formatted = Math.abs(amount).toLocaleString("he-IL", { style: "currency", currency: "ILS" });
        return amount < 0 ? `-${formatted}` : formatted;
    };

    return (
        <div className="h-full flex flex-col bg-[var(--surface)]">
            {showHeader && (
                <div className="px-4 py-3 border-b border-[var(--surface-light)] flex items-center justify-between">
                    <h3 className="font-bold text-[var(--text-muted)]">{t("transactions.autoTagging.matchingTransactions")}</h3>
                    <span className="text-sm text-[var(--text-muted)]">
                        {loading ? t("common.loading") : `${count} ${t("transactions.autoTagging.matches")}`}
                    </span>
                </div>
            )}

            <div className="flex-1 overflow-auto">
                {loading ? (
                    <div className="flex items-center justify-center h-full text-[var(--text-muted)] p-8">
                        <Loader2 size={24} className="animate-spin me-2" />
                        {t("transactions.autoTagging.loadingPreview")}
                    </div>
                ) : matches.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-[var(--text-muted)] p-8 text-center">
                        {t("transactions.autoTagging.noMatchesYet")}<br />
                        {t("transactions.autoTagging.startTyping")}
                    </div>
                ) : (
                    <>
                        {/* Mobile: card list */}
                        <ul className="md:hidden divide-y divide-[var(--surface-light)]/50">
                            {matches.map((tx, i) => (
                                <li key={tx.unique_id || i} className="px-4 py-3 hover:bg-[var(--surface-light)]/20">
                                    <div className="flex items-start justify-between gap-3 mb-1">
                                        <span className="text-xs text-[var(--text-muted)] whitespace-nowrap" dir="ltr">
                                            {tx.date?.split("T")[0] || "—"}
                                        </span>
                                        <span className={`text-sm font-mono font-semibold whitespace-nowrap ${(tx.amount ?? 0) < 0 ? "text-red-400" : "text-green-400"}`} dir="ltr">
                                            {formatAmount(tx.amount ?? 0)}
                                        </span>
                                    </div>
                                    <div className="text-sm break-words" title={tx.description}>
                                        {tx.description}
                                    </div>
                                    <div className="mt-1.5">
                                        {tx.category ? (
                                            <span className="inline-flex flex-wrap gap-1 text-xs">
                                                <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">{tx.category}</span>
                                                {tx.tag && <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">{tx.tag}</span>}
                                            </span>
                                        ) : (
                                            <span className="text-[var(--text-muted)] text-xs">{t("transactions.autoTagging.untagged")}</span>
                                        )}
                                    </div>
                                </li>
                            ))}
                        </ul>

                        {/* Desktop: table */}
                        <table className="hidden md:table w-full text-sm">
                            <thead className="sticky top-0 bg-[var(--surface)] border-b border-[var(--surface-light)]">
                                <tr className="text-start text-[var(--text-muted)]">
                                    <th className="px-4 py-2 font-medium text-start whitespace-nowrap">{t("common.date")}</th>
                                    <th className="px-4 py-2 font-medium text-start">{t("common.description")}</th>
                                    <th className="px-4 py-2 font-medium text-end whitespace-nowrap">{t("common.amount")}</th>
                                    <th className="px-4 py-2 font-medium text-start whitespace-nowrap">{t("transactions.autoTagging.currentTag")}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {matches.map((tx, i) => (
                                    <tr key={tx.unique_id || i} className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/20">
                                        <td className="px-4 py-2 text-[var(--text-muted)] whitespace-nowrap">
                                            {tx.date?.split("T")[0] || "—"}
                                        </td>
                                        <td className="px-4 py-2 truncate max-w-xs" title={tx.description}>
                                            {tx.description}
                                        </td>
                                        <td className={`px-4 py-2 text-end whitespace-nowrap font-mono ${(tx.amount ?? 0) < 0 ? "text-red-400" : "text-green-400"}`}>
                                            <span dir="ltr">{formatAmount(tx.amount ?? 0)}</span>
                                        </td>
                                        <td className="px-4 py-2">
                                            {tx.category ? (
                                                <span className="inline-flex gap-1 text-xs">
                                                    <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">{tx.category}</span>
                                                    {tx.tag && <span className="px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">{tx.tag}</span>}
                                                </span>
                                            ) : (
                                                <span className="text-[var(--text-muted)] text-xs">{t("transactions.autoTagging.untagged")}</span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </>
                )}
            </div>
        </div>
    );
}

// Rule Form Component
function RuleForm({
    name,
    category, setCategory,
    tag, setTag,
    conditions, setConditions,
    availableCategories, availableTags,
    onCreateCategory, onCreateTag,
}: {
    name: string;
    category: string; setCategory: (v: string) => void;
    tag: string; setTag: (v: string) => void;
    conditions: ConditionNode; setConditions: (v: ConditionNode) => void;
    availableCategories: string[];
    availableTags: string[];
    onCreateCategory: (name: string) => Promise<void>;
    onCreateTag: (name: string) => Promise<void>;
}) {
    const { t } = useTranslation();
    return (
        <div className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-4 p-4 bg-[var(--surface)] rounded-xl border border-[var(--surface-light)]">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                    <h4 className="text-xs text-[var(--text-muted)] uppercase font-bold tracking-wide">{t("transactions.autoTagging.ruleDetails")}</h4>
                    {name && (
                        <span className="text-xs text-[var(--text-muted)] font-mono break-all">{name}</span>
                    )}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                        <label className="text-xs text-[var(--text-muted)] uppercase font-bold">{t("common.category")}</label>
                        <div className="mt-1">
                        <SelectDropdown
                            options={availableCategories.map((c) => ({ label: c, value: c }))}
                            value={category}
                            onChange={(val) => setCategory(val)}
                            placeholder={t("common.select")}
                            size="sm"
                            onCreateNew={onCreateCategory}
                        />
                        </div>
                    </div>
                    <div>
                        <label className="text-xs text-[var(--text-muted)] uppercase font-bold">{t("common.tag")}</label>
                        <div className="mt-1">
                        <SelectDropdown
                            options={availableTags.map((t: string) => ({ label: t, value: t }))}
                            value={tag}
                            onChange={(val) => setTag(val)}
                            placeholder={t("common.select")}
                            disabled={!category}
                            size="sm"
                            onCreateNew={onCreateTag}
                        />
                        </div>
                    </div>
                </div>
            </div>

            {/* Conditions */}
            <div className="space-y-3">
                <h4 className="text-xs text-[var(--text-muted)] uppercase font-bold tracking-wide">{t("transactions.autoTagging.conditions")}</h4>
                <div className="p-4 bg-[var(--surface)] rounded-xl border border-[var(--surface-light)]">
                    <RuleBuilder value={conditions} onChange={setConditions} />
                </div>
            </div>
        </div>
    );
}
