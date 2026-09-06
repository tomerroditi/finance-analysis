import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MonthlyBudgetTab } from "./budget/MonthlyBudgetTab";
import { YearlyBudgetTab } from "./budget/YearlyBudgetTab";
import { ProjectBudgetTab } from "./budget/ProjectBudgetTab";

type BudgetTab = "monthly" | "yearly" | "projects";

interface BudgetSectionProps {
  categoryIcons: Record<string, string> | undefined;
}

/**
 * Dashboard budget card: chrome, tab strip and the period cursors.
 *
 * Cursors live here rather than in the tabs so switching tabs does not discard
 * a month the user had navigated to. Each tab owns its own query, so an
 * unmounted tab simply does not fetch.
 */
export function BudgetSection({ categoryIcons }: BudgetSectionProps) {
  const { t } = useTranslation();
  const now = new Date();
  const [activeTab, setActiveTab] = useState<BudgetTab>("monthly");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [yearlyYear, setYearlyYear] = useState(now.getFullYear());
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  const tabClass = (tab: BudgetTab) =>
    `shrink-0 whitespace-nowrap px-3 py-1 rounded-md text-xs font-semibold transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text)]"
    }`;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)] flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {t("budget.title")}
        </p>
        <div className="flex bg-[var(--surface-light)] p-0.5 rounded-lg">
          <button
            onClick={() => setActiveTab("monthly")}
            className={tabClass("monthly")}
            aria-pressed={activeTab === "monthly"}
          >
            {t("budget.monthlyBudget")}
          </button>
          <button
            onClick={() => setActiveTab("yearly")}
            className={tabClass("yearly")}
            aria-pressed={activeTab === "yearly"}
          >
            {t("budget.yearly.tab")}
          </button>
          <button
            onClick={() => setActiveTab("projects")}
            className={tabClass("projects")}
            aria-pressed={activeTab === "projects"}
          >
            {t("budget.projectBudgets")}
          </button>
        </div>
      </div>

      {activeTab === "monthly" && (
        <MonthlyBudgetTab
          year={year}
          month={month}
          onYearChange={setYear}
          onMonthChange={setMonth}
          categoryIcons={categoryIcons}
        />
      )}
      {activeTab === "yearly" && (
        <YearlyBudgetTab
          year={yearlyYear}
          onYearChange={setYearlyYear}
          categoryIcons={categoryIcons}
        />
      )}
      {activeTab === "projects" && (
        <ProjectBudgetTab
          selectedProject={selectedProject}
          onSelectProject={setSelectedProject}
          categoryIcons={categoryIcons}
        />
      )}
    </div>
  );
}
