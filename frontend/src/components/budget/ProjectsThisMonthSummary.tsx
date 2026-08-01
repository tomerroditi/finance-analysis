import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import i18n from "../../i18n";
import { formatCurrency } from "../../utils/numberFormatting";
import { RailCard } from "./BudgetRail";

interface ProjectSpendingItem {
  category: string;
  spent: number;
}

interface ProjectsThisMonthSummaryProps {
  projects: ProjectSpendingItem[];
  onViewAll: () => void;
}

/**
 * "Projects consumed money this month" card for the rail.
 *
 * Deliberately read-only: the rail is ~272px, too narrow for a transaction
 * list with per-row actions, and the Projects tab — one click away via the
 * command bar — is where a project is actually managed.
 */
export const ProjectsThisMonthSummary: React.FC<ProjectsThisMonthSummaryProps> = ({
  projects,
  onViewAll,
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";

  if (!projects || projects.length === 0) return null;

  return (
    <RailCard
      title={t("budget.projectsThisMonth")}
      items={projects.map((project) => ({
        key: project.category,
        label: project.category,
        value: formatCurrency(Math.abs(project.spent)),
      }))}
    >
      <button
        onClick={onViewAll}
        className="inline-flex items-center gap-1 mt-2 text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
      >
        {t("budget.viewAllProjects")}
        <ArrowRight size={14} className={isRtl ? "rotate-180" : ""} />
      </button>
    </RailCard>
  );
};
