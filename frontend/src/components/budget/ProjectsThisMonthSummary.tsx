import React from "react";
import { useTranslation } from "react-i18next";
import { Layers, ArrowRight } from "lucide-react";
import i18n from "../../i18n";
import { formatCurrency } from "../../utils/numberFormatting";

interface ProjectSpendingItem {
  category: string;
  spent: number;
}

interface ProjectsThisMonthSummaryProps {
  projects: ProjectSpendingItem[];
  onViewAll: () => void;
}

/**
 * Compact, read-only "projects consumed money this month" strip for the
 * monthly view. The full per-project drilldown lives in the Projects tab —
 * this avoids duplicating the transaction lists in two places.
 */
export const ProjectsThisMonthSummary: React.FC<ProjectsThisMonthSummaryProps> = ({
  projects,
  onViewAll,
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";

  if (!projects || projects.length === 0) return null;

  return (
    <div className="pt-4 md:pt-6 border-t border-[var(--surface-light)]">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="flex items-center gap-2 text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">
          <Layers size={14} />
          {t("budget.projectsThisMonth")}
        </h3>
        <button
          onClick={onViewAll}
          className="inline-flex items-center gap-1 text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
        >
          {t("budget.viewAllProjects")}
          {isRtl ? (
            <ArrowRight size={14} className="rotate-180" />
          ) : (
            <ArrowRight size={14} />
          )}
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        {projects.map((project) => (
          <div
            key={project.category}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-[var(--surface-light)]/40 border border-[var(--surface-light)]"
          >
            <span className="text-sm font-medium text-[var(--text-default)] truncate max-w-[40vw]" dir="auto">
              {project.category}
            </span>
            <span className="text-sm font-bold font-mono text-[var(--text-muted)]" dir="ltr">
              {formatCurrency(Math.abs(project.spent))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
