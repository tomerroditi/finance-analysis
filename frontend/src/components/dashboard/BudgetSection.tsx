import { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { BudgetTotalBar } from "../common/BudgetTotalBar";
import { Skeleton } from "../common/Skeleton";
import { ProjectModal } from "../modals/ProjectModal";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";
import { formatMonthYear } from "../../utils/dateFormatting";
import { BudgetRuleGrid } from "./budget/BudgetRuleGrid";
import type { BudgetRule } from "./budget/types";

type BudgetViewMode = "monthly" | "projects";

export function BudgetSpendingGauge({
  categoryIcons,
}: {
  categoryIcons: Record<string, string> | undefined;
}) {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const [year, setYear] = useState(currentYear);
  const [month, setMonth] = useState(currentMonth);
  const [viewMode, setViewMode] = useState<BudgetViewMode>("monthly");
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const qk = useQueryKeys();

  const isCurrentMonth = year === currentYear && month === currentMonth;
  const monthDate = new Date(year, month - 1);
  const monthName = formatMonthYear(monthDate);
  const daysInMonth = new Date(year, month, 0).getDate();
  const daysRemaining = daysInMonth - now.getDate();

  const handlePreviousMonth = () => {
    if (month === 1) {
      setMonth(12);
      setYear(year - 1);
    } else {
      setMonth(month - 1);
    }
  };

  const handleNextMonth = () => {
    if (month === 12) {
      setMonth(1);
      setYear(year + 1);
    } else {
      setMonth(month + 1);
    }
  };

  const queryClient = useQueryClient();

  // Prefetch surrounding 11 months so navigation is instant
  useEffect(() => {
    for (let i = 1; i <= 11; i++) {
      const d = new Date(currentYear, currentMonth - 1 - i);
      const prefetchYear = d.getFullYear();
      const prefetchMonth = d.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: qk.budget.analysis(prefetchYear, prefetchMonth, false),
        queryFn: async () => {
          const res = await budgetApi.getAnalysis(prefetchYear, prefetchMonth, false);
          return res.data;
        },
      });
    }
  }, [qk, currentYear, currentMonth, queryClient]);

  // --- Monthly budget data ---
  const { data: rawBudgetAnalysis, isLoading: monthlyLoading } = useQuery({
    queryKey: qk.budget.analysis(year, month, false),
    queryFn: async () => {
      const res = await budgetApi.getAnalysis(year, month, false);
      return res.data;
    },
    enabled: viewMode === "monthly",
  });

  const budgetAnalysis = useMemo(() => {
    if (!rawBudgetAnalysis?.rules) return undefined;
    const rules: BudgetRule[] = rawBudgetAnalysis.rules.map((item: { rule: { id: number; name: string; category: string; tags: string | null; amount: number }; current_amount: number }) => ({
      id: item.rule.id,
      name: item.rule.name,
      category: item.rule.category,
      budget_amount: item.rule.amount,
      spent_amount: item.current_amount,
    }));
    const totalRule = rules.find((r) => r.name === "Total Budget");
    return {
      rules,
      total_budget: totalRule?.budget_amount,
      total_spent: totalRule?.spent_amount,
    };
  }, [rawBudgetAnalysis]);

  // --- Project budget data ---
  const { data: projects } = useQuery({
    queryKey: qk.budget.projects(),
    queryFn: async () => {
      const res = await budgetApi.getProjects();
      return res.data as string[];
    },
    enabled: viewMode === "projects",
  });

  const createProjectMutation = useMutation({
    mutationFn: budgetApi.createProject,
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
      setSelectedProject(variables.category);
      setIsProjectModalOpen(false);
    },
  });

  // Auto-select first project when projects load

  useEffect(() => {
    if (projects && projects.length > 0 && !selectedProject) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  const { data: rawProjectDetails, isLoading: projectLoading } = useQuery({
    queryKey: qk.budget.projectDetails(selectedProject ?? "", false),
    queryFn: async () => {
      const res = await budgetApi.getProjectDetails(selectedProject!, false);
      return res.data;
    },
    enabled: viewMode === "projects" && !!selectedProject,
  });

  const projectAnalysis = useMemo(() => {
    if (!rawProjectDetails?.rules) return undefined;
    const rules: BudgetRule[] = rawProjectDetails.rules.map((item: { rule: { id: number; name: string; category: string; tags: string | null; amount: number }; current_amount: number }) => ({
      id: item.rule.id,
      name: item.rule.name,
      category: item.rule.category,
      budget_amount: item.rule.amount,
      spent_amount: item.current_amount,
    }));
    const totalRule = rules.find((r) => r.name === "Total Budget");
    return {
      rules,
      total_budget: totalRule?.budget_amount,
      total_spent: totalRule?.spent_amount ?? rawProjectDetails.total_spent,
    };
  }, [rawProjectDetails]);

  // --- Computed values ---
  const activeAnalysis = viewMode === "monthly" ? budgetAnalysis : projectAnalysis;
  const isLoading = viewMode === "monthly" ? monthlyLoading : projectLoading;

  const totalBudget =
    activeAnalysis?.total_budget ??
    (activeAnalysis?.rules?.reduce((sum, r) => sum + r.budget_amount, 0) ?? 0);
  const totalSpent =
    activeAnalysis?.total_spent ??
    (activeAnalysis?.rules?.reduce((sum, r) => sum + r.spent_amount, 0) ?? 0);

  const miniRules = useMemo(() => {
    if (!activeAnalysis?.rules) return [];
    return activeAnalysis.rules
      .filter((r) => r.name !== "Total Budget")
      .sort((a, b) => b.spent_amount - a.spent_amount);
  }, [activeAnalysis]);

  const hasNoMonthlyRules =
    viewMode === "monthly" && (!budgetAnalysis || budgetAnalysis.rules.length === 0);
  const hasNoProjects = viewMode === "projects" && (!projects || projects.length === 0);

  const toggleViewMode = () =>
    setViewMode(viewMode === "monthly" ? "projects" : "monthly");

  const segmentedControlEl = (
    <button
      onClick={toggleViewMode}
      className="flex bg-[var(--surface-light)] p-0.5 rounded-lg cursor-pointer"
    >
      {([
        { key: "monthly" as const, label: t("budget.monthlyBudget") },
        { key: "projects" as const, label: t("budget.projectBudgets") },
      ]).map(({ key, label }) => (
        <span
          key={key}
          className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
            viewMode === key
              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
              : "text-[var(--text-muted)]"
          }`}
        >
          {label}
        </span>
      ))}
    </button>
  );

  return (
    <div
      className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)] flex flex-col h-full"
    >
      {/* Header row: segmented control */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {t("budget.title")}
        </p>
        {segmentedControlEl}
      </div>

      {isLoading ? (
        <>
          <div className="h-9 mb-4">
            <Skeleton variant="text" lines={1} className="h-full" />
          </div>
          <Skeleton variant="chart" className="h-16" />
        </>
      ) : (
        <>
          {/* Sub-header: month nav or project selector — fixed h-9 so content below stays in place */}
          <div className="h-9 flex items-center mb-4">
            {viewMode === "monthly" ? (
              <div className="flex items-center justify-between w-full">
                <div className="flex items-center gap-2">
                  <button
                    onClick={handlePreviousMonth}
                    aria-label={t("common.previous")}
                    className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                  >
                    {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                  </button>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center">
                    {monthName}
                  </p>
                  <button
                    onClick={handleNextMonth}
                    aria-label={t("common.next")}
                    className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                  >
                    {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                  </button>
                </div>
                {isCurrentMonth && (
                  <span className="text-xs text-[var(--text-muted)]">
                    ⏳ {t("dashboard.daysRemaining", { count: daysRemaining })}
                  </span>
                )}
              </div>
            ) : (
              !hasNoProjects && (
                <div className="w-full flex items-center gap-2">
                  <div className="flex-1">
                    <SelectDropdown
                      options={(projects ?? []).map((p) => ({ label: p, value: p }))}
                      value={selectedProject ?? ""}
                      onChange={setSelectedProject}
                      placeholder={t("budget.selectProject")}
                      size="sm"
                    />
                  </div>
                  <button
                    onClick={() => setIsProjectModalOpen(true)}
                    className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--primary)] transition-colors shrink-0"
                    title={t("tooltips.addNewProject")}
                  >
                    <Plus size={16} />
                  </button>
                </div>
              )
            )}
          </div>

          {/* Empty state for projects */}
          {hasNoProjects ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-[var(--text-muted)] mb-3">{t("dashboard.noProjectBudgets")}</p>
              <button
                onClick={() => setIsProjectModalOpen(true)}
                className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
              >
                <Plus size={16} />
                {t("budget.addProject")}
              </button>
            </div>
          ) : hasNoMonthlyRules ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <p className="text-sm text-[var(--text-muted)] mb-3">{t("dashboard.noBudgetRulesForMonth")}</p>
              <Link
                to="/budget"
                className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
              >
                <Plus size={16} />
                {t("budget.addRule")}
              </Link>
            </div>
          ) : (
            <div className="flex flex-1 flex-col min-h-0">
              <div className="mb-4">
                <BudgetTotalBar spent={totalSpent} total={totalBudget} />
              </div>

              {/* Budget rule cards */}
              <BudgetRuleGrid rules={miniRules} categoryIcons={categoryIcons} />

              {/* Link to budget page */}
              <div className="text-end">
                <Link
                  to="/budget"
                  className="text-sm font-medium text-[var(--primary)] hover:underline"
                >
                  {t("dashboard.viewAllBudgetRules")} &rarr;
                </Link>
              </div>
            </div>
          )}
        </>
      )}

      <ProjectModal
        isOpen={isProjectModalOpen}
        onClose={() => setIsProjectModalOpen(false)}
        onSubmit={(data) => createProjectMutation.mutate(data)}
      />
    </div>
  );
}
