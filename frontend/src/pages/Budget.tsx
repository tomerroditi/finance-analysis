import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { Layers, Calendar, CalendarRange } from "lucide-react";
import { MonthlyBudgetView } from "../components/budget/MonthlyBudgetView";
import { YearlyBudgetView } from "../components/budget/YearlyBudgetView";
import { ProjectBudgetView } from "../components/budget/ProjectBudgetView";

type BudgetTab = "monthly" | "yearly" | "projects";

export const Budget: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<BudgetTab>("monthly");

  const tabClass = (tab: BudgetTab) =>
    `flex-1 whitespace-nowrap flex items-center justify-center gap-2 px-3 md:px-6 py-2.5 rounded-lg font-bold text-xs md:text-sm transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
    }`;

  return (
    <div className="container mx-auto max-w-7xl animate-in fade-in duration-500">
      <div className="mb-6">
        <div className="flex w-full gap-1 bg-[var(--surface-light)] p-1 rounded-xl">
          <button onClick={() => setActiveTab("monthly")} className={tabClass("monthly")}>
            <Calendar size={18} />
            {t("budget.monthlyBudget")}
          </button>
          <button onClick={() => setActiveTab("yearly")} className={tabClass("yearly")}>
            <CalendarRange size={18} />
            {t("budget.yearly.tab")}
          </button>
          <button onClick={() => setActiveTab("projects")} className={tabClass("projects")}>
            <Layers size={18} />
            {t("budget.projectBudgets")}
          </button>
        </div>
      </div>

      <div className="min-h-[600px]">
        {activeTab === "monthly" && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <MonthlyBudgetView onViewProjects={() => setActiveTab("projects")} />
          </div>
        )}
        {activeTab === "yearly" && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <YearlyBudgetView />
          </div>
        )}
        {activeTab === "projects" && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <ProjectBudgetView />
          </div>
        )}
      </div>
    </div>
  );
};
