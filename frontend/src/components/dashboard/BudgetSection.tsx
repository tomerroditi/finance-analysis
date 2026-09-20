import { useState } from "react";
import { useTranslation } from "react-i18next";
import { OverviewBudgetTab } from "./budget/OverviewBudgetTab";
import { MonthlyBudgetTab } from "./budget/MonthlyBudgetTab";
import { YearlyBudgetTab } from "./budget/YearlyBudgetTab";
import { ProjectBudgetTab } from "./budget/ProjectBudgetTab";
import type { BudgetTabId } from "../../utils/budgetNavigation";

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
  const [activeTab, setActiveTab] = useState<BudgetTabId>("overview");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [yearlyYear, setYearlyYear] = useState(now.getFullYear());
  const [selectedProject, setSelectedProject] = useState<string | null>(null);

  const tabClass = (tab: BudgetTabId) =>
    `shrink-0 whitespace-nowrap px-3 py-1 rounded-md text-xs font-semibold transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text)]"
    }`;

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-4 md:p-6 border border-[var(--surface-light)] flex flex-col h-full">
      {/* The card sits in a `overflow-y-auto` grid cell, which makes its
          horizontal overflow scrollable too — so a tab strip wider than the
          card used to drag the whole card sideways, figures and all. The strip
          scrolls on its own instead: `min-w-0` lets it shrink below its
          content, `max-w-full` keeps it inside the card, and the tabs stay
          `shrink-0 whitespace-nowrap`. See frontend_responsive.md →
          "Tab Bars & Button Groups". */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4 min-w-0">
        <p className="shrink-0 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {t("budget.title")}
        </p>
        <div
          data-testid="dashboard-budget-tabs"
          className="flex w-full sm:w-auto max-w-full min-w-0 bg-[var(--surface-light)] p-0.5 rounded-lg overflow-x-auto scrollbar-auto-hide"
        >
          <button
            onClick={() => setActiveTab("overview")}
            className={tabClass("overview")}
            aria-pressed={activeTab === "overview"}
          >
            {t("budget.overview.tab")}
          </button>
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

      {activeTab === "overview" && (
        <OverviewBudgetTab
          year={year}
          month={month}
          onYearChange={setYear}
          onMonthChange={setMonth}
        />
      )}
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
