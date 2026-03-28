import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X, Plus, Trash2, ShieldCheck, Play, Edit2 } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { taggingApi, type TaggingRule } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { useScrollLock } from "../../hooks/useScrollLock";

interface RuleManagerProps {
  onClose: () => void;
}

export function RuleManager({ onClose }: RuleManagerProps) {
  const { t } = useTranslation();
  useScrollLock(true);
  const queryClient = useQueryClient();
  const [isCreating, setIsCreating] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [newRule, setNewRule] = useState({
    name: "",
    description_contains: "", // Still using this for the simple UI, will map to conditions
    category: "",
    tag: "",
  });

  const { data: rules, isLoading } = useQuery({
    queryKey: ["tagging-rules"],
    queryFn: () => taggingApi.getRules().then((res) => res.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const createMutation = useMutation({
    mutationFn: (rule: { name?: string; description_contains: string; category: string; tag: string }) => {
      const payload = {
        name: rule.name || rule.description_contains,
        conditions: {
          type: "CONDITION" as const,
          field: "description",
          operator: "contains" as const,
          value: rule.description_contains,
        },
        category: rule.category,
        tag: rule.tag,
      };
      return taggingApi.createRule(payload);
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
      setIsCreating(false);
      setNewRule({ name: "", description_contains: "", category: "", tag: "" });
      setSuccessMessage(
        `Rule created! ${res.data.tagged_count} transactions tagged.`,
      );
      setTimeout(() => setSuccessMessage(null), 5000);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, rule }: { id: number; rule: { name?: string; description_contains: string; category: string; tag: string } }) => {
      const payload = {
        name: rule.name || rule.description_contains,
        conditions: {
          type: "CONDITION" as const,
          field: "description",
          operator: "contains" as const,
          value: rule.description_contains,
        },
        category: rule.category,
        tag: rule.tag,
      };
      return taggingApi.updateRule(id, payload);
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["tagging-rules"] });
      setEditingRuleId(null);
      setNewRule({ name: "", description_contains: "", category: "", tag: "" });
      setSuccessMessage(
        `Rule updated! ${res.data.tagged_count} transactions tagged.`,
      );
      setTimeout(() => setSuccessMessage(null), 5000);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => taggingApi.deleteRule(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["tagging-rules"] }),
  });

  const applyMutation = useMutation({
    mutationFn: () => taggingApi.applyRules(),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      setSuccessMessage(
        `Success! ${res.data.tagged_count} transactions tagged.`,
      );
      setTimeout(() => setSuccessMessage(null), 5000);
    },
  });

  const availableTags =
    newRule.category && categories ? categories[newRule.category] || [] : [];

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-[calc(100vw-2rem)] md:max-w-3xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        <div className="px-4 md:px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/20 shrink-0">
          <div>
            <h2 className="text-lg md:text-xl font-bold text-white">{t("modals.ruleManager.title")}</h2>
            <p className="text-sm text-[var(--text-muted)]">
              {t("modals.ruleManager.subtitle")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 md:p-6 overflow-y-auto flex-1">
          <div className="flex flex-col sm:flex-row gap-4 mb-4">
            <button
              onClick={() => {
                setIsCreating(true);
                setEditingRuleId(null);
                setNewRule({
                  name: "",
                  description_contains: "",
                  category: "",
                  tag: "",
                });
              }}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[var(--primary)]/10 text-[var(--primary)] hover:bg-[var(--primary)]/20 border border-[var(--primary)]/20 font-bold transition-all"
            >
              <Plus size={18} /> {t("modals.ruleManager.newRule")}
            </button>
            <button
              onClick={() => applyMutation.mutate()}
              disabled={applyMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition-all disabled:opacity-50"
            >
              <Play size={18} />{" "}
              {applyMutation.isPending ? t("modals.ruleManager.applying") : t("modals.ruleManager.applyRulesNow")}
            </button>
          </div>
        </div>

        {successMessage && (
          <div className="mb-6 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-bold animate-in slide-in-from-top-2 duration-300">
            {successMessage}
          </div>
        )}

        {(isCreating || editingRuleId !== null) && (
          <div className="mb-6 p-4 rounded-xl bg-[var(--surface-base)] border border-[var(--primary)]/30 animate-in slide-in-from-top-2 duration-200">
            <h3 className="text-sm font-bold uppercase tracking-wider text-[var(--primary)] mb-4">
              {editingRuleId !== null ? t("modals.ruleManager.editRule") : t("modals.ruleManager.createNewRule")}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="space-y-1.5 text-start">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ms-1">
                  {t("modals.ruleManager.ruleName")}
                </label>
                <input
                  type="text"
                  placeholder="e.g. Coffee Shops"
                  className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--primary)]"
                  value={newRule.name}
                  onChange={(e) =>
                    setNewRule({ ...newRule, name: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5 text-start">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ms-1">
                  {t("modals.ruleManager.contains")}
                </label>
                <input
                  type="text"
                  placeholder="e.g. McDonald's"
                  className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--primary)]"
                  value={newRule.description_contains}
                  onChange={(e) =>
                    setNewRule({
                      ...newRule,
                      description_contains: e.target.value,
                    })
                  }
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5 text-start">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ms-1">
                  {t("common.category")}
                </label>
                <SelectDropdown
                  options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
                  value={newRule.category}
                  onChange={(val) =>
                    setNewRule({
                      ...newRule,
                      category: val,
                      tag: "",
                    })
                  }
                  placeholder={t("modals.transactionForm.selectCategory")}
                  size="sm"
                />
              </div>
              <div className="space-y-1.5 text-start">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ms-1">
                  {t("common.tag")}
                </label>
                <SelectDropdown
                  options={availableTags.map((tag: string) => ({ label: tag, value: tag }))}
                  value={newRule.tag}
                  onChange={(val) =>
                    setNewRule({ ...newRule, tag: val })
                  }
                  placeholder={t("modals.transactionForm.selectTag")}
                  disabled={!newRule.category}
                  size="sm"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4 justify-end">
              <button
                onClick={() => {
                  setIsCreating(false);
                  setEditingRuleId(null);
                }}
                className="px-4 py-2 text-sm font-medium hover:text-white transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => {
                  if (editingRuleId !== null) {
                    updateMutation.mutate({
                      id: editingRuleId,
                      rule: newRule,
                    });
                  } else {
                    createMutation.mutate(newRule);
                  }
                }}
                disabled={!newRule.description_contains || !newRule.category}
                className="px-6 py-2 rounded-lg bg-[var(--primary)] text-white text-sm font-bold shadow-lg shadow-[var(--primary)]/20 hover:bg-[var(--primary-dark)] transition-all disabled:opacity-50"
              >
                {editingRuleId !== null ? t("modals.ruleManager.updateRule") : t("modals.ruleManager.saveRule")}
              </button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {isLoading ? (
            <div className="text-center py-8 text-[var(--text-muted)]">
              {t("modals.ruleManager.loadingRules")}
            </div>
          ) : rules?.length === 0 ? (
            <div className="text-center py-8 text-[var(--text-muted)] bg-[var(--surface-base)] rounded-xl border border-dashed border-[var(--surface-light)]">
              {t("modals.ruleManager.noRules")}
            </div>
          ) : (
            rules?.map((rule: TaggingRule) => (
              <div
                key={rule.id}
                className="group flex items-center justify-between p-4 rounded-xl bg-[var(--surface-base)]/50 border border-[var(--surface-light)] hover:border-[var(--primary)]/30 transition-all"
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-full bg-[var(--surface-light)] flex items-center justify-center text-[var(--primary)]">
                    <ShieldCheck size={20} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">
                        {t("modals.ruleManager.ifIncludes")}:
                      </span>
                      <code className="text-xs bg-[var(--surface)] px-2 py-0.5 rounded border border-[var(--surface-light)] text-amber-400">
                        {rule.conditions?.subconditions?.find(c => c.field === "description")?.value ?? rule.name}
                      </code>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-[var(--text-muted)]">
                        {t("modals.ruleManager.setCategoryTo")}
                      </span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400">
                        {rule.category}
                      </span>
                      {rule.tag && (
                        <>
                          <span className="text-xs text-[var(--text-muted)]">
                            {t("modals.ruleManager.andTagTo")}
                          </span>
                          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-purple-500/10 text-purple-400">
                            {rule.tag}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      const descriptionCondition = rule.conditions?.subconditions?.find(
                        (c) => c.field === "description",
                      );
                      setNewRule({
                        name: rule.name,
                        description_contains:
                          String(descriptionCondition?.value ?? ""),
                        category: rule.category,
                        tag: rule.tag,
                      });
                      setEditingRuleId(rule.id);
                      setIsCreating(false);
                    }}
                    className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Edit2 size={18} />
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(rule.id)}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400 opacity-100 md:opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="p-4 md:p-6 border-t border-[var(--surface-light)] bg-[var(--surface-light)]/10 flex justify-end">
        <button
          onClick={onClose}
          className="px-6 py-2 rounded-xl bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-semibold transition-all"
        >
          {t("common.close")}
        </button>
      </div>
    </div>
  );
}
