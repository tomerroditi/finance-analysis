import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, ChevronDown, ChevronUp, Layers } from "lucide-react";
import i18n from "../../i18n";
import { formatCurrency } from "../../utils/numberFormatting";
import { TransactionCollapsibleList } from "./TransactionCollapsibleList";
import type { Transaction } from "../../types/transaction";

export interface ProjectSpendingItem {
  category: string;
  spent: number;
  /** Rides along on the month analysis — no request of its own. */
  transactions?: Transaction[];
}

interface ProjectsThisMonthSummaryProps {
  projects: ProjectSpendingItem[];
  onViewAll: () => void;
  onTransactionUpdated?: () => void;
}

/**
 * "Projects consumed money this month", one expandable row per project.
 *
 * The rows used to be read-only, because the card lived in the ~272px rail
 * where a transaction table could not fit. It now shares a half-width row
 * with the savings-goals block, so "which purchases were those?" can be
 * answered here instead of sending the user to the Projects tab — the
 * transactions are already in the month analysis payload, so expanding one
 * costs no request.
 */
export const ProjectsThisMonthSummary: React.FC<ProjectsThisMonthSummaryProps> = ({
  projects,
  onViewAll,
  onTransactionUpdated,
}) => {
  const { t } = useTranslation();
  const isRtl = i18n.language === "he";
  const [expanded, setExpanded] = useState<string | null>(null);

  if (!projects || projects.length === 0) return null;

  const total = projects.reduce((sum, p) => sum + Math.abs(p.spent), 0);

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-4 md:p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1.5 rounded-lg bg-[var(--primary)]/15 text-[var(--primary)]">
            <Layers size={16} />
          </div>
          <p className="text-sm md:text-base font-bold truncate">
            {t("budget.projectsThisMonth")}
          </p>
        </div>
        <span dir="ltr" className="text-xs md:text-sm font-bold tabular-nums shrink-0">
          {formatCurrency(total)}
        </span>
      </div>

      <div className="space-y-2">
        {projects.map((project) => {
          const isOpen = expanded === project.category;
          const transactions = project.transactions ?? [];
          return (
            <div
              key={project.category}
              className="rounded-xl border border-[var(--surface-light)] bg-[var(--surface-base)]/40"
            >
              <button
                type="button"
                onClick={() => setExpanded(isOpen ? null : project.category)}
                aria-expanded={isOpen}
                className="w-full flex items-center justify-between gap-3 px-3 py-2 text-start"
              >
                <span
                  className="text-sm font-medium text-[var(--text-default)] truncate"
                  dir="auto"
                >
                  {project.category}
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  <span dir="ltr" className="font-mono text-xs tabular-nums">
                    {formatCurrency(Math.abs(project.spent))}
                  </span>
                  <span className="text-[var(--text-muted)]">
                    {isOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </span>
                </span>
              </button>

              {isOpen && (
                <div className="px-3 pb-3">
                  <TransactionCollapsibleList
                    transactions={transactions}
                    isOpen
                    showActions
                    onTransactionUpdated={onTransactionUpdated}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <button
        onClick={onViewAll}
        className="inline-flex items-center gap-1 mt-3 text-xs font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
      >
        {t("budget.viewAllProjects")}
        <ArrowRight size={14} className={isRtl ? "rotate-180" : ""} />
      </button>
    </div>
  );
};
