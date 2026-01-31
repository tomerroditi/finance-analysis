import React, { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, PenSquare } from "lucide-react";
import { budgetApi, pendingRefundsApi } from "../../services/api";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { ProjectModal } from "../modals/ProjectModal";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";

export const ProjectBudgetView: React.FC = () => {
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingRule, setEditingRule] = useState<any>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // Fetch list of projects
  const { data: projects = [] } = useQuery({
    queryKey: ["projects"],
    queryFn: () => budgetApi.getProjects().then((res) => res.data),
  });

  // Fetch pending refunds
  const { data: pendingRefunds } = useQuery({
    queryKey: ["pendingRefunds", "all"],
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  // Create a map of pending refunds
  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, any>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  // Map of linked refunds
  const refundLinksMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      if (pr.links) {
        pr.links.forEach((link: any) => {
          const key = `${link.refund_source}_${link.refund_transaction_id}`;
          map.set(key, link.id);
        });
      }
    });
    return map;
  }, [pendingRefunds]);

  // Auto-select first project if available and none selected
  useEffect(() => {
    if (!selectedProject && projects.length > 0) {
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  // Fetch details for selected project
  const { data: projectDetails } = useQuery({
    queryKey: ["projectDetails", selectedProject],
    queryFn: () =>
      budgetApi.getProjectDetails(selectedProject).then((res) => res.data),
    enabled: !!selectedProject,
  });

  const createMutation = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["availableProjects"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      setSelectedProject(variables.category);
      setIsProjectModalOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      name,
      data,
    }: {
      name: string;
      data: { total_budget: number };
    }) => budgetApi.updateProject(name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projectDetails", selectedProject],
      });
      setIsProjectModalOpen(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: budgetApi.deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["availableProjects"] });
      queryClient.invalidateQueries({ queryKey: ["budgetAnalysis"] });
      setSelectedProject("");
    },
  });

  const updateRuleMutation = useMutation({
    mutationFn: ({ id, rule }: { id: number; rule: any }) =>
      budgetApi.updateRule(id, rule),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["projectDetails", selectedProject],
      });
    },
  });

  const handleCreateProject = (data: {
    category: string;
    total_budget: number;
  }) => {
    createMutation.mutate(data);
  };

  const handleUpdateProject = (data: {
    category: string;
    total_budget: number;
  }) => {
    // Category/Name cannot be changed usually, just budget
    updateMutation.mutate({
      name: selectedProject,
      data: { total_budget: data.total_budget },
    });
  };

  const handleDeleteProject = () => {
    if (
      confirm(`Are you sure you want to delete project '${selectedProject}'?`)
    ) {
      deleteMutation.mutate(selectedProject);
    }
  };

  const handleSaveRule = async (rule: any) => {
    if (editingRule) {
      await updateRuleMutation.mutateAsync({ id: editingRule.id, rule });
    } else {
      // New rule for project - note: ProjectModal handles "Total Budget"
      // This would be for adding specific tag rules if we implement it.
      // For now let's focus on editing existing.
      await budgetApi.createRule(rule);
      queryClient.invalidateQueries({
        queryKey: ["projectDetails", selectedProject],
      });
    }
  };

  const openCreateModal = () => {
    setIsEditMode(false);
    setIsProjectModalOpen(true);
  };

  const openEditModal = () => {
    setIsEditMode(true);
    setIsProjectModalOpen(true);
  };

  const toggleExpand = (id: string) => {
    setExpandedRuleId((prev) => (prev === id ? null : id));
  };

  // Calculate initial data for edit modal
  // We need the total budget amount for the project rule.
  // We can find it in projectDetails.rules where rule.tags == ALL_TAGS?
  // Actually the backend response structure for rules: 'rule' is the rule object.
  const projectTotalRule = projectDetails?.rules?.find(
    (r: any) =>
      r.rule.tags?.includes("ALL_TAGS") ||
      r.rule.tags === "ALL_TAGS" ||
      (Array.isArray(r.rule.tags) && r.rule.tags[0] === "ALL_TAGS"),
  );
  // Note: Backend might return tags as list or string. The budget_service.py converts tags to list in get_all_rules.
  // But check response.

  // A safer check:
  // Actually total rule is likely the first one or we can just use the total_budget if passed separately?
  // We didn't pass "total_budget" explicit field in response except implicit in rules.
  // Wait, get_project_details controller returns: { "name", "rules", "total_spent" }
  // We need to extract the total budget from the rules.
  // Or we can rely on `projectTotalRule` logic.

  const initialModalData =
    isEditMode && projectTotalRule
      ? {
        category: selectedProject,
        total_budget: projectTotalRule.rule.amount,
      }
      : null;

  // Calculate "Other" transactions (those not in specific tag rules)
  const otherTransactions = useMemo(() => {
    if (!projectDetails?.rules) return [];

    const allTransactions = projectTotalRule?.data || [];
    const specificRules = projectDetails.rules.filter(
      (r: any) => r !== projectTotalRule,
    );

    // Collect IDs of transactions in specific rules
    const coveredIds = new Set();
    specificRules.forEach((rule: any) => {
      rule.data.forEach((tx: any) => coveredIds.add(tx.unique_id || tx.id)); // Adjust key if needed based on backend
    });

    return allTransactions.filter(
      (tx: any) => !coveredIds.has(tx.unique_id || tx.id),
    );
  }, [projectDetails, projectTotalRule]);

  return (
    <div className="space-y-8">
      {/* Header / Project Selection */}
      <div className="flex items-center justify-between bg-[var(--surface)] p-4 rounded-2xl shadow-sm border border-[var(--surface-light)]">
        <div className="flex items-center gap-4">
          <label className="font-semibold text-[var(--text-default)]">
            Select Project:
          </label>
          <div className="relative">
            <select
              value={selectedProject}
              onChange={(e) => setSelectedProject(e.target.value)}
              className="appearance-none bg-[var(--surface-base)] border border-[var(--surface-light)] text-[var(--text-default)] text-sm rounded-lg focus:ring-[var(--primary)] focus:border-[var(--primary)] block w-64 p-2.5 pr-8 transition-colors hover:bg-[var(--surface-light)]"
              disabled={projects.length === 0}
            >
              {projects.length === 0 && <option>No Projects</option>}
              {projects.map((p: string) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-[var(--text-muted)]">
              <svg
                className="fill-current h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
              >
                <path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z" />
              </svg>
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium"
          >
            <Plus size={20} />
            New Project
          </button>
          {selectedProject && (
            <button
              onClick={handleDeleteProject}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg hover:bg-red-500/20 transition-colors shadow-sm font-medium"
            >
              <Trash2 size={20} />
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Project Details */}
      {selectedProject && projectDetails && (
        <div className="space-y-4">
          {/* Move Total Rule to top if needed, or stick to list order from backend (usually Total is first or separate) */}
          {/* The backend returns list. Total rule is one of them. */}
          {projectDetails.rules.map((item: any) => {
            const isTotalRule =
              item.rule.tags?.includes("ALL_TAGS") ||
              item.rule.tags === "ALL_TAGS" ||
              (Array.isArray(item.rule.tags) &&
                item.rule.tags[0] === "ALL_TAGS");

            return (
              <BudgetProgressBar
                key={item.rule.id}
                label={isTotalRule ? "Total Project Budget" : item.rule.name}
                subLabel={
                  isTotalRule
                    ? "Overall Allocation"
                    : Array.isArray(item.rule.tags)
                      ? item.rule.tags.join(", ")
                      : item.rule.tags
                }
                current={item.current_amount}
                total={item.rule.amount}
                onToggleExpand={() => toggleExpand(String(item.rule.id))}
                isExpanded={expandedRuleId === String(item.rule.id)}
                actions={
                  <>
                    {item.allow_edit && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (isTotalRule) {
                            openEditModal();
                          } else {
                            setEditingRule(item.rule);
                            setIsRuleModalOpen(true);
                          }
                        }}
                        className="p-1.5 text-[var(--text-muted)] hover:text-blue-500 hover:bg-blue-500/10 rounded-lg transition-all"
                        title="Edit Rule"
                      >
                        <PenSquare size={16} />
                      </button>
                    )}
                  </>
                }
              >
                <TransactionCollapsibleList
                  transactions={item.data}
                  isOpen={expandedRuleId === String(item.rule.id)}
                  showActions
                  onTransactionUpdated={() =>
                    queryClient.invalidateQueries({
                      queryKey: ["projectDetails", selectedProject],
                    })
                  }
                  pendingRefundsMap={pendingRefundsMap}
                />
              </BudgetProgressBar>
            );
          })}

          {/* Other Transactions Section */}
          {otherTransactions.length > 0 && (
            <div className="pt-4 border-t border-[var(--surface-light)] mt-8">
              <h3 className="text-sm font-bold text-[var(--text-muted)] mb-3 uppercase tracking-wider">
                Other Project Transactions
              </h3>
              <BudgetProgressBar
                label="Uncategorized Spending"
                subLabel="(Transactions not covered by specific rules)"
                current={otherTransactions.reduce(
                  (acc: number, tx: any) => acc + Math.abs(tx.amount || 0),
                  0,
                )}
                total={0} // No specific budget for "uncategorized"
                onToggleExpand={() => toggleExpand("other_project_txs")}
                isExpanded={expandedRuleId === "other_project_txs"}
              >
                <TransactionCollapsibleList
                  transactions={otherTransactions}
                  isOpen={expandedRuleId === "other_project_txs"}
                  showActions
                  onTransactionUpdated={() =>
                    queryClient.invalidateQueries({
                      queryKey: ["projectDetails", selectedProject],
                    })
                  }
                  pendingRefundsMap={pendingRefundsMap}
                />
              </BudgetProgressBar>
            </div>
          )}

          {projectDetails.rules.length === 0 && (
            <div className="text-center text-[var(--text-muted)] py-8">
              No budget rules defined for this project.
            </div>
          )}
        </div>
      )}

      {!selectedProject && projects.length === 0 && (
        <div className="text-center text-[var(--text-muted)] py-12 bg-[var(--surface)] rounded-xl border border-dashed border-[var(--surface-light)]">
          <h3 className="text-lg font-medium mb-2">No Projects Found</h3>
          <p className="mb-4">Create a new project to get started.</p>
        </div>
      )}

      {/* Modals */}
      <ProjectModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        onSubmit={isEditMode ? handleUpdateProject : handleCreateProject}
        initialData={initialModalData}
        isEdit={isEditMode}
      />

      <BudgetRuleModal
        isOpen={isRuleModalOpen}
        onClose={() => {
          setIsRuleModalOpen(false);
          setEditingRule(null);
        }}
        onSave={handleSaveRule}
        initialData={editingRule}
        selectedYear={0} // Passed as 0/null for projects
        selectedMonth={0}
      />
    </div>
  );
};
