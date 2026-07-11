import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { budgetApi, pendingRefundsApi, type PendingRefund } from "../../services/api";
import { ProjectModal } from "../modals/ProjectModal";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { useConfirm } from "../../context/DialogContext";
import { ProjectSelectorHeader } from "./ProjectSelectorHeader";
import { ProjectBudgetList } from "./ProjectBudgetList";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";

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
  data: { id?: number; unique_id?: string; amount: number; [key: string]: unknown }[];
  allow_edit: boolean;
  allow_delete: boolean;
}

function isAllTagsRule(rule: ProjectBudgetRule): boolean {
  return (
    rule.tags?.includes("ALL_TAGS") === true ||
    rule.tags === "ALL_TAGS" ||
    (Array.isArray(rule.tags) && rule.tags[0] === "ALL_TAGS")
  );
}

export const ProjectBudgetView: React.FC = () => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const [selectedProject, setSelectedProject] = useState<string>("");
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingRule, setEditingRule] = useState<ProjectBudgetRule | null>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [includeSplitParents, setIncludeSplitParents] = useState(false);

  const queryClient = useQueryClient();
  const qk = useQueryKeys();

  const { data: projects = [] } = useQuery({
    queryKey: qk.budget.projects(),
    queryFn: () => budgetApi.getProjects().then((res) => res.data),
  });

  const { data: pendingRefunds } = useQuery({
    queryKey: qk.pendingRefunds.all(),
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, PendingRefund>();
    pendingRefunds?.forEach((pr: PendingRefund) => {
      map.set(`${pr.source_table}_${pr.source_id}`, pr);
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

  const { data: projectDetails } = useQuery({
    queryKey: qk.budget.projectDetails(selectedProject, includeSplitParents),
    queryFn: () =>
      budgetApi.getProjectDetails(selectedProject, includeSplitParents).then((res) => res.data),
    enabled: !!selectedProject,
  });

  const createMutation = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setSelectedProject(variables.category);
      setIsProjectModalOpen(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ name, data }: { name: string; data: { total_budget: number } }) =>
      budgetApi.updateProject(name, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setIsProjectModalOpen(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: budgetApi.deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setSelectedProject("");
    },
  });

  const updateRuleMutation = useMutation({
    mutationFn: ({ id, rule }: { id: number; rule: object }) =>
      budgetApi.updateRule(id, rule),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    },
  });

  const handleCreateProject = (data: { category: string; total_budget: number }) =>
    createMutation.mutate(data);

  const handleUpdateProject = (data: { category: string; total_budget: number }) =>
    updateMutation.mutate({
      name: selectedProject,
      data: { total_budget: data.total_budget },
    });

  const handleDeleteProject = async () => {
    const ok = await confirm({
      title: t("common.deleteTitle"),
      message: t("budget.confirmDeleteProject", { name: selectedProject }),
      confirmLabel: t("common.delete"),
      isDestructive: true,
    });
    if (ok) deleteMutation.mutate(selectedProject);
  };

  const handleSaveRule = async (rule: object) => {
    if (editingRule) {
      await updateRuleMutation.mutateAsync({ id: editingRule.id, rule });
    } else {
      await budgetApi.createRule(rule);
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    }
  };

  const toggleExpand = (id: string) =>
    setExpandedRuleId((prev) => (prev === id ? null : id));

  const projectTotalRule = projectDetails?.rules?.find((r: ProjectRuleItem) =>
    isAllTagsRule(r.rule),
  );
  const initialModalData =
    isEditMode && projectTotalRule
      ? { category: selectedProject, total_budget: projectTotalRule.rule.amount }
      : null;

  return (
    <div className="space-y-4 md:space-y-6">
      <ProjectSelectorHeader
        projects={projects}
        selectedProject={selectedProject}
        onSelect={setSelectedProject}
        onCreate={() => {
          setIsEditMode(false);
          setIsProjectModalOpen(true);
        }}
        onDelete={handleDeleteProject}
      />

      {selectedProject && projectDetails && (
        <ProjectBudgetList
          projectDetails={projectDetails}
          expandedRuleId={expandedRuleId}
          toggleExpand={toggleExpand}
          pendingRefundsMap={pendingRefundsMap}
          includeSplitParents={includeSplitParents}
          onIncludeSplitParentsChange={setIncludeSplitParents}
          onEditTotalBudget={() => {
            setIsEditMode(true);
            setIsProjectModalOpen(true);
          }}
          onEditTagRule={(rule) => {
            setEditingRule(rule);
            setIsRuleModalOpen(true);
          }}
          onTransactionUpdated={() =>
            queryClient.invalidateQueries({ queryKey: qkPrefix.budget })
          }
        />
      )}

      {!selectedProject && projects.length === 0 && (
        <div className="text-center text-[var(--text-muted)] py-8 md:py-12 bg-[var(--surface)] rounded-xl border border-dashed border-[var(--surface-light)]">
          <h3 className="text-lg font-medium mb-2">{t("budget.noProjectsFound")}</h3>
          <p className="mb-4">{t("budget.createProjectToStart")}</p>
        </div>
      )}

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
        selectedYear={0}
        selectedMonth={0}
      />
    </div>
  );
};
