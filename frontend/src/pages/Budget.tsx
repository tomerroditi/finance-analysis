import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { Layers, Calendar, CalendarRange, Gauge } from "lucide-react";
import { OverviewBudgetView } from "../components/budget/OverviewBudgetView";
import { MonthlyBudgetView } from "../components/budget/MonthlyBudgetView";
import { YearlyBudgetView } from "../components/budget/YearlyBudgetView";
import { ProjectBudgetView } from "../components/budget/ProjectBudgetView";
import {
  parseBudgetEntry,
  type BudgetEntry,
  type BudgetTabId,
} from "../utils/budgetNavigation";

/**
 * The page owns only the tab state. Each view renders the shared command bar
 * itself (with these tabs passed in), because the period control next to the
 * tabs is per-view — a month stepper, a year stepper, or a project picker.
 *
 * The opening tab — and the period or project it opens on — comes from the
 * query string, so the dashboard budget card can link into the tab the user
 * was already looking at. That intent is read once, at mount: from then on the
 * views own their cursors, and clicking a tab here only rewrites `?tab=`.
 */
export const Budget: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [entry] = useState(() => parseBudgetEntry(searchParams));
  const [activeTab, setActiveTab] = useState<BudgetTabId>(entry.tab);

  const selectTab = (tab: BudgetTabId) => {
    setActiveTab(tab);
    // `replace`: switching tabs is not a navigation the back button should
    // have to walk through, but the URL still names where you are.
    setSearchParams({ tab }, { replace: true });
  };

  /** A period param only applies to the tab it arrived for. */
  const entryFor = (tab: BudgetTabId): Partial<BudgetEntry> =>
    entry.tab === tab ? entry : {};

  // `shrink-0` + `whitespace-nowrap`: on mobile the tabs keep their natural
  // width and the bar scrolls, instead of the widest tab forcing the page
  // past the viewport. See frontend_responsive.md → "Tab Bars & Button Groups".
  const tabClass = (tab: BudgetTabId) =>
    `shrink-0 whitespace-nowrap flex items-center justify-center gap-1.5 px-2.5 md:px-3.5 rounded-lg font-bold text-xs md:text-sm transition-all ${
      activeTab === tab
        ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
        : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
    }`;

  const tabs = (
    <>
      <button
        onClick={() => selectTab("overview")}
        className={tabClass("overview")}
        aria-pressed={activeTab === "overview"}
      >
        <Gauge size={16} />
        {t("budget.overview.tab")}
      </button>
      <button
        onClick={() => selectTab("monthly")}
        className={tabClass("monthly")}
        aria-pressed={activeTab === "monthly"}
      >
        <Calendar size={16} />
        {t("budget.monthlyBudget")}
      </button>
      <button
        onClick={() => selectTab("yearly")}
        className={tabClass("yearly")}
        aria-pressed={activeTab === "yearly"}
      >
        <CalendarRange size={16} />
        {t("budget.yearly.tab")}
      </button>
      <button
        onClick={() => selectTab("projects")}
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
        {activeTab === "overview" && (
          <OverviewBudgetView
            tabs={tabs}
            initialYear={entryFor("overview").year}
            initialMonth={entryFor("overview").month}
          />
        )}
        {activeTab === "monthly" && (
          <MonthlyBudgetView
            tabs={tabs}
            onViewProjects={() => selectTab("projects")}
            initialYear={entryFor("monthly").year}
            initialMonth={entryFor("monthly").month}
          />
        )}
        {activeTab === "yearly" && (
          <YearlyBudgetView tabs={tabs} initialYear={entryFor("yearly").year} />
        )}
        {activeTab === "projects" && (
          <ProjectBudgetView tabs={tabs} initialProject={entryFor("projects").project} />
        )}
      </div>
    </div>
  );
};
