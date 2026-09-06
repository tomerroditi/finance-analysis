import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { Plus } from "lucide-react";
import { budgetApi } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { SelectDropdown } from "../../common/SelectDropdown";
import { Skeleton } from "../../common/Skeleton";
import { ProjectModal } from "../../modals/ProjectModal";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { qkPrefix } from "../../../services/queryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import { normalizeAnalysis } from "./normalizeAnalysis";

interface ProjectBudgetTabProps {
  selectedProject: string | null;
  onSelectProject: (project: string | null) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const ProjectBudgetTab: React.FC<ProjectBudgetTabProps> = ({
  selectedProject,
  onSelectProject,
  categoryIcons,
}) => {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { data: projects, isLoading: isProjectsLoading } = useQuery({
    queryKey: qk.budget.projects(),
    queryFn: async () => {
      const res = await budgetApi.getProjects();
      return res.data as string[];
    },
  });

  const createProject = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      onSelectProject(variables.category);
      setIsModalOpen(false);
    },
  });

  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProject) {
      onSelectProject(projects[0]);
    }
  }, [projects, selectedProject, onSelectProject]);

  const { data, isLoading: isDetailsLoading } = useQuery({
    queryKey: qk.budget.projectDetails(selectedProject ?? "", false),
    queryFn: async () => {
      const res = await budgetApi.getProjectDetails(selectedProject!, false);
      return res.data;
    },
    enabled: !!selectedProject,
  });

  // Projects fall back to the payload's own total_spent, which covers spend
  // that predates any rule; monthly has no such field and sums its rules.
  const analysis = useMemo(
    () => (data?.rules ? normalizeAnalysis(data.rules, data.total_spent) : undefined),
    [data],
  );

  const modal = (
    <ProjectModal
      isOpen={isModalOpen}
      onClose={() => setIsModalOpen(false)}
      onSubmit={(payload) => createProject.mutate(payload)}
    />
  );

  if (isProjectsLoading) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        <Skeleton variant="chart" className="h-16" />
      </div>
    );
  }

  if (!projects || projects.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">
            {t("dashboard.noProjectBudgets")}
          </p>
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.addProject")}
          </button>
        </div>
        {modal}
      </div>
    );
  }

  const selector = (
    <div className="h-9 flex items-center w-full gap-2 mb-4">
      <div className="flex-1">
        <SelectDropdown
          options={projects.map((p) => ({ label: p, value: p }))}
          value={selectedProject ?? ""}
          onChange={onSelectProject}
          placeholder={t("budget.selectProject")}
          size="sm"
        />
      </div>
      <button
        onClick={() => setIsModalOpen(true)}
        className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--primary)] transition-colors shrink-0"
        title={t("tooltips.addNewProject")}
      >
        <Plus size={16} />
      </button>
    </div>
  );

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {selector}
      {isDetailsLoading || !analysis ? (
        <Skeleton variant="chart" className="h-16" />
      ) : (
        <>
          <div className="mb-4">
            <BudgetTotalBar spent={analysis.totalSpent} total={analysis.totalBudget} />
          </div>
          <BudgetRuleGrid rules={analysis.rules} categoryIcons={categoryIcons} />
          <div className="text-end">
            <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
              {t("dashboard.viewAllBudgetRules")} &rarr;
            </Link>
          </div>
        </>
      )}
      {modal}
    </div>
  );
};
