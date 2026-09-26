import React, { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, Plus, Trash2, PenSquare } from "lucide-react";
import {
  budgetApi,
  pendingRefundsApi,
  type PendingRefund,
  type ProjectStatus,
} from "../../services/api";
import { ProjectModal } from "../modals/ProjectModal";
import { BudgetRuleModal } from "../modals/BudgetRuleModal";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { ProjectBudgetList } from "./ProjectBudgetList";
import { isAllTagsRule } from "../../utils/budgetRules";
import { BAR_CONTROL, BudgetCommandBar } from "./BudgetCommandBar";
import { BudgetStatusBand, type BandStat } from "./BudgetStatusBand";
import { BudgetNoticeLine } from "./BudgetNoticeLine";
import { RuleSparkline } from "./RuleSparkline";
import { ProjectGoalLink } from "./ProjectGoalLink";
import { SelectDropdown } from "../common/SelectDropdown";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatMonthCompact } from "../../utils/dateFormatting";
import { bucketByMonth, type TrendTransaction } from "../../utils/budgetTrends";
import type { Transaction } from "../../types/transaction";

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
  data: Transaction[];
  allow_edit: boolean;
  allow_delete: boolean;
}

interface ProjectBudgetViewProps {
  tabs: React.ReactNode;
  /** Project to open on, when the link that got here named one. */
  initialProject?: string;
}

/** Month keys from the project's first transaction to today, oldest first. */
function projectMonthKeys(transactions: Transaction[]): string[] {
  const dates = transactions
    .map((tx) => (tx.date ? String(tx.date).slice(0, 7) : null))
    .filter((key): key is string => Boolean(key))
    .sort();
  const now = new Date();
  const end = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const start = dates[0] ?? end;

  const keys: string[] = [];
  const [startYear, startMonth] = start.split("-").map(Number);
  const cursor = new Date(startYear, startMonth - 1, 1);
  const guard = new Date(now.getFullYear(), now.getMonth(), 1);
  while (cursor <= guard && keys.length < 120) {
    keys.push(
      `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`,
    );
    cursor.setMonth(cursor.getMonth() + 1);
  }
  return keys.length ? keys : [end];
}

