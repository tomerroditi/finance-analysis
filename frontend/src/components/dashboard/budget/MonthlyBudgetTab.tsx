import React, { useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { formatMonthYear } from "../../../utils/dateFormatting";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import { normalizeAnalysis } from "./normalizeAnalysis";

interface MonthlyBudgetTabProps {
  year: number;
  month: number;
  onYearChange: (year: number) => void;
  onMonthChange: (month: number) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const MonthlyBudgetTab: React.FC<MonthlyBudgetTabProps> = ({
  year,
  month,
  onYearChange,
  onMonthChange,
  categoryIcons,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const qk = useQueryKeys();
  const queryClient = useQueryClient();

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const isCurrentMonth = year === currentYear && month === currentMonth;
  const monthName = formatMonthYear(new Date(year, month - 1));
  const daysRemaining = new Date(year, month, 0).getDate() - now.getDate();

  const handlePrevious = () => {
    if (month === 1) {
      onMonthChange(12);
      onYearChange(year - 1);
    } else {
      onMonthChange(month - 1);
    }
  };

  const handleNext = () => {
    if (month === 12) {
      onMonthChange(1);
      onYearChange(year + 1);
    } else {
      onMonthChange(month + 1);
    }
  };

  // Prefetch the surrounding 11 months so navigation is instant.
  useEffect(() => {
    for (let i = 1; i <= 11; i++) {
      const d = new Date(currentYear, currentMonth - 1 - i);
      const prefetchYear = d.getFullYear();
      const prefetchMonth = d.getMonth() + 1;
      queryClient.prefetchQuery({
        queryKey: qk.budget.analysis(prefetchYear, prefetchMonth, false),
        queryFn: async () => {
          const res = await budgetApi.getAnalysis(prefetchYear, prefetchMonth, false);
          return res.data;
        },
      });
    }
  }, [qk, currentYear, currentMonth, queryClient]);

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.analysis(year, month, false),
    queryFn: async () => {
      const res = await budgetApi.getAnalysis(year, month, false);
      return res.data;
    },
  });

  const analysis = useMemo(
    () => (data?.rules ? normalizeAnalysis(data.rules) : undefined),
    [data],
  );

  const nav = (
    <div className="h-9 flex items-center justify-between w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={handlePrevious}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center">
          {monthName}
        </p>
        <button
          onClick={handleNext}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
      {isCurrentMonth && (
        <span className="text-xs text-[var(--text-muted)]">
          ⏳ {t("dashboard.daysRemaining", { count: daysRemaining })}
        </span>
      )}
    </div>
  );

  if (isLoading) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <Skeleton variant="chart" className="h-16" />
      </div>
    );
  }

  if (!analysis || analysis.rules.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">
            {t("dashboard.noBudgetRulesForMonth")}
          </p>
          <Link
            to="/budget"
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.addRule")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}
      <div className="mb-4">
        <BudgetTotalBar spent={analysis.totalSpent} total={analysis.totalBudget} />
      </div>
      <BudgetRuleGrid rules={analysis.rules} categoryIcons={categoryIcons} />
      <div className="text-end">
        <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
    </div>
  );
};
