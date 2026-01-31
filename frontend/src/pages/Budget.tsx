import React, { useState } from "react";
import { Layers, Calendar } from "lucide-react";
import { MonthlyBudgetView } from "../components/budget/MonthlyBudgetView";
import { ProjectBudgetView } from "../components/budget/ProjectBudgetView";

export const Budget: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"monthly" | "projects">("monthly");

  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600 mb-2">
            Budget Management
          </h1>
          <p className="text-[var(--text-muted)] font-medium">
            Track your spending, manage allocations, and monitor project
            budgets.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-[var(--surface-light)] p-1 rounded-xl">
          <button
            onClick={() => setActiveTab("monthly")}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold transition-all ${activeTab === "monthly"
              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
              : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
              }`}
          >
            <Calendar size={18} />
            Monthly Budget
          </button>
          <button
            onClick={() => setActiveTab("projects")}
            className={`flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold transition-all ${activeTab === "projects"
              ? "bg-[var(--surface)] text-[var(--primary)] shadow-sm"
              : "text-[var(--text-muted)] hover:text-[var(--text-default)]"
              }`}
          >
            <Layers size={18} />
            Project Budgets
          </button>
        </div>
      </div>

      <div className="bg-[var(--surface)] rounded-2xl shadow-sm border border-[var(--surface-light)] p-6 min-h-[600px]">
        {activeTab === "monthly" ? (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <MonthlyBudgetView />
          </div>
        ) : (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <ProjectBudgetView />
          </div>
        )}
      </div>
    </div>
  );
};