export const ProjectBudgetView: React.FC<ProjectBudgetViewProps> = ({
  tabs,
  initialProject,
}) => {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const notify = useNotify();
  const [selectedProject, setSelectedProject] = useState<string>(initialProject ?? "");
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingRule, setEditingRule] = useState<ProjectBudgetRule | null>(null);
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [includeSplitParents, setIncludeSplitParents] = useState(false);

  const queryClient = useQueryClient();
  const qk = useQueryKeys();

  // One read answers both "which projects" and "which are finished" — the
  // picker has to label the closed ones, so a plain name list is not enough.
  const { data: projectsStatus = [] } = useQuery({
    queryKey: qk.budget.projectsStatus(),
    queryFn: () => budgetApi.getProjectsStatus().then((res) => res.data),
  });
  const projects = useMemo(
    () => projectsStatus.map((project: ProjectStatus) => project.name),
    [projectsStatus],
  );
  const isSelectedClosed = Boolean(
    projectsStatus.find((p: ProjectStatus) => p.name === selectedProject)?.closed,
  );

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

  // Auto-select a project when none is selected yet: the first *open* one,
  // since a closed project is a finished one and landing on it means the tab
  // opens on history the user is no longer spending against. Only when every
  // project is closed does the first of those stand in — an empty tab would
  // say less than a settled project does.
  useEffect(() => {
    if (selectedProject || projectsStatus.length === 0) return;
    const firstOpen = projectsStatus.find((p: ProjectStatus) => !p.closed);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedProject((firstOpen ?? projectsStatus[0]).name);
  }, [projectsStatus, selectedProject]);

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
    onError: (error: unknown) => {
      // ProjectModal closes itself on submit regardless of outcome (see
      // handleSubmit there), so a 400 from the backend — e.g. the category
      // picker being bypassed/racing another tab into claiming a category
      // already used by a monthly/yearly budget — must be surfaced here.
      const axiosErr = error as { response?: { data?: { detail?: string } } };
      notify.error(axiosErr.response?.data?.detail || t("budget.failedCreateProject"));
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

  const closedMutation = useMutation({
    mutationFn: ({ name, closed }: { name: string; closed: boolean }) =>
      budgetApi.setProjectClosed(name, closed),
    onSuccess: () => {
      // The whole budget prefix, not just the project keys: the Overview's
      // rule list is built from this flag, so it has to refetch too.
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
    },
    onError: () => notify.error(t("budget.failedCloseProject")),
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

  // Reopening is a plain undo, so only closing asks first.
  const handleToggleClosed = async () => {
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

  // Derived inside the memo: `?? []` would otherwise mint a new array on
  // every render and defeat it.
  const monthKeys = useMemo(
    () => projectMonthKeys(projectTotalRule?.data ?? []),
    [projectTotalRule],
  );
  const allTransactions: Transaction[] = projectTotalRule?.data ?? [];
  const monthLabels = useMemo(
    () => monthKeys.map((key) => formatMonthCompact(`${key}-01`)),
    [monthKeys],
  );

  const spent = projectTotalRule?.current_amount ?? 0;
  const total = projectTotalRule?.rule.amount ?? 0;
  const tagCount =
    (projectDetails?.rules?.length ?? 0) - (projectTotalRule ? 1 : 0);
  const activeMonths = Math.max(monthKeys.length, 1);

  const stats: BandStat[] = [
    {
      key: "tags",
      label: t("budget.projectTags"),
      value: (
        <span className="flex items-baseline gap-1">
          <span className="text-lg md:text-xl font-bold">{tagCount}</span>
          <span className="text-[10px] sm:text-xs text-[var(--text-muted)]">
            {t("budget.projectTagRules")}
          </span>
        </span>
      ),
    },
    {
      key: "burnRate",
      label: t("budget.projectAvgPerMonth"),
      value: (
        <span className="text-lg md:text-xl font-bold" dir="ltr">
          {formatCurrency(Math.max(spent, 0) / activeMonths)}
        </span>
      ),
    },
    {
      key: "burn",
      label: t("budget.projectBurn"),
      trend: (
        <RuleSparkline
          variant="burn"
          series={bucketByMonth(
            allTransactions as TrendTransaction[],
            monthKeys,
            spent,
          )}
          labels={monthLabels}
          budget={total}
          totalPeriods={monthKeys.length}
          width={84}
          height={26}
        />
      ),
    },
  ];

  return (
    <div className="space-y-1.5">
      <BudgetCommandBar
        tabs={tabs}
        actions={
          <>
            <button
              onClick={() => {
                setIsEditMode(false);
                setIsProjectModalOpen(true);
              }}
              className={`inline-flex items-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-[var(--primary)] text-white rounded-lg hover:bg-[var(--primary-dark)] transition-colors shadow-sm font-medium whitespace-nowrap ${BAR_CONTROL}`}
            >
              <Plus size={18} className="shrink-0" />
              {t("budget.newProject")}
            </button>
            {selectedProject && (
              <>
                <ProjectGoalLink project={selectedProject} />
                <button
                  onClick={handleToggleClosed}
                  disabled={closedMutation.isPending}
                  data-testid="project-closed-toggle"
                  className={`inline-flex items-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg hover:bg-[var(--surface)] transition-colors shadow-sm font-medium whitespace-nowrap disabled:opacity-60 ${BAR_CONTROL}`}
                >
                  {isSelectedClosed ? (
                    <ArchiveRestore size={18} className="shrink-0" />
                  ) : (
                    <Archive size={18} className="shrink-0" />
                  )}
                  {isSelectedClosed
                    ? t("budget.reopenProject")
                    : t("budget.closeProject")}
                </button>
                <button
                  onClick={handleDeleteProject}
                  className={`inline-flex items-center gap-2 px-3 md:px-4 text-xs md:text-sm bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg hover:bg-red-500/20 transition-colors shadow-sm font-medium whitespace-nowrap ${BAR_CONTROL}`}
                >
                  <Trash2 size={18} className="shrink-0" />
                  {t("common.delete")}
                </button>
              </>
            )}
          </>
        }
      >
        {/* The picker takes the space beside its label instead of sitting in
            it at a fixed 160px: a project name is free text, and it was being
            truncated mid-name while the rest of the row stood empty. `w-full`
            (not `flex-1`) keeps the group a full line on a phone, so the
            actions still wrap below it rather than squeezing the select back
            down; the desktop cap stops it stretching across a wide screen,
            where that space belongs to the actions. */}
        <div className="flex w-full md:w-auto md:flex-auto items-center gap-2 min-w-0">
          <label className="text-xs md:text-sm font-medium text-[var(--text-muted)] whitespace-nowrap">
            {t("budget.selectProject")}
          </label>
          <div
            className="flex-1 min-w-0 md:max-w-80"
            data-testid="project-picker"
          >
            <SelectDropdown
              options={projectsStatus.map((p: ProjectStatus) => ({
                label: p.closed
                  ? t("budget.projectClosedOption", { name: p.name })
                  : p.name,
                value: p.name,
              }))}
              value={selectedProject}
              onChange={setSelectedProject}
              placeholder={
                projects.length === 0 ? t("budget.noProjects") : t("budget.selectProject")
              }
              disabled={projects.length === 0}
              size="sm"
              triggerClassName={`${BAR_CONTROL} py-0`}
            />
          </div>
        </div>
      </BudgetCommandBar>

      <BudgetNoticeLine />

      {/* Only the status band needs the project's `all_tags` anchor rule (it
          is where the project's total lives) — the rule ledger does not.
          Gating the whole block on the anchor rendered a project without one
          as a blank page: no band, no ledger, not even an empty state. */}
      {selectedProject && projectDetails && (
        <>
          {isSelectedClosed && (
            <p
              data-testid="project-closed-notice"
              className="flex items-center gap-2 text-xs md:text-sm text-[var(--text-muted)] bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl px-3 py-2"
            >
              <Archive size={14} className="shrink-0" />
              {t("budget.projectClosedNotice")}
            </p>
          )}

          {projectTotalRule && (
            <BudgetStatusBand
              label={selectedProject}
              spent={spent}
              total={total}
              stats={stats}
              footer={
                projectTotalRule.allow_edit ? (
                  <button
                    onClick={() => {
                      setIsEditMode(true);
                      setIsProjectModalOpen(true);
                    }}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
                  >
                    <PenSquare size={14} />
                    {t("budget.editTotalBudget")}
                  </button>
                ) : undefined
              }
            />
          )}

          <ProjectBudgetList
            projectDetails={projectDetails}
            monthKeys={monthKeys}
            expandedRuleId={expandedRuleId}
            toggleExpand={toggleExpand}
            pendingRefundsMap={pendingRefundsMap}
            includeSplitParents={includeSplitParents}
            onIncludeSplitParentsChange={setIncludeSplitParents}
            onEditTagRule={(rule) => {
              setEditingRule(rule);
              setIsRuleModalOpen(true);
            }}
            onTransactionUpdated={() =>
              queryClient.invalidateQueries({ queryKey: qkPrefix.budget })
            }
          />
        </>
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
