import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { budgetApi, type YearlyAnalysis } from "../../../services/api";
import { BudgetTotalBar } from "../../common/BudgetTotalBar";
import { Skeleton } from "../../common/Skeleton";
import { useQueryKeys } from "../../../hooks/useQueryKeys";
import { BudgetRuleGrid } from "./BudgetRuleGrid";
import type { BudgetRule } from "./types";

interface YearlyBudgetTabProps {
  year: number;
  onYearChange: (year: number) => void;
  categoryIcons: Record<string, string> | undefined;
}

export const YearlyBudgetTab: React.FC<YearlyBudgetTabProps> = ({
  year,
  onYearChange,
  categoryIcons,
}) => {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const qk = useQueryKeys();

  const { data, isLoading } = useQuery({
    queryKey: qk.budget.yearly(year),
    queryFn: () => budgetApi.getYearlyAnalysis(year).then((r) => r.data as YearlyAnalysis),
  });

  // Yearly analysis emits no "Total Budget" pseudo-rule — the roll-up sums the
  // view — so every row here is a real rule and the totals come from summary.
  const rules: BudgetRule[] = useMemo(
    () =>
      (data?.rules ?? [])
        .map((item) => ({
          id: item.rule.id,
          name: item.rule.name,
          category: item.rule.category,
          budget_amount: item.rule.amount,
          spent_amount: item.current_amount,
        }))
        .sort((a, b) => b.spent_amount - a.spent_amount),
    [data],
  );

  const nav = (
    <div className="h-9 flex items-center w-full mb-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => onYearChange(year - 1)}
          aria-label={t("common.previous")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <p
          className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] w-36 text-center"
          dir="ltr"
        >
          {year}
        </p>
        <button
          onClick={() => onYearChange(year + 1)}
          aria-label={t("common.next")}
          className="p-1 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {isRtl ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
        </button>
      </div>
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

  if (rules.length === 0) {
    return (
      <div className="flex flex-1 flex-col min-h-0">
        {nav}
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-sm text-[var(--text-muted)] mb-3">{t("budget.yearly.empty")}</p>
          <Link
            to="/budget"
            className="flex items-center gap-2 text-sm font-medium text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors cursor-pointer"
          >
            <Plus size={16} />
            {t("budget.yearly.addRule")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col min-h-0">
      {nav}
      <div className="mb-4">
        <BudgetTotalBar
          spent={data?.summary.total_spent ?? 0}
          total={data?.summary.total_allocated ?? 0}
        />
      </div>
      <BudgetRuleGrid rules={rules} categoryIcons={categoryIcons} />
      <div className="text-end">
        <Link to="/budget" className="text-sm font-medium text-[var(--primary)] hover:underline">
          {t("dashboard.viewAllBudgetRules")} &rarr;
        </Link>
      </div>
    </div>
  );
};
