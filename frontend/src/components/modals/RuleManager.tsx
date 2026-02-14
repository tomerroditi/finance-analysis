import { useState } from "react";
import { X, Plus, Trash2, ShieldCheck, Play, Edit2 } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { taggingApi } from "../../services/api";

interface RuleManagerProps {
  onClose: () => void;
}

export function RuleManager({ onClose }: RuleManagerProps) {
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
    mutationFn: (rule: any) => {
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
    mutationFn: ({ id, rule }: { id: number; rule: any }) => {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-3xl overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        <div className="px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/20">
          <div>
            <h2 className="text-xl font-bold text-white">Auto-Tagging Rules</h2>
            <p className="text-sm text-[var(--text-muted)]">
              Automatically tag transactions based on their description
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-[var(--surface-light)] rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          <div className="flex gap-4 mb-4">
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
              <Plus size={18} /> New Rule
            </button>
            <button
              onClick={() => applyMutation.mutate()}
              disabled={applyMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 font-bold transition-all disabled:opacity-50"
            >
              <Play size={18} />{" "}
              {applyMutation.isPending ? "Applying..." : "Apply Rules Now"}
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
              {editingRuleId !== null ? "Edit Rule" : "Create New Rule"}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="space-y-1.5 text-left">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ml-1">
                  Rule Name
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
              <div className="space-y-1.5 text-left">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ml-1">
                  Contains
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
              <div className="space-y-1.5 text-left">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ml-1">
                  Category
                </label>
                <select
                  className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--primary)]"
                  value={newRule.category}
                  onChange={(e) =>
                    setNewRule({
                      ...newRule,
                      category: e.target.value,
                      tag: "",
                    })
                  }
                >
                  <option value="">Select Category</option>
                  {categories &&
                    Object.keys(categories).map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                </select>
              </div>
              <div className="space-y-1.5 text-left">
                <label className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest ml-1">
                  Tag
                </label>
                <select
                  className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50"
                  value={newRule.tag}
                  onChange={(e) =>
                    setNewRule({ ...newRule, tag: e.target.value })
                  }
                  disabled={!newRule.category}
                >
                  <option value="">Select Tag</option>
                  {availableTags.map((tag: string) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </select>
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
                Cancel
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
                {editingRuleId !== null ? "Update Rule" : "Save Rule"}
              </button>
            </div>
          </div>
        )}

        <div className="space-y-2">
          {isLoading ? (
            <div className="text-center py-8 text-[var(--text-muted)]">
              Loading rules...
            </div>
          ) : rules?.length === 0 ? (
            <div className="text-center py-8 text-[var(--text-muted)] bg-[var(--surface-base)] rounded-xl border border-dashed border-[var(--surface-light)]">
              No rules defined yet
            </div>
          ) : (
            rules?.map((rule: any) => (
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
                        If includes:
                      </span>
                      <code className="text-xs bg-[var(--surface)] px-2 py-0.5 rounded border border-[var(--surface-light)] text-amber-400">
                        {rule.description_contains}
                      </code>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-[var(--text-muted)]">
                        Set Category to
                      </span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-500/10 text-blue-400">
                        {rule.category}
                      </span>
                      {rule.tag && (
                        <>
                          <span className="text-xs text-[var(--text-muted)]">
                            & Tag to
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
                      const descriptionCondition = rule.conditions?.find(
                        (c: any) => c.field === "description",
                      );
                      setNewRule({
                        name: rule.name,
                        description_contains:
                          descriptionCondition?.value || "",
                        category: rule.category,
                        tag: rule.tag,
                      });
                      setEditingRuleId(rule.id);
                      setIsCreating(false);
                    }}
                    className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Edit2 size={18} />
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(rule.id)}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="p-6 border-t border-[var(--surface-light)] bg-[var(--surface-light)]/10 flex justify-end">
        <button
          onClick={onClose}
          className="px-6 py-2 rounded-xl bg-[var(--surface-light)] hover:bg-[var(--surface-base)] text-sm font-semibold transition-all"
        >
          Close
        </button>
      </div>
    </div>
  );
}
