import React from "react";
import { useTranslation } from "react-i18next";
import { Layers, ArrowRight, ChevronDown, ChevronUp } from "lucide-react";
import i18n from "../../i18n";
import { formatCurrency } from "../../utils/numberFormatting";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import type { Transaction } from "../../types/transaction";
import type { PendingRefund } from "../../services/api";

interface ProjectSpendingItem {
  category: string;
  spent: number;
  transactions: Transaction[];
}

interface ProjectsThisMonthSummaryProps {
  projects: ProjectSpendingItem[];
  onViewAll: () => void;
  expandedRuleId: string | null;
  toggleExpand: (id: string) => void;
  pendingRefundsMap: Map<string, PendingRefund>;
  onTransactionUpdated: () => void;
}

/**
 * "Projects consumed money this month" strip for the monthly view. Each
 * project row expands to show that project's transactions for the month;
 * the full project budget management still lives in the Projects tab.
 */
export const ProjectsThisMonthSummary: React.FC<ProjectsThisMonthSummaryProps> = ({
  projects,
  onViewAll,
  expandedRuleId,
  toggleExpand,
  pendingRefundsMap,
  onTransactionUpdated,
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

      <div className="space-y-2">
        {projects.map((project) => {
          const key = `project_month_${project.category}`;
          const isOpen = expandedRuleId === key;
          return (
            <div
              key={project.category}
              className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] shadow-sm"
            >
              <button
                onClick={() => toggleExpand(key)}
                aria-expanded={isOpen}
                className="w-full flex items-center justify-between gap-2 px-3 md:px-4 py-2.5 text-start"
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className="text-[var(--text-muted)] shrink-0">
                    {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </span>
                  <span
                    className="font-medium text-sm text-[var(--text-default)] truncate"
                    dir="auto"
                  >
                    {project.category}
                  </span>
                </span>
                <span className="font-bold font-mono text-sm shrink-0" dir="ltr">
                  {formatCurrency(Math.abs(project.spent))}
                </span>
              </button>
              <TransactionCollapsibleList
                transactions={project.transactions}
                isOpen={isOpen}
                showActions
                onTransactionUpdated={onTransactionUpdated}
                pendingRefundsMap={pendingRefundsMap}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};
