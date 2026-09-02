import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Layers, Calendar, CalendarRange } from "lucide-react";
import { MonthlyBudgetView } from "../components/budget/MonthlyBudgetView";
import { YearlyBudgetView } from "../components/budget/YearlyBudgetView";
import { ProjectBudgetView } from "../components/budget/ProjectBudgetView";

type BudgetTab = "monthly" | "yearly" | "projects";

/**
 * The page owns only the tab state. Each view renders the shared command bar
 * itself (with these tabs passed in), because the period control next to the
 * tabs is per-view — a month stepper, a year stepper, or a project picker.
 */
export const Budget: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<BudgetTab>("monthly");

  // `shrink-0` + `whitespace-nowrap`: on mobile the tabs keep their natural
  // width and the bar scrolls, instead of the widest tab forcing the page
  // past the viewport. See frontend_responsive.md → "Tab Bars & Button Groups".
  const tabClass = (tab: BudgetTab) =>
    `shrink-0 whitespace-nowrap flex items-center justify-center gap-1.5 px-2.5 md:px-3.5 py-2 rounded-lg font-bold text-xs md:text-sm transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
    }`;

  const tabs = (
    <>
      <button
        onClick={() => setActiveTab("monthly")}
        className={tabClass("monthly")}
        aria-pressed={activeTab === "monthly"}
      >
        <Calendar size={16} />
        {t("budget.monthlyBudget")}
      </button>
      <button
        onClick={() => setActiveTab("yearly")}
        className={tabClass("yearly")}
        aria-pressed={activeTab === "yearly"}
      >
        <CalendarRange size={16} />
        {t("budget.yearly.tab")}
      </button>
      <button
        onClick={() => setActiveTab("projects")}
        className={tabClass("projects")}
        aria-pressed={activeTab === "projects"}
      >
        <Layers size={16} />
        {t("budget.projectBudgets")}
      </button>
    </>
  );

  return (
    <div className="container mx-auto max-w-7xl animate-in fade-in duration-500">
      <div className="min-h-[600px]">
        {activeTab === "monthly" && (
          <MonthlyBudgetView tabs={tabs} onViewProjects={() => setActiveTab("projects")} />
        )}
        {activeTab === "yearly" && <YearlyBudgetView tabs={tabs} />}
        {activeTab === "projects" && <ProjectBudgetView tabs={tabs} />}
      </div>
    </div>
  );
};
