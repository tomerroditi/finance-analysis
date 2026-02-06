import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
    Plus,
    Play,
    ShieldCheck,
    Edit2,
    Trash2,
    AlertTriangle,
    Save,
    ArrowLeft,
    Search
} from "lucide-react";
import { taggingApi } from "../../services/api";
import type { TaggingRule, ConditionNode } from "../../services/api";
import { RuleBuilder } from "./RuleBuilder";

const EMPTY_RULE_CONDITIONS: ConditionNode = {
    type: "CONDITION",
    field: "description",
    operator: "contains",
    value: ""
};

export function AutoTaggingPanel() {
    const queryClient = useQueryClient();
    const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Form State
    const [ruleName, setRuleName] = useState("");
    const [ruleCategory, setRuleCategory] = useState("");
    const [ruleTag, setRuleTag] = useState("");
    const [ruleConditions, setRuleConditions] = useState<ConditionNode>(EMPTY_RULE_CONDITIONS);

    const { data: rules, isLoading: rulesLoading } = useQuery({
        queryKey: ["tagging-rules"],
        queryFn: () => taggingApi.getRules().then(res => res.data)
    });

    const { data: categories } = useQuery({
        queryKey: ["categories"],
        queryFn: () => taggingApi.getCategories().then(res => res.data as Record<string, string[]>)
    });

    const createMutation = useMutation({
        mutationFn: (payload: any) => taggingApi.createRule(payload),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
            resetForm();
            setSuccess("Rule created successfully");
            setTimeout(() => setSuccess(null), 3000);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || "Failed to create rule");
        }
    });

    const updateMutation = useMutation({
        mutationFn: (payload: { id: number, data: any }) => taggingApi.updateRule(payload.id, payload.data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
            resetForm();
            setSuccess("Rule updated successfully");
            setTimeout(() => setSuccess(null), 3000);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || "Failed to update rule");
        }
    });

    const deleteMutation = useMutation({
        mutationFn: (id: number) => taggingApi.deleteRule(id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tagging-rules"] })
    });

    const applyMutation = useMutation({
        mutationFn: () => taggingApi.applyRules(false),
        onSuccess: (res) => {
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            setSuccess(`Applied rules! ${res.data.tagged_count} tagged.`);
            setTimeout(() => setSuccess(null), 3000);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || "Failed to apply rules");
        }
    });

    const [searchQuery, setSearchQuery] = useState("");

    const availableTags = ruleCategory && categories ? categories[ruleCategory] || [] : [];

    // Filter rules based on search
    const filteredRules = rules?.filter(rule => {
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
            rule.name.toLowerCase().includes(q) ||
            rule.category.toLowerCase().includes(q) ||
            (rule.tag && rule.tag.toLowerCase().includes(q))
        );
    });

    const handleSave = () => {
        setError(null);
        if (!ruleName || !ruleCategory) return;

        const payload = {
            name: ruleName,
            category: ruleCategory,
            tag: ruleTag,
            conditions: ruleConditions
        };

        if (editingRuleId) {
            updateMutation.mutate({ id: editingRuleId, data: payload });
        } else {
            createMutation.mutate(payload);
        }
    };

    const resetForm = () => {
        setIsCreating(false);
        setEditingRuleId(null);
        setRuleName("");
        setRuleCategory("");
        setRuleTag("");
        setRuleConditions(EMPTY_RULE_CONDITIONS);
        setError(null);
    };

    const startEdit = (rule: TaggingRule) => {
        setEditingRuleId(rule.id);
        setRuleName(rule.name);
        setRuleCategory(rule.category);
        setRuleTag(rule.tag);
        setRuleConditions(rule.conditions);
        setIsCreating(false);
    };

    const showEditor = isCreating || editingRuleId !== null;

    return (
        <div className="shrink-0 z-40 h-[calc(100vh-2rem)] sticky top-4 w-[400px] ml-4 flex flex-col">
            <div className="w-full h-full flex flex-col bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl overflow-hidden">
                {/* Header */}
                <div className="p-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/10">
                    <div className="flex items-center gap-2">
                        <ShieldCheck className="text-[var(--primary)]" size={20} />
                        <h2 className="font-bold text-lg">Auto Tagging</h2>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                    {/* Main Actions */}
                    {!showEditor && (
                        <div className="space-y-4 mb-4">
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setIsCreating(true)}
                                    className="flex-1 py-2 flex items-center justify-center gap-2 bg-[var(--primary)]/10 text-[var(--primary)] rounded-xl border border-[var(--primary)]/20 hover:bg-[var(--primary)]/20 font-bold transition-all"
                                >
                                    <Plus size={18} /> New Rule
                                </button>
                                <button
                                    onClick={() => applyMutation.mutate()}
                                    disabled={applyMutation.isPending}
                                    className="flex-1 py-2 flex items-center justify-center gap-2 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 hover:bg-emerald-500/20 font-bold transition-all disabled:opacity-50"
                                >
                                    <Play size={18} /> Apply Rules
                                </button>
                            </div>

                            {/* Search */}
                            <div className="relative">
                                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
                                <input
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Search rules..."
                                    className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl py-2 pl-9 pr-4 text-sm outline-none focus:border-[var(--primary)] transition-colors placeholder:text-[var(--text-muted)]"
                                />
                            </div>
                        </div>
                    )}

                    {/* Success/Error Messages */}
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

                    {/* Editor Mode */}
                    {showEditor ? (
                        <div className="space-y-4 animate-in fade-in zoom-in-95 duration-200">
                            <div className="flex items-center gap-2 mb-2">
                                <button onClick={resetForm} className="p-1 hover:bg-[var(--surface-light)] rounded">
                                    <ArrowLeft size={16} />
                                </button>
                                <h3 className="font-bold">{editingRuleId ? "Edit Rule" : "Create Rule"}</h3>
                            </div>

                            {/* Basic Info */}
                            <div className="space-y-3 p-4 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)]">
                                <div>
                                    <label className="text-xs text-[var(--text-muted)] uppercase font-bold">Rule Name</label>
                                    <input
                                        value={ruleName}
                                        onChange={e => setRuleName(e.target.value)}
                                        className="w-full mt-1 bg-[var(--surface)] border border-[var(--surface-light)] rounded px-3 py-2 text-sm outline-none focus:border-[var(--primary)]"
                                        placeholder="e.g. Shopping"
                                    />
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="text-xs text-[var(--text-muted)] uppercase font-bold">Category</label>
                                        <select
                                            value={ruleCategory}
                                            onChange={e => {
                                                setRuleCategory(e.target.value);
                                                setRuleTag("");
                                            }}
                                            className="w-full mt-1 bg-[var(--surface)] border border-[var(--surface-light)] rounded px-3 py-2 text-sm outline-none focus:border-[var(--primary)]"
                                        >
                                            <option value="">Select...</option>
                                            {categories && Object.keys(categories).map(c => (
                                                <option key={c} value={c}>{c}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-xs text-[var(--text-muted)] uppercase font-bold">Tag</label>
                                        <select
                                            value={ruleTag}
                                            onChange={e => setRuleTag(e.target.value)}
                                            disabled={!ruleCategory}
                                            className="w-full mt-1 bg-[var(--surface)] border border-[var(--surface-light)] rounded px-3 py-2 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50"
                                        >
                                            <option value="">Select...</option>
                                            {availableTags.map(t => (
                                                <option key={t} value={t}>{t}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                            </div>

                            {/* Conditions Builder */}
                            <div>
                                <h4 className="text-xs text-[var(--text-muted)] uppercase font-bold mb-2">Conditions</h4>
                                <RuleBuilder
                                    value={ruleConditions}
                                    onChange={setRuleConditions}
                                />
                            </div>

                            {/* Actions */}
                            <div className="flex gap-2 pt-4">
                                <button
                                    onClick={resetForm}
                                    className="flex-1 py-2 text-sm font-bold hover:bg-[var(--surface-light)] rounded-xl transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    disabled={!ruleName || !ruleCategory || createMutation.isPending || updateMutation.isPending}
                                    className="flex-[2] py-2 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                                >
                                    <Save size={16} /> Save Rule
                                </button>
                            </div>
                        </div>
                    ) : (
                        // Rules List
                        <div className="space-y-2">
                            {rulesLoading ? (
                                <div className="text-center text-[var(--text-muted)] py-8">Loading rules...</div>
                            ) : filteredRules?.length === 0 ? (
                                <div className="text-center p-8 border border-dashed border-[var(--surface-light)] rounded-xl text-[var(--text-muted)]">
                                    {searchQuery ? "No matching rules found." : "No rules found. Create one to get started."}
                                </div>
                            ) : (
                                filteredRules?.map((rule: TaggingRule) => (
                                    <div key={rule.id} className="group p-3 bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)] hover:border-[var(--primary)]/30 transition-all">
                                        <div className="flex justify-between items-start mb-2">
                                            <h4 className="font-bold text-sm">{rule.name}</h4>
                                            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                                <button
                                                    onClick={() => startEdit(rule)}
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
                    )}
                </div>
            </div>
        </div>
    );
}
