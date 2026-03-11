import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, PenSquare } from "lucide-react";
import { budgetApi, pendingRefundsApi, type PendingRefund } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { BudgetProgressBar } from "../BudgetProgressBar";
import { ProjectModal } from "../modals/ProjectModal";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";

interface ProjectBudgetRule {
  id: number;
  name: string;
  category: string;
  amount: number;
  tags?: string | string[];
}

interface ProjectRuleItem {
  rule: ProjectBudgetRule;
  current_amount: number;
  data: ProjectTransaction[];
  allow_edit: boolean;
  allow_delete: boolean;
}

interface ProjectTransaction {
  id?: number;
  unique_id?: string;
  amount: number;
  date: string;
  source?: string;
  desc?: string;
  description?: string;
  category?: string;
  tag?: string;
  provider?: string;
  account_name?: string;
  account_number?: string;
  pending_refund_id?: number;
  [key: string]: unknown;
}

export const ProjectBudgetView: React.FC = () => {
  const { t } = useTranslation();
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingRule, setEditingRule] = useState<ProjectBudgetRule | null>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [includeSplitParents, setIncludeSplitParents] = useState(false);

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
    const map = new Map<string, PendingRefund>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: PendingRefund) => {
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  // Auto-select first project if available and none selected
   
  useEffect(() => {
    if (!selectedProject && projects.length > 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  // Fetch details for selected project
  const { data: projectDetails } = useQuery({
    queryKey: ["projectDetails", selectedProject, includeSplitParents],
    queryFn: () =>
      budgetApi
        .getProjectDetails(selectedProject, includeSplitParents)
        .then((res) => res.data),
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
    mutationFn: ({ id, rule }: { id: number; rule: object }) =>
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
      confirm(t("budget.confirmDeleteProject", { name: selectedProject }))
    ) {
      deleteMutation.mutate(selectedProject);
    }
  };

  const handleSaveRule = async (rule: object) => {
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
    (r: ProjectRuleItem) =>
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
      (r: ProjectRuleItem) => r !== projectTotalRule,
    );

    // Collect IDs of transactions in specific rules
    const coveredIds = new Set<string | number | undefined>();
    specificRules.forEach((rule: ProjectRuleItem) => {
      rule.data.forEach((tx: ProjectTransaction) => coveredIds.add(tx.unique_id || tx.id));
    });

    return allTransactions.filter(
      (tx: ProjectTransaction) => !coveredIds.has(tx.unique_id || tx.id),
    );
  }, [projectDetails, projectTotalRule]);

  return (
    <div className="space-y-8">
      {/* Header / Project Selection */}
      <div className="flex items-center justify-between bg-[var(--surface)] p-4 rounded-2xl shadow-sm border border-[var(--surface-light)]">
        <div className="flex items-center gap-4">
          <label className="font-semibold text-[var(--text-default)]">
            {t("budget.selectProject")}
          </label>
          <div className="w-64">
            <SelectDropdown
              options={projects.length > 0 ? projects.map((p: string) => ({ label: p, value: p })) : []}
              value={selectedProject}
              onChange={(val) => setSelectedProject(val)}
              placeholder={projects.length === 0 ? t("budget.noProjects") : t("budget.selectProject")}
              disabled={projects.length === 0}
              size="sm"
            />
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={openCreateModal}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium"
          >
            <Plus size={20} />
            {t("budget.newProject")}
          </button>
          {selectedProject && (
            <button
              onClick={handleDeleteProject}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg hover:bg-red-500/20 transition-colors shadow-sm font-medium"
            >
              <Trash2 size={20} />
              {t("common.delete")}
            </button>
          )}
        </div>
      </div>

      {/* Project Details */}
      {selectedProject && projectDetails && (
        <div className="space-y-4">
          {/* Move Total Rule to top if needed, or stick to list order from backend (usually Total is first or separate) */}
          {/* The backend returns list. Total rule is one of them. */}
          {projectDetails.rules.map((item: ProjectRuleItem) => {
            const isTotalRule =
              item.rule.tags?.includes("ALL_TAGS") ||
              item.rule.tags === "ALL_TAGS" ||
              (Array.isArray(item.rule.tags) &&
                item.rule.tags[0] === "ALL_TAGS");

            return (
              <BudgetProgressBar
                key={item.rule.id}
                label={isTotalRule ? t("budget.totalProjectBudget") : item.rule.name}
                subLabel={
                  isTotalRule
                    ? t("budget.overallAllocation")
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
                        title={t("budget.editRule")}
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
                  showSplitParentsFilter
                  includeSplitParents={includeSplitParents}
                  onIncludeSplitParentsChange={setIncludeSplitParents}
                />
              </BudgetProgressBar>
            );
          })}

          {/* Other Transactions Section */}
          {otherTransactions.length > 0 && (
            <div className="pt-4 border-t border-[var(--surface-light)] mt-8">
              <h3 className="text-sm font-bold text-[var(--text-muted)] mb-3 uppercase tracking-wider">
                {t("budget.otherProjectTransactions")}
              </h3>
              <BudgetProgressBar
                label={t("budget.uncategorizedSpending")}
                subLabel={t("budget.uncategorizedSubLabel")}
                current={otherTransactions.reduce(
                  (acc: number, tx: ProjectTransaction) => acc + Math.abs(tx.amount || 0),
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
                  showSplitParentsFilter
                  includeSplitParents={includeSplitParents}
                  onIncludeSplitParentsChange={setIncludeSplitParents}
                />
              </BudgetProgressBar>
            </div>
          )}

          {projectDetails.rules.length === 0 && (
            <div className="text-center text-[var(--text-muted)] py-8">
              {t("budget.noRulesForProject")}
            </div>
          )}
        </div>
      )}

      {!selectedProject && projects.length === 0 && (
        <div className="text-center text-[var(--text-muted)] py-12 bg-[var(--surface)] rounded-xl border border-dashed border-[var(--surface-light)]">
          <h3 className="text-lg font-medium mb-2">{t("budget.noProjectsFound")}</h3>
          <p className="mb-4">{t("budget.createProjectToStart")}</p>
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
