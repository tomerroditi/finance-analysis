import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { Archive, ArchiveRestore, Plus } from "lucide-react";
import { budgetApi, type ProjectStatus } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { SelectDropdown } from "../../common/SelectDropdown";
import { Skeleton } from "../../common/Skeleton";
import { ProjectModal } from "../../modals/ProjectModal";
import { useConfirm, useNotify } from "../../../context/DialogContext";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { qkPrefix } from "../../../services/queryKeys";
import { budgetLink } from "../../../utils/budgetNavigation";
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
  const confirm = useConfirm();
  const notify = useNotify();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);

  // The status read, not the plain name list: finishing a project from here
  // means the picker has to say which ones are already closed.
  const { data: projectsStatus, isLoading: isProjectsLoading } = useQuery({
    queryKey: qk.budget.projectsStatus(),
    queryFn: async () => {
      const res = await budgetApi.getProjectsStatus();
      return res.data;
    },
  });

  const projects = useMemo(
    () => (projectsStatus ?? []).map((project: ProjectStatus) => project.name),
    [projectsStatus],
  );
  const isSelectedClosed = Boolean(
    projectsStatus?.find((p: ProjectStatus) => p.name === selectedProject)?.closed,
  );

  const createProject = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      onSelectProject(variables.category);
      setIsModalOpen(false);
    },
  });

  const closedMutation = useMutation({
    mutationFn: ({ name, closed }: { name: string; closed: boolean }) =>
      budgetApi.setProjectClosed(name, closed),
    onSuccess: () => {
      // The whole budget prefix: this card's own Overview tab builds its
      // envelope list from the flag, so it has to refetch too.
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    },
    onError: () => notify.error(t("budget.failedCloseProject")),
  });

  useEffect(() => {
    if (projects.length > 0 && !selectedProject) {
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

  // Reopening is a plain undo, so only closing asks first — same as the
  // Budget page's projects tab.
  const handleToggleClosed = async () => {
    if (!selectedProject) return;
    if (isSelectedClosed) {
      closedMutation.mutate({ name: selectedProject, closed: false });
      return;
    }
    const ok = await confirm({
      title: t("budget.closeProject"),
      message: t("budget.confirmCloseProject", { name: selectedProject }),
      confirmLabel: t("budget.closeProject"),
    });
    if (ok) closedMutation.mutate({ name: selectedProject, closed: true });
  };

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

  if (projects.length === 0) {
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
      <div className="flex-1 min-w-0">
        <SelectDropdown
          options={(projectsStatus ?? []).map((p: ProjectStatus) => ({
            label: p.closed ? t("budget.projectClosedOption", { name: p.name }) : p.name,
            value: p.name,
          }))}
          value={selectedProject ?? ""}
          onChange={onSelectProject}
          placeholder={t("budget.selectProject")}
          size="sm"
        />
      </div>
      {!!selectedProject && (
        <button
          onClick={handleToggleClosed}
          disabled={closedMutation.isPending}
          data-testid="card-project-closed-toggle"
          aria-label={
            isSelectedClosed ? t("budget.reopenProject") : t("budget.closeProject")
          }
          title={isSelectedClosed ? t("budget.reopenProject") : t("budget.closeProject")}
          className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors shrink-0 disabled:opacity-60"
        >
          {isSelectedClosed ? <ArchiveRestore size={16} /> : <Archive size={16} />}
        </button>
      )}
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
      {isSelectedClosed && (
        <p
          data-testid="card-project-closed-notice"
          className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] mb-3"
        >
          <Archive size={12} className="shrink-0" />
          {t("budget.projectClosedNotice")}
        </p>
      )}
      {isDetailsLoading || !analysis ? (
        <Skeleton variant="chart" className="h-16" />
      ) : (
        <>
          <div className="mb-4">
            <BudgetTotalBar spent={analysis.totalSpent} total={analysis.totalBudget} />
          </div>
          <BudgetRuleGrid rules={analysis.rules} categoryIcons={categoryIcons} />
          <div className="text-end">
            <Link
              to={budgetLink("projects", { project: selectedProject })}
              className="text-sm font-medium text-[var(--primary)] hover:underline"
            >
              {t("dashboard.viewAllBudgetRules")} &rarr;
            </Link>
          </div>
        </>
      )}
      {modal}
    </div>
  );
};
